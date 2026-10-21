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

import json
from datetime import datetime, timedelta

from pylons import app_globals as g
from pylons import request, response
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.controllers.tippr_base import TipprController
from r2.lib import linked_logins, two_factor
from r2.lib.cookies import Cookie, DELETE
from r2.lib.csrf import csrf_exempt
from r2.lib.pages import BoringPage, LinkedLoginLink, LinkedLoginOtp, PaymentStatus
from r2.lib.validator import (
    VBoolean,
    VLength,
    VOneOf,
    VThrottledLogin,
    nop,
    validate,
)
from r2.models import Account, NotFound


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
            return self.redirect(linked_logins.safe_dest(dest))
        if purpose == "link" and two_factor.needs_code(c.user,
                                                       "linked_logins"):
            # the code first (preferences, security)
            return self.redirect("/prefs/security")
        try:
            url, token = linked_logins.start(
                provider, purpose,
                account=c.user if purpose == "link" else None,
                dest=linked_logins.safe_dest(dest), rem=rem)
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

        if two_factor.login_needs_code(account):
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
        if provider:
            linked_logins.touch(provider, subject)
            g.log.info("linked logins: %s signed in with %s", account.name,
                       provider)
        return self.redirect(linked_logins.safe_dest(dest))

    @validate(dest=nop("dest"))
    def GET_otp(self, dest):
        """A password login waiting for the two-factor code (the login
        form sends the browser here; r2.controllers.login)."""
        token = request.cookies.get(linked_logins.OTP_COOKIE)
        held = linked_logins.pending(token)
        if not held or c.user_is_loggedin:
            return self.redirect("/login")
        if not held.get("dest") and dest:
            held["dest"] = linked_logins.safe_dest(dest)
            linked_logins.pending_update(token, held)
        return BoringPage(_("sign in"), show_sidebar=False,
                          content=LinkedLoginOtp(token)).render()

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
        linked_logins.unlinked_done(token)
        c.cookies[linked_logins.LINK_COOKIE] = Cookie(value="",
                                                      expires=DELETE)
        if two_factor.enabled(user):
            # the code before linking (and signing in)
            otp_token = linked_logins.hold_for_otp(
                user, held, provider, held["identity"]["subject"],
                link_identity=held["identity"])
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginOtp(otp_token)).render()
        return self._link_and_login(user, held["rem"], held["dest"],
                                    provider, held["identity"])

    def _link_and_login(self, account, rem, dest, provider, identity):
        try:
            linked_logins.link(account, provider, identity)
        except linked_logins.LoginError as e:
            return _message(str(e), "/login", _("log in"))
        g.log.info("linked logins: %s linked %s while signing in",
                   account.name, provider)
        return self._finish_login(account, rem, dest, provider,
                                  identity["subject"])

    def _passkey_json(self, data):
        response.content_type = "application/json"
        return json.dumps(data)

    @csrf_exempt
    @validate(token=VLength("token", 200, empty_error=None))
    def POST_passkey_options(self, token):
        """"Use a passkey" on the code page: the options for the browser,
        for the account whose sign-in is waiting (the token is the secret)."""
        from r2.lib import passkeys
        held = linked_logins.pending(token)
        if not held:
            return self._passkey_json({"error": _(
                "That sign-in took too long. Please start again.")})
        account = Account._byID(held["account_id"], data=True)
        try:
            options, challenge = passkeys.authentication_options(account)
        except passkeys.PasskeyError as e:
            return self._passkey_json({"error": _(str(e))})
        return self._passkey_json({"options": json.loads(options),
                                   "token": challenge})

    @csrf_exempt
    @validate(token=VLength("token", 200, empty_error=None),
              challenge=VLength("challenge", 100, empty_error=None),
              credential=VLength("credential", 20000, empty_error=None))
    def POST_passkey_auth(self, token, challenge, credential):
        """The browser's passkey answer on the code page; returns a token
        the form then sends as its code (POST_otp)."""
        from r2.lib import passkeys
        held = linked_logins.pending(token)
        if not held or not credential:
            return self._passkey_json({"error": _(
                "That sign-in took too long. Please start again.")})
        account = Account._byID(held["account_id"], data=True)
        try:
            code = passkeys.authenticate(account, challenge, credential)
        except passkeys.PasskeyError as e:
            return self._passkey_json({"error": _(str(e))})
        return self._passkey_json({"code": code})

    @csrf_exempt
    @validate(token=VLength("token", 200, empty_error=None),
              otp=nop("otp"),
              remember=VBoolean("remember"))
    def POST_otp(self, token, otp, remember):
        """The two-factor code, for an account that has it. (No modhash:
        the sign-in token is the secret.)"""
        held = linked_logins.pending(token)
        if not held:
            return _message(_("That sign-in took too long. Please start "
                              "again."), "/login", _("log in"))
        account = Account._byID(held["account_id"], data=True)
        if not two_factor.check_code(account, otp):
            linked_logins.pending_failed(token, held)
            if not linked_logins.pending(token):
                return _message(_("Too many wrong codes. Please start "
                                  "again."), "/login", _("log in"))
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginOtp(token, wrong=True)).render()
        linked_logins.pending_done(token)
        c.cookies[linked_logins.OTP_COOKIE] = Cookie(value="", expires=DELETE)
        if remember:
            two_factor.remember_device(account)
        if held.get("link_identity"):
            return self._link_and_login(account, held["rem"], held["dest"],
                                        held["provider"],
                                        held["link_identity"])
        return self._finish_login(account, held["rem"], held["dest"],
                                  held["provider"], held["subject"])
