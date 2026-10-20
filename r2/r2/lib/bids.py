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
"""A sold ad campaign's payment record (models.bidding.Bid).

Each campaign that's paid for has a Bid, named by the campaign's trans_id:

- a freebie (a sponsor gave it away): a negative trans_id (minus the ad's
  link id) and FREEBIE_PAYMENT_METHOD_ID;
- paid through a provider on /admin/payments (r2.lib.payments.ads): an id
  made from the payment's, and PROVIDER_PAYMENT_METHOD_ID, recorded as
  charged at once, since the money is taken when the campaign is
  submitted.

(reddit's authorize.net card holds, charged the day before a campaign ran,
are gone.) These functions keep their (success, message) returns, which
r2.lib.promote checks.
"""

from pylons import app_globals as g
from sqlalchemy.orm.exc import MultipleResultsFound

from r2.lib.db.thing import NotFound
from r2.models.bidding import Bid

FREEBIE_PAYMENT_METHOD_ID = -1


def _paid_with_provider(bid):
    from r2.lib.payments import ads
    return ads.is_provider_bid(bid)


def is_charged_transaction(trans_id, campaign_id):
    if not trans_id:
        return False    # trans_id 0: no bid
    try:
        bid = Bid.one(transaction=trans_id, campaign=campaign_id)
    except NotFound:
        return False
    except MultipleResultsFound:
        g.log.error('Multiple bids for trans_id %s' % trans_id)
        return False
    return bid.is_charged() or bid.is_refund()


def auth_freebie_transaction(amount, user, link, campaign_id):
    transaction_id = -link._id
    try:
        # a freebie given again: update it
        bid = Bid.one(thing_id=link._id, transaction=transaction_id,
                      campaign=campaign_id)
    except NotFound:
        Bid._new(transaction_id, user, FREEBIE_PAYMENT_METHOD_ID, link._id,
                 amount, campaign_id)
    else:
        bid.bid = amount
        bid.auth()
    return transaction_id, ""


def charge_transaction(user, transaction_id, campaign_id):
    """Before a campaign runs. Freebies are "charged" now; provider
    payments were charged when they were paid."""
    bid = Bid.one(transaction=transaction_id, campaign=campaign_id)
    if not bid.is_charged():
        bid.charged()
    return True, None


def void_transaction(user, transaction_id, campaign_id):
    """The campaign isn't paid for any more: a provider payment is refunded
    in full."""
    bid = Bid.one(transaction=transaction_id, campaign=campaign_id)
    if _paid_with_provider(bid):
        from r2.lib.payments import ads
        success, message = ads.refund_bid(bid)
        if success:
            bid.void()
        return success, message
    bid.void()
    return True, None


def refund_transaction(user, transaction_id, campaign_id, amount):
    """Give back amount (dollars) of what was paid: an ad that showed less
    than was paid for."""
    bid = Bid.one(transaction=transaction_id, campaign=campaign_id)
    if _paid_with_provider(bid):
        from r2.lib.payments import ads
        success, message = ads.refund_bid(
            bid, pennies=int(round(float(amount) * 100)))
        if success:
            bid.refund(amount)
        return success, message
    bid.refund(amount)
    return True, None
