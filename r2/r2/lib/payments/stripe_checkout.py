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
"""Stripe Checkout (hosted payment page).

We create a Checkout Session and send the buyer to Stripe's page, which
offers cards plus Google Pay, Apple Pay, Link and whatever else is turned
on under Settings > Payment methods in the Stripe dashboard. Card details
never touch this site.

Settings: the secret key (sk_test_… for testing, sk_live_… for real, or a
restricted key that can write Checkout Sessions and Refunds). Webhooks are
optional; add one for checkout.session.completed,
checkout.session.async_payment_succeeded,
checkout.session.async_payment_failed, checkout.session.expired and
charge.refunded pointing at /api/payments/webhook/stripe.

This talks to the API directly (not the stripe package, whose global key
belongs to the old card form in r2.controllers.ipn).
"""

from r2.lib.payments import CURRENCY, PaymentError
from r2.lib.payments._http import call

API = "https://api.stripe.com/v1"


def _api(settings, method, path, **kwargs):
    return call(method, API + path, auth=(settings["stripe_secret_key"], ""),
                **kwargs)


def check_credentials(settings):
    _api(settings, "GET", "/checkout/sessions", params={"limit": 1})


def create_checkout(payment, settings, return_url, cancel_url,
                    buyer_email=None):
    data = {
        "mode": "payment",
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": CURRENCY.lower(),
        "line_items[0][price_data][unit_amount]": payment["pennies"],
        "line_items[0][price_data][product_data][name]":
            payment["description"][:250],
        "success_url": return_url,
        "cancel_url": cancel_url,
        "client_reference_id": payment["id"],
        "metadata[tippr_payment]": payment["id"],
        "payment_intent_data[metadata][tippr_payment]": payment["id"],
    }
    if buyer_email:
        data["customer_email"] = buyer_email
    _, session = _api(settings, "POST", "/checkout/sessions", data=data,
                      headers={"Idempotency-Key": "session-" + payment["id"]})
    if not session.get("id") or not session.get("url"):
        raise PaymentError("Stripe didn't give a checkout page")
    return session["id"], session["url"]


def fetch_status(payment, settings, returning=False):
    _, session = _api(settings, "GET",
                      "/checkout/sessions/%s" % payment["provider_ref"],
                      params={"expand[]": "payment_intent.latest_charge"})
    intent = session.get("payment_intent")
    state = {}
    if isinstance(intent, dict):
        state["capture_ref"] = intent.get("id")
        charge = intent.get("latest_charge")
        if isinstance(charge, dict) and charge.get("refunded"):
            # refunded in full (a partial refund leaves it paid)
            state["status"] = "refunded"
            return state
    elif intent:
        state["capture_ref"] = intent

    if session.get("payment_status") in ("paid", "no_payment_required"):
        state["status"] = "paid"
    elif session.get("status") == "expired":
        state["status"] = "expired"
    elif session.get("status") == "complete":
        # completed with a delayed method (a bank debit): wait for it
        state["status"] = "pending"
    else:
        state["status"] = None
    return state


def refund(payment, settings, pennies=None, key="full"):
    """Refund all of it, or pennies of it (key tells refunds apart, so a
    retried one isn't made twice)."""
    if not payment["capture_ref"]:
        raise PaymentError("no Stripe payment to refund")
    data = {"payment_intent": payment["capture_ref"]}
    if pennies:
        data["amount"] = int(pennies)
    _api(settings, "POST", "/refunds", data=data,
         headers={"Idempotency-Key": "refund-%s-%s" % (payment["id"], key)})


def webhook_refs(event):
    """(our payment id, session id, payment intent id) from an event."""
    obj = (event.get("data") or {}).get("object") or {}
    event_type = event.get("type", "")
    metadata = obj.get("metadata") or {}
    payment_id = metadata.get("tippr_payment")
    if event_type.startswith("checkout.session"):
        return (payment_id or obj.get("client_reference_id"), obj.get("id"),
                obj.get("payment_intent"))
    if event_type.startswith("charge.") or event_type.startswith("refund"):
        return payment_id, None, obj.get("payment_intent")
    return payment_id, None, None
