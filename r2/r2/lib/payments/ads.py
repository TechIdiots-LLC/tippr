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
"""Paying for sold ads (promoted posts' campaigns) through r2.lib.payments.

reddit's ads put an authorization hold on a card (authorize.net, removed)
when the advertiser paid, and charged it the day before the campaign
started. With
these providers the advertiser pays the whole budget when they submit the
campaign, and is refunded if the ad isn't approved:

- Paying records a Bid for the campaign that's already charged (with
  PROVIDER_PAYMENT_METHOD_ID as its payment method and an id made from the
  payment's), and the campaign waits for review like any paid one. The
  daily charge step finds it charged and leaves it alone.
- Anything that voids the campaign's payment (rejecting the ad, changing
  the budget, deleting the campaign, paying again) refunds it in full
  (r2.lib.bids.void_transaction calls refund_bid()).
- The partial refund for an ad that showed less than was paid for goes
  back through the provider too.
- A refund made in the provider's dashboard unpays the campaign.

BitPay payments can't be refunded from here: a void marks the payment for
a refund by hand (the campaign's log and /admin/payments say so).
"""

from pylons import app_globals as g

from r2.lib import payments

# the Bid.pay_id of a campaign paid through r2.lib.payments (freebies are
# -1; reddit's authorize.net payment profiles were positive)
PROVIDER_PAYMENT_METHOD_ID = -2

# Bid.transaction ids for these payments: above any authorize.net one an
# old database may have, and positive (negative ones are freebies)
TRANSACTION_BASE = 10 ** 15


def reference(link, campaign):
    return "%s:%s" % (link._fullname, campaign._id36)


def transaction_id(payment):
    return TRANSACTION_BASE + int(payment["id"][:12], 16)


def _load(payment):
    """(link, campaign) a payment is for; either may be None if deleted."""
    from r2.models import Link, NotFound, PromoCampaign
    fullname, _, campaign_id36 = (payment["reference"] or "").partition(":")
    try:
        link = Link._by_fullname(fullname, data=True)
    except (NotFound, ValueError):
        return None, None
    try:
        campaign = PromoCampaign._byID36(campaign_id36, data=True)
    except (NotFound, ValueError):
        return link, None
    if campaign.link_id != link._id or getattr(campaign, "_deleted", False):
        return link, None
    return link, campaign


def is_provider_bid(bid):
    return bid is not None and bid.pay_id == PROVIDER_PAYMENT_METHOD_ID


def payment_for_bid(link_fullname, campaign_id36, transaction):
    """The payment behind one of these Bids."""
    for payment in payments.for_reference(
            "ad", "%s:%s" % (link_fullname, campaign_id36)):
        if transaction_id(payment) == int(transaction):
            return payment
    return None


def campaign_bid(link, campaign):
    from r2.lib import promote
    return promote.get_transactions(link, [campaign]).get(campaign._id)


def checkout(provider, link_fullname, campaign_id36, buyer):
    """Start paying a campaign's budget; returns the provider's page.
    ValueError if it can't be paid this way (or isn't the buyer's)."""
    from r2.lib import promote
    from r2.models import Link, NotFound, PromoCampaign
    if provider not in payments.enabled_providers("ad"):
        raise ValueError("provider not enabled")
    if not buyer:
        raise ValueError("not signed in")
    try:
        link = Link._by_fullname(link_fullname or "", data=True)
        campaign = PromoCampaign._byID36(campaign_id36 or "", data=True)
    except (NotFound, ValueError):
        raise ValueError("no such campaign")
    if (campaign.link_id != link._id or link.author_id != buyer._id or
            not promote.is_promo(link)):
        raise ValueError("not your campaign")
    if campaign.is_house or campaign.total_budget_pennies <= 0:
        raise ValueError("nothing to pay")
    bid = campaign_bid(link, campaign)
    if bid and not bid.is_void() and bid.is_charged():
        raise ValueError("already paid for")
    min_start, max_start, _max_end = promote.get_date_limits(link)
    if not (min_start <= campaign.start_date.date() <= max_start):
        raise ValueError("change the campaign's start date first")

    description = "%s - ad: %s (%s to %s)" % (
        g.site_name or g.domain, link.title[:80],
        campaign.start_date.strftime("%Y-%m-%d"),
        campaign.end_date.strftime("%Y-%m-%d"))
    payment = payments.create_payment(
        provider, "ad", campaign.total_budget_pennies, description,
        reference=reference(link, campaign), account=buyer,
        data={"budget_pennies": campaign.total_budget_pennies})
    email = buyer.email if getattr(buyer, "email_verified", False) else None
    return payments.start_checkout(payment, buyer_email=email)


