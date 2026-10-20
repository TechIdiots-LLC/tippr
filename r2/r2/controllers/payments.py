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
"""Paying with the providers on /admin/payments (r2.lib.payments): the
checkout button's target, where providers send buyers back, and their
webhooks."""

from pylons import app_globals as g
from pylons import request, response
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.controllers.tippr_base import TipprController
from r2.lib import payments
from r2.lib.csrf import csrf_exempt
from r2.lib.pages import BoringPage, PaymentStatus
from r2.lib.validator import VLength, VOneOf, VPrintable, nop, validate


def _status_page(message, link=None, link_text=None, refresh=False):
    return BoringPage(_("payment"), show_sidebar=False,
                      content=PaymentStatus(message, link, link_text,
                                            refresh)).render()


class PaymentsController(TipprController):
    @csrf_exempt
    @validate(provider=VOneOf("provider", payments.PROVIDER_ORDER),
              passthrough=VPrintable("passthrough", 50),
              purpose=VOneOf("purpose", ("gold", "ad"), default="gold"),
              link=nop("link"),
              campaign=nop("campaign"))
    def POST_checkout(self, provider, passthrough, purpose, link, campaign):
        """Start paying with a provider: off to its payment page.

        No modhash: gift codes can be bought signed out, and a gold
        purchase is named by its payment blob's code, a secret only the
        payment page knows (and the blob says whose it is). Ads need the
        advertiser signed in (r2.lib.payments.ads)."""
        if not provider:
            return _status_page(_("That payment method isn't available."))
        buyer = c.user if c.user_is_loggedin else None
        try:
            if purpose == "ad":
                from r2.lib.payments import ads
                url = ads.checkout(provider, link, campaign, buyer)
            else:
                from r2.lib.payments import gold
                url = gold.checkout(provider, passthrough, buyer)
        except ValueError as e:
            g.log.info("payments: refused checkout (%s): %s", provider, e)
            return _status_page(
                _("This purchase can't be paid for any more: it may have "
                  "been paid already, or it's too old. Please start again."),
                "/gold" if purpose == "gold" else "/promoted",
                _("start again"))
        except payments.PaymentError as e:
            g.log.warning("payments: %s checkout failed: %s", provider, e)
            return _status_page(
                _("The payment couldn't be started with %(provider)s. "
                  "Please try again in a moment, or pay another way.") %
                {"provider": _(payments.PROVIDERS[provider][0])})
        return self.redirect(url, code=303)

    @validate(payment_id=VLength("payment_id", 40))
    def GET_return(self, payment_id):
        """Where providers send the buyer back after paying. PayPal's
        payment is taken (captured) here."""
        payment = payments.sync(payments.get(payment_id), returning=True)
        if not payment:
            return self.abort404()
        if payment["purpose"] == "ad":
            from r2.lib.payments import ads
            done_url = ads.done_url(payment)
        else:
            done_url = None

        if payment["status"] == "paid":
            if done_url:
                return self.redirect(done_url)
            return self.redirect("/gold/thanks?v=paid")
        if payment["status"] in ("created", "pending"):
            if payment["provider"] in ("coinbase", "bitpay"):
                message = _("Thanks! Your payment is being confirmed on the "
                            "network, which can take a while. Your purchase "
                            "is delivered as soon as it's confirmed; you can "
                            "close this page.")
            else:
                message = _("Thanks! Your payment is being processed. Your "
                            "purchase is delivered as soon as it's done; "
                            "you can close this page.")
            return _status_page(message, refresh=True)
        if payment["status"] == "refunded":
            return _status_page(_("This payment was refunded."))
        return _status_page(
            _("The payment didn't go through, so you haven't been "
              "charged."), done_url or "/gold", _("try again"))

    @validate(payment_id=VLength("payment_id", 40))
    def GET_cancel(self, payment_id):
        """Where providers send the buyer if they don't pay."""
        payment = payments.get(payment_id)
        if payment and payment["purpose"] == "ad":
            from r2.lib.payments import ads
            return self.redirect(ads.done_url(payment))
        return self.redirect("/gold")

    @csrf_exempt
    @validate(provider=VOneOf("provider", payments.PROVIDER_ORDER))
    def POST_webhook(self, provider):
        """A provider's notification. What it says isn't trusted: it's only
        a cue to ask the provider about the payment (payments.sync), so a
        forged one can't do anything."""
        response.content_type = "text/plain"
        if not provider:
            return self.abort404()
        try:
            payment = payments.handle_webhook(provider, request.body,
                                              request.headers)
        except payments.PaymentError:
            # the provider will send it again
            response.status_code = 503
            return "try again"
        return "ok" if payment else "ignored"
