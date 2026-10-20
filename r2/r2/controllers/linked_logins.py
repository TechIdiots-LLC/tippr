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
"""Signing in with, and linking, Google and Facebook accounts
(r2.lib.linked_logins)."""

from datetime import datetime, timedelta

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.controllers.tippr_base import TipprController
from r2.lib import linked_logins
from r2.lib.cookies import Cookie, DELETE
from r2.lib.csrf import csrf_exempt
from r2.lib.pages import BoringPage, LinkedLoginLink, LinkedLoginOtp, PaymentStatus
from r2.lib.validator import (
    VBoolean,
    VLength,
    VOneOf,
    VOneTimePassword,
    VThrottledLogin,
    nop,
    validate,
)
from r2.models import Account, NotFound


def _safe_dest(dest):
    """Only addresses on this site (no //other.host)."""
    dest = (dest or "").strip()
    if not dest.startswith("/") or dest.startswith("//") or "\\" in dest:
        return "/"
    return dest


def _message(text, link=None, link_text=None):
    return BoringPage(_("sign in"), show_sidebar=False,
                      content=PaymentStatus(text, link, link_text)).render()


class LinkedLoginsController(TipprController):
    @validate(provider=VOneOf("provider", linked_logins.PROVIDER_ORDER),
              purpose=VOneOf("purpose", ("login", "link"), default="login"),
              dest=nop("dest"),
              rem=VBoolean("rem"))
    def GET_start(self, provider, purpose, dest, rem):
        """Off to the provider to sign in (or to link an account)."""
        if not provider:
            return self.abort404()
        if purpose == "link" and not c.user_is_loggedin:
            return self.redirect("/login?dest=/prefs/security")
        if purpose == "login" and c.user_is_loggedin:
            return self.redirect(_safe_dest(dest))
        try:
            url, token = linked_logins.start(
                provider, purpose,
                account=c.user if purpose == "link" else None,
                dest=_safe_dest(dest), rem=rem)
        except linked_logins.LoginError as e:
            return _message(str(e), "/login", _("log in"))
        c.cookies[linked_logins.STATE_COOKIE] = Cookie(
            value=token, httponly=True, secure=True,
            expires=datetime.utcnow() + timedelta(
                seconds=linked_logins.STATE_TTL))
        return self.redirect(url)

    @validate(provider=VOneOf("provider", linked_logins.PROVIDER_ORDER),
              code=VLength("code", 2000, empty_error=None),
              state=VLength("state", 200, empty_error=None))
    def GET_callback(self, provider, code, state):
        """Where the provider sends the browser back."""
        if not provider:
            return self.abort404()
        cookie_state = request.cookies.get(linked_logins.STATE_COOKIE)
        c.cookies[linked_logins.STATE_COOKIE] = Cookie(value="",
                                                       expires=DELETE)
        name = _(linked_logins.PROVIDERS[provider]["name"])
        try:
            record, identity = linked_logins.finish(provider, code, state,
                                                    cookie_state)
        except linked_logins.LoginError as e:
            return _message(str(e), "/login", _("log in"))

        if record["purpose"] == "link":
            if not c.user_is_loggedin or c.user._id != record["account_id"]:
                return _message(_("Log in to the account you want to link "
                                  "it to, then try again."),
                                "/login?dest=/prefs/security", _("log in"))
            try:
                linked_logins.link(c.user, provider, identity)
            except linked_logins.LoginError as e:
                return _message(str(e), "/prefs/security", _("back"))
            return self.redirect("/prefs/security?linked=" + provider)

        account_id = linked_logins.account_id_for(provider,
                                                  identity["subject"])
        if not account_id:
            # nobody linked it: offer to log in with a password and link it
            token = linked_logins.hold_unlinked(record, provider, identity)
            c.cookies[linked_logins.LINK_COOKIE] = Cookie(
                value=token, httponly=True, secure=True,
                expires=datetime.utcnow() + timedelta(
                    seconds=linked_logins.STATE_TTL))
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginLink(
                                  token, name, identity.get("email"))).render()
        try:
            account = Account._byID(account_id, data=True)
        except NotFound:
            account = None
        if not account or account._deleted or account._banned:
            return _message(_("That account can't be logged into."))

        if account.otp_secret:
            token = linked_logins.hold_for_otp(account, record, provider,
                                               identity["subject"])
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginOtp(token)).render()
        return self._finish_login(account, record["rem"], record["dest"],
                                  provider, identity["subject"])

    def _finish_login(self, account, rem, dest, provider, subject):
        c.user = account
        c.user_is_loggedin = True
        self.login(account, rem=rem)
        linked_logins.touch(provider, subject)
        g.log.info("linked logins: %s signed in with %s", account.name,
                   provider)
        return self.redirect(_safe_dest(dest))

    @csrf_exempt
    @validate(token=VLength("token", 200, empty_error=None),
              user=VThrottledLogin(["user", "passwd"]))
    def POST_link_existing(self, token, user):
        """Log in with a password to link the outside account just signed
        in with (it wasn't linked to anyone). Failed passwords count
        against the login rate limits, as on the login form."""
        held = linked_logins.unlinked(
            token, request.cookies.get(linked_logins.LINK_COOKIE))
        if not held:
            return _message(_("That sign-in took too long. Please start "
                              "again."), "/login", _("log in"))
        provider = held["provider"]
        name = _(linked_logins.PROVIDERS[provider]["name"])
        if not user:
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginLink(
                                  token, name, held["identity"].get("email"),
                                  wrong=True)).render()
        try:
            linked_logins.link(user, provider, held["identity"])
        except linked_logins.LoginError as e:
            return _message(str(e), "/login", _("log in"))
        linked_logins.unlinked_done(token)
        c.cookies[linked_logins.LINK_COOKIE] = Cookie(value="",
                                                      expires=DELETE)
        g.log.info("linked logins: %s linked %s while signing in",
                   user.name, provider)
        return self._finish_login(user, held["rem"], held["dest"], provider,
                                  held["identity"]["subject"])

    @csrf_exempt
    @validate(token=VLength("token", 200, empty_error=None),
              otp=nop("otp"))
    def POST_otp(self, token, otp):
        """The two-factor code, for an account that has it. (No modhash:
        the sign-in token is the secret.)"""
        held = linked_logins.pending(token)
        if not held:
            return _message(_("That sign-in took too long. Please start "
                              "again."), "/login", _("log in"))
        account = Account._byID(held["account_id"], data=True)
        # validate_otp remembers used codes per account (c.user)
        logged_out_user, c.user = c.user, account
        valid = bool(otp) and VOneTimePassword.validate_otp(
            account.otp_secret, otp)
        if not valid:
            c.user = logged_out_user
            linked_logins.pending_failed(token, held)
            if not linked_logins.pending(token):
                return _message(_("Too many wrong codes. Please start "
                                  "again."), "/login", _("log in"))
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginOtp(token, wrong=True)).render()
        linked_logins.pending_done(token)
        return self._finish_login(account, held["rem"], held["dest"],
                                  held["provider"], held["subject"])
