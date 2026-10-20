# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################
"""Coinbase Business checkouts (crypto: USDC on Base).

(Coinbase Commerce, which the old "Bitcoin" button used, is shut down.)
We create a checkout priced in dollars, which Coinbase converts to USDC,
and send the buyer to Coinbase's payment page. The checkout is COMPLETED
once the payment settles on-chain; we check when the buyer comes back and
when a webhook arrives.

Settings: a CDP secret API key (portal.cdp.coinbase.com, API keys): its key
ID and secret, Ed25519 (the default: a base64 string) or ECDSA (a PEM
"EC PRIVATE KEY"). Sandbox uses Coinbase's test checkouts. Webhooks are
optional (they're set up with the CDP CLI, for the checkout.payment.*
events, pointing at /api/payments/webhook/coinbase).

Requests are authenticated with a JWT signed by that key, for each
request, made here with pycryptodome (already a dependency).
"""

import base64
import hashlib
import json
import os
import time
import uuid

from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS, eddsa

from r2.lib.payments import CURRENCY, PaymentError, dollars
from r2.lib.payments._http import call

HOST = "business.coinbase.com"
PREFIX = {"sandbox": "/sandbox/api/v1", "live": "/api/v1"}


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signer(secret):
    """(JWT alg, sign(bytes) -> bytes) for a CDP key secret."""
    secret = secret.strip().replace("\\n", "\n")
    if "BEGIN" in secret:
        try:
            key = ECC.import_key(secret)
        except (ValueError, IndexError, TypeError):
            raise PaymentError("the Coinbase key secret isn't a valid key")
        signer = DSS.new(key, "fips-186-3")
        # JWS wants r||s, which is DSS's default "binary" encoding
        return "ES256", lambda data: signer.sign(SHA256.new(data))
    try:
        raw = base64.b64decode(secret, validate=True)
    except (ValueError, TypeError):
        raise PaymentError("the Coinbase key secret isn't valid base64")
    if len(raw) not in (32, 64):
        raise PaymentError("the Coinbase key secret should be 64 bytes")
    key = ECC.construct(curve="Ed25519", seed=raw[:32])
    signer = eddsa.new(key, "rfc8032")
    return "EdDSA", signer.sign


def make_jwt(key_id, secret, method, path, now=None):
    alg, sign = _signer(secret)
    now = int(now or time.time())
    header = {"alg": alg, "typ": "JWT", "kid": key_id,
              "nonce": os.urandom(16).hex()}
    claims = {"sub": key_id, "iss": "cdp", "aud": ["cdp_service"],
              "nbf": now, "exp": now + 120,
              "uri": "%s %s%s" % (method, HOST, path)}
    signing_input = "%s.%s" % (
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(claims, separators=(",", ":")).encode()))
    signature = sign(signing_input.encode("ascii"))
    return "%s.%s" % (signing_input, _b64url(signature))


def idempotency_key(name):
    """A UUID v4 (the form Coinbase wants) that's the same for the same
    name, so a retried request isn't done twice."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()[:16]
    return str(uuid.UUID(bytes=digest, version=4))


def _api(settings, method, path, **kwargs):
    path = PREFIX[settings["coinbase_mode"]] + path
    token = make_jwt(settings["coinbase_key_id"],
                     settings["coinbase_key_secret"], method, path)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = "Bearer " + token
    headers["Content-Type"] = "application/json"
    return call(method, "https://%s%s" % (HOST, path), headers=headers,
                **kwargs)


def check_credentials(settings):
    _api(settings, "GET", "/checkouts", params={"pageSize": 1})


def create_checkout(payment, settings, return_url, cancel_url,
                    buyer_email=None):
    body = {
        "amount": dollars(payment["pennies"]),
        "currency": CURRENCY,
        "description": payment["description"][:500],
        "metadata": {"tippr_payment": payment["id"]},
        "successRedirectUrl": return_url,
        "failRedirectUrl": cancel_url,
    }
    _, checkout = _api(settings, "POST", "/checkouts", json=body,
                       headers={"X-Idempotency-Key":
                                idempotency_key("checkout-" + payment["id"])})
    if not checkout.get("id") or not checkout.get("url"):
        raise PaymentError("Coinbase didn't give a payment page")
    return checkout["id"], checkout["url"]


STATUS = {
    "ACTIVE": None,
    "PROCESSING": "pending",
    "COMPLETED": "paid",
    # a partial refund leaves it paid: an admin decides
    "PARTIALLY_REFUNDED": "paid",
    "REFUNDED": "refunded",
    "EXPIRED": "expired",
    "DEACTIVATED": "expired",
    "FAILED": "failed",
}


def fetch_status(payment, settings, returning=False):
    _, checkout = _api(settings, "GET",
                       "/checkouts/%s" % payment["provider_ref"])
    return {"status": STATUS.get(checkout.get("status"))}


def refund(payment, settings, pennies=None, key="full"):
    """Refund all of it, or pennies of it (key tells refunds apart, so a
    retried one isn't made twice)."""
    _api(settings, "POST", "/checkouts/%s/refund" % payment["provider_ref"],
         json={"amount": dollars(pennies or payment["pennies"]),
               "currency": CURRENCY, "reason": "refunded by the site"},
         headers={"X-Idempotency-Key": idempotency_key(
             "refund-%s-%s" % (payment["id"], key))})


def _find(value, key):
    """The first value for key anywhere in a JSON document."""
    if isinstance(value, dict):
        if key in value and isinstance(value[key], str):
            return value[key]
        for item in value.values():
            found = _find(item, key)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find(item, key)
            if found:
                return found
    return None


def webhook_refs(event):
    """(our payment id, checkout id, None) from a webhook event: our id is
    in the checkout's metadata, wherever the event puts the checkout."""
    payment_id = _find(event, "tippr_payment")
    checkout_id = _find(event, "checkoutId")
    if not checkout_id:
        data = event.get("data") if isinstance(event.get("data"), dict) else event
        checkout_id = data.get("id") if isinstance(data.get("id"), str) else None
    return payment_id, checkout_id, None
