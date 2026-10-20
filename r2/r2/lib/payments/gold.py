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
"""Buying gold, gold to give, gifts and gift codes through r2.lib.payments.

The /gold payment page makes a payment blob (what's being bought, by whom,
for whom: r2.controllers.ipn) and shows a button for each provider. Paying
starts a payment whose reference is the blob's code; once it's paid, the
purchase is delivered the way every gold payment always was
(GoldPaymentController.complete_gold_purchase), and a refund takes it back
(reverse_gold_purchase).
"""

from pylons import app_globals as g
from pylons.i18n import _

from r2.lib import payments


def transaction_id(payment):
    """The payment's id in the gold table."""
    return payments.TRANSACTION_PREFIX[payment["provider"]] + payment["id"]


def describe(goldtype, months, recipient=None):
    if goldtype == "coins":
        what = _("%(count)d months of gold to give") % {"count": months}
    elif months % 12 == 0:
        what = _("%(count)d year(s) of gold") % {"count": months // 12}
    else:
        what = _("%(count)d month(s) of gold") % {"count": months}
    if goldtype == "gift" and recipient:
        what = _("%(what)s for %(name)s") % {"what": what, "name": recipient}
    elif goldtype == "code":
        what = _("a gift code for %(what)s") % {"what": what}
    return "%s - %s" % (g.site_name or g.domain, what)


def checkout(provider, passthrough, buyer=None):
    """Start paying for the purchase in a payment blob; returns the
    provider's page to send the buyer to. ValueError if the blob isn't one
    that can be paid for this way (or isn't the buyer's)."""
    from r2.controllers.ipn import GoldException, validate_blob
    if provider not in payments.enabled_providers("gold"):
        raise ValueError("provider not enabled")
    try:
        blob = validate_blob(passthrough)
    except GoldException as e:
        raise ValueError(str(e))
    raw = g.hardcache.get("payment_blob-%s" % passthrough) or {}
    if raw.get("status") != "initialized":
        raise ValueError("already paid for")
    goldtype = blob["goldtype"]
    if goldtype == "autorenew":
        # subscriptions still go through the old PayPal and Stripe forms
        raise ValueError("subscriptions can't be paid this way")
    if blob.get("buyer") and (not buyer or buyer._id != blob["buyer"]._id):
        raise ValueError("not your purchase")
    months, pennies = payments.gold_price(raw.get("months") or 1)
    recipient = blob.get("recipient")
    payment = payments.create_payment(
        provider, "gold", pennies,
        describe(goldtype, months, recipient.name if recipient else None),
        reference=passthrough, account=blob.get("buyer"),
        email=blob.get("email"),
        data={"months": months, "goldtype": goldtype})
    email = blob.get("email") or (getattr(buyer, "email", None)
                                  if buyer and buyer.email_verified else None)
    return payments.start_checkout(payment, buyer_email=email)


def on_paid(payment):
    from r2.controllers.ipn import GoldPaymentController, Webhook
    from r2.models import retrieve_gold_transaction
    trans_id = transaction_id(payment)
    if retrieve_gold_transaction(trans_id):
        return
    webhook = Webhook(passthrough=payment["reference"],
                      transaction_id=trans_id, pennies=payment["pennies"],
                      months=int(payment["data"].get("months") or 1),
                      payer_email=payment["email"] or "",
                      payer_id=payment["account_id"] or payment["email"] or "")
    webhook.load_blob()
    GoldPaymentController.complete_gold_purchase(webhook)
    # the blob can't start another payment now
    raw = g.hardcache.get("payment_blob-%s" % payment["reference"])
    if raw:
        raw["status"] = "processed"
        g.hardcache.set("payment_blob-%s" % payment["reference"], raw,
                        86400 * 30)


def on_refunded(payment):
    from r2.controllers.ipn import _gold_support, reverse_gold_purchase
    from r2.lib.errors import MessageError
    from r2.models import (Account, retrieve_gold_transaction,
                           send_system_message)
    trans_id = transaction_id(payment)
    transaction = retrieve_gold_transaction(trans_id)
    if not transaction or transaction.status != "processed":
        # a gift code (status unclaimed/claimed) can't be taken back once
        # it's out; it's still marked refunded here
        g.log.info("payments: refunded %s, no gold to take back (%s)",
                   payment["id"], transaction.status if transaction else None)
        return
    reverse_gold_purchase(trans_id)
    if payment["account_id"]:
        buyer = Account._byID(int(payment["account_id"]), data=True)
        try:
            send_system_message(
                buyer, _("gold refund"),
                _("Your gold payment has been refunded, contact "
                  "%(gold_email)s for details") % {"gold_email":
                                                    _gold_support()})
        except MessageError:
            g.log.error("payments: can't tell %s about a refund", buyer.name)


payments.register("gold", on_paid, on_refunded)
