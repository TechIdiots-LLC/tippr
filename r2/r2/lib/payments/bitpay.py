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
"""BitPay invoices (Bitcoin and the other coins BitPay takes).

We create an invoice priced in dollars and send the buyer to BitPay's
invoice page. An invoice is "paid" once the buyer sends the coins and
"confirmed" (then "complete") once the network confirms it; we deliver at
confirmed. BitPay's notifications (IPNs) aren't signed, so as with every
provider we only use them as a cue to fetch the invoice from BitPay.

Settings: a "pos" (point of sale) API token, from the BitPay dashboard
(Payment Tools > API Tokens, without "require authentication"): it can
create and read invoices, nothing else. Test mode uses test.bitpay.com
(which needs its own test account and token). Notifications need no
setup: each invoice says where to send them.

Refunds are made in the BitPay dashboard (they need the buyer's address),
then marked refunded on /admin/payments.
"""

from r2.lib.payments import CURRENCY, PaymentError, dollars, webhook_url
from r2.lib.payments._http import call

HOSTS = {
    "test": "https://test.bitpay.com",
    "live": "https://bitpay.com",
}
HEADERS = {"X-Accept-Version": "2.0.0", "Content-Type": "application/json"}


def _base(settings):
    return HOSTS[settings["bitpay_mode"]]


def check_credentials(settings):
    # a pos token can only create and read invoices, so there's nothing
    # to check it with short of making one
    raise PaymentError("BitPay tokens can't be checked without making an "
                       "invoice: try a test purchase")


def create_checkout(payment, settings, return_url, cancel_url,
                    buyer_email=None):
    invoice = {
        "token": settings["bitpay_token"],
        "price": float(dollars(payment["pennies"])),
        "currency": CURRENCY,
        "orderId": payment["id"],
        "posData": payment["id"],
        "itemDesc": payment["description"][:100],
        "notificationURL": webhook_url("bitpay"),
        "redirectURL": return_url,
        "closeURL": cancel_url,
        "fullNotifications": True,
        "transactionSpeed": "medium",
    }
    if buyer_email:
        invoice["buyer"] = {"email": buyer_email}
    _, body = call("POST", _base(settings) + "/invoices", headers=HEADERS,
                   json=invoice)
    data = body.get("data") or {}
    if not data.get("id") or not data.get("url"):
        raise PaymentError("BitPay didn't give an invoice page")
    return data["id"], data["url"]


STATUS = {
    "new": None,
    # coins sent, waiting for confirmations
    "paid": "pending",
    "confirmed": "paid",
    "complete": "paid",
    "expired": "expired",
    "invalid": "failed",
    "declined": "failed",
}


def fetch_status(payment, settings, returning=False):
    _, body = call("GET", "%s/invoices/%s" % (_base(settings),
                                              payment["provider_ref"]),
                   headers=HEADERS, params={"token": settings["bitpay_token"]})
    data = body.get("data") or {}
    if data.get("orderId") and data["orderId"] != payment["id"]:
        raise PaymentError("BitPay invoice %s isn't for payment %s"
                           % (payment["provider_ref"], payment["id"]))
    return {"status": STATUS.get(data.get("status"))}


def refund(payment, settings, pennies=None, key="full"):
    raise PaymentError("BitPay refunds are made in the BitPay dashboard")


def webhook_refs(event):
    """(our payment id, invoice id, None) from an IPN (the old format has
    the invoice at the top, the new one under "data")."""
    data = event.get("data") if isinstance(event.get("data"), dict) else event
    return (data.get("orderId") or data.get("posData"), data.get("id"), None)