def done_url(payment):
    """Where the advertiser goes after paying: the ad's campaigns."""
    from r2.lib import promote
    link, _ = _load(payment)
    return promote.promo_edit_url(link) if link else "/promoted"


def on_paid(payment):
    from r2.lib import emailer, hooks, promote
    from r2.models import Account, Bid, PromotionLog
    from r2.models.promo import PROMOTE_STATUS

    link, campaign = _load(payment)
    if not campaign:
        _refund_unwanted(payment, link, "the campaign was deleted")
        return
    if payment["pennies"] != campaign.total_budget_pennies:
        _refund_unwanted(payment, link, "the budget changed while paying")
        return
    bid = campaign_bid(link, campaign)
    trans_id = transaction_id(payment)
    if bid and bid.transaction == trans_id:
        return
    if bid and not bid.is_void() and bid.is_charged():
        _refund_unwanted(payment, link, "the campaign was already paid for")
        return

    # replaces a freebie or an old authorization, if there was one
    promote.void_campaign(link, campaign, reason="changed_payment")

    user = Account._byID(link.author_id, data=True)
    dollars = payment["pennies"] / 100.
    new_bid = Bid._new(trans_id, user, PROVIDER_PAYMENT_METHOD_ID, link._id,
                       dollars, campaign._id)
    # the money's already taken: nothing to charge before it runs
    new_bid.charged()
    campaign.trans_id = trans_id
    campaign._commit()

    PromotionLog.add(link, "campaign %s paid with %s: $%s (payment %s, "
                     "trans_id: %d)" % (campaign._id, payment["provider"],
                                        payments.dollars(payment["pennies"]),
                                        payment["id"], trans_id))
    if promote.is_finished(link):
        # a finished ad with a new paid campaign needn't be reviewed again
        new_status = PROMOTE_STATUS.accepted
    else:
        new_status = max(PROMOTE_STATUS.unseen, link.promote_status)
    promote.update_promote_status(link, new_status)
    emailer.promo_total_budget(link, dollars, campaign.start_date)
    hooks.get_hook("promote.campaign_paid").call(link=link, campaign=campaign)


def _refund_unwanted(payment, link, why):
    """A payment for a campaign that can't take it: give it back."""
    from r2.models import PromotionLog
    g.log.warning("payments: refunding %s: %s", payment["id"], why)
    if link:
        PromotionLog.add(link, "refunding payment %s: %s" % (payment["id"], why))
    try:
        payments.refund(payment, take_back=False)
    except payments.PaymentError as e:
        g.log.error("payments: %s needs refunding by hand (%s): %s",
                    payment["id"], why, e)


def on_refunded(payment):
    """Refunded outside the ads code (the provider's dashboard, or
    /admin/payments): the campaign isn't paid for any more."""
    from r2.models import NO_TRANSACTION, PromotionLog
    link, campaign = _load(payment)
    if not campaign:
        return
    bid = campaign_bid(link, campaign)
    if bid and bid.transaction == transaction_id(payment):
        bid.void()
        campaign.trans_id = NO_TRANSACTION
        campaign._commit()
        PromotionLog.add(link, "payment %s refunded: campaign %s is unpaid"
                         % (payment["id"], campaign._id))


def refund_bid(bid, pennies=None):
    """Refund one of these Bids, in full (a void) or pennies of it (an ad
    that showed less than was paid for). Returns (success, message)."""
    from r2.models import Link
    link = Link._byID(bid.thing_id, data=True)
    from r2.models import PromoCampaign
    campaign = PromoCampaign._byID(bid.campaign, data=True)
    payment = payment_for_bid(link._fullname, campaign._id36, bid.transaction)
    if not payment:
        return False, "no payment found for this campaign"
    if payment["status"] == "refunded":
        return True, None
    try:
        payments.refund(payment, pennies=pennies, take_back=False)
    except payments.PaymentError as e:
        if not payments.can_refund(payment["provider"]):
            # BitPay: an admin refunds it in BitPay's dashboard
            from r2.models import PromotionLog
            PromotionLog.add(link, "payment %s (%s) must be refunded by "
                             "hand: %s" % (payment["id"], payment["provider"],
                                           "$" + payments.dollars(
                                               pennies or payment["pennies"])))
            return True, None
        return False, str(e)
    return True, None


payments.register("ad", on_paid, on_refunded)
