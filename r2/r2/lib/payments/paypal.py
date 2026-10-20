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
"""PayPal, with the Orders API (v2).

We create an order and send the buyer to PayPal to approve it (PayPal,
Venmo, Pay Later, or a card as a guest). PayPal sends them back to our
return address, where we capture the order: that's when the money moves.
If they close the window after approving, the CHECKOUT.ORDER.APPROVED
webhook captures it instead.

Settings: a REST app's client ID and secret (developer.paypal.com, Apps &
Credentials), sandbox or live. Webhooks are optional; add one for
CHECKOUT.ORDER.APPROVED, PAYMENT.CAPTURE.COMPLETED, PAYMENT.CAPTURE.DENIED
and PAYMENT.CAPTURE.REFUNDED pointing at /api/payments/webhook/paypal.
"""

import threading
import time

from pylons import app_globals as g

from r2.lib.payments import CURRENCY, PaymentError, dollars
from r2.lib.payments._http import call

HOSTS = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}

_token_lock = threading.Lock()
_tokens = {}    # (mode, client id) -> (token, expires)


def _base(settings):
    return HOSTS[settings["paypal_mode"]]


def _token(settings):
    key = (settings["paypal_mode"], settings["paypal_client_id"],
           settings["paypal_client_secret"])
    with _token_lock:
        token, expires = _tokens.get(key, (None, 0))
        if token and expires > time.time() + 60:
            return token
    _, body = call("POST", _base(settings) + "/v1/oauth2/token",
                   auth=(settings["paypal_client_id"],
                         settings["paypal_client_secret"]),
                   data={"grant_type": "client_credentials"},
                   headers={"Accept": "application/json"})
    token = body.get("access_token")
    if not token:
        raise PaymentError("PayPal didn't give an access token")
    with _token_lock:
        _tokens[key] = (token, time.time() + int(body.get("expires_in", 300)))
    return token


def _api(settings, method, path, ok=(200, 201), **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = "Bearer " + _token(settings)
    headers["Content-Type"] = "application/json"
    return call(method, _base(settings) + path, ok=ok, headers=headers,
                **kwargs)


def check_credentials(settings):
    _token(settings)


def create_checkout(payment, settings, return_url, cancel_url,
                    buyer_email=None):
    order = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": payment["id"],
            "custom_id": payment["id"],
            "invoice_id": payment["id"],
            "description": payment["description"][:127],
            "amount": {"currency_code": CURRENCY,
                       "value": dollars(payment["pennies"])},
        }],
        "payment_source": {"paypal": {"experience_context": {
            "brand_name": (g.site_name or g.domain)[:127],
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        }}},
    }
    _, body = _api(settings, "POST", "/v2/checkout/orders", json=order,
                   headers={"PayPal-Request-Id": "order-" + payment["id"]})
    url = _link(body, "payer-action") or _link(body, "approve")
    if not body.get("id") or not url:
        raise PaymentError("PayPal didn't give an approval page")
    return body["id"], url


def _link(body, rel):
    for link in body.get("links", []):
        if link.get("rel") == rel:
            return link.get("href")
    return None


def _capture(payment, settings):
    _, body = _api(settings, "POST",
                   "/v2/checkout/orders/%s/capture" % payment["provider_ref"],
                   headers={"PayPal-Request-Id": "capture-" + payment["id"]},
                   ok=(200, 201, 422))
    return body


def _state(order):
    """Our status for a PayPal order."""
    status = order.get("status")
    captures = []
    for unit in order.get("purchase_units", []):
        captures += unit.get("payments", {}).get("captures", [])
    if captures:
        capture = captures[0]
        capture_status = capture.get("status")
        state = {"capture_ref": capture.get("id")}
        if capture_status == "COMPLETED":
            state["status"] = "paid"
        elif capture_status == "PENDING":
            # e.g. an eCheck, or a payment PayPal is reviewing
            state["status"] = "pending"
        elif capture_status == "REFUNDED":
            state["status"] = "refunded"
        elif capture_status in ("DECLINED", "FAILED"):
            state["status"] = "failed"
        else:
            # PARTIALLY_REFUNDED: still paid, an admin decides
            state["status"] = "paid"
        return state
    if status == "VOIDED":
        return {"status": "failed"}
    return {"status": None, "order_status": status}


def fetch_status(payment, settings, returning=False):
    _, order = _api(settings, "GET",
                    "/v2/checkout/orders/%s" % payment["provider_ref"])
    state = _state(order)
    if state.get("order_status") == "APPROVED":
        # approved but not yet captured: take the money now
        body = _capture(payment, settings)
        if body.get("status") or body.get("purchase_units"):
            state = _state(body)
            if state.get("status") is None:
                _, order = _api(settings, "GET", "/v2/checkout/orders/%s"
                                % payment["provider_ref"])
                state = _state(order)
        else:
            # 422: e.g. INSTRUMENT_DECLINED; the buyer can try again
            g.log.warning("payments: PayPal capture of %s refused: %s",
                          payment["id"], body)
            state = {"status": None}
    return state


def refund(payment, settings, pennies=None, key="full"):
    """Refund all of it, or pennies of it (key tells refunds apart, so a
    retried one isn't made twice)."""
    if not payment["capture_ref"]:
        raise PaymentError("no PayPal capture to refund")
    body = {}
    if pennies:
        body["amount"] = {"value": dollars(pennies), "currency_code": CURRENCY}
    _api(settings, "POST",
         "/v2/payments/captures/%s/refund" % payment["capture_ref"],
         json=body,
         headers={"PayPal-Request-Id": "refund-%s-%s" % (payment["id"], key)})


def webhook_refs(event):
    """(our payment id, order id, capture id) from a webhook event."""
    resource = event.get("resource") or {}
    event_type = event.get("event_type", "")
    payment_id = resource.get("custom_id") or resource.get("invoice_id")
    order_id = capture_id = None
    if event_type.startswith("CHECKOUT.ORDER"):
        order_id = resource.get("id")
        units = resource.get("purchase_units") or [{}]
        payment_id = payment_id or units[0].get("custom_id")
    elif event_type.startswith("PAYMENT.CAPTURE"):
        related = (resource.get("supplementary_data") or {}).get(
            "related_ids") or {}
        order_id = related.get("order_id")
        capture_id = resource.get("id")
        # a refund's resource is the refund: its "up" link is the capture
        for link in resource.get("links", []):
            if link.get("rel") == "up" and "/captures/" in link.get("href", ""):
                capture_id = link["href"].rstrip("/").split("/")[-1]
    return payment_id, order_id, capture_id
