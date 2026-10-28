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
"""Signing in with, and linking, Google, Facebook, GitHub and Discord accounts
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
    def pre(self):
        TipprController.pre(self)
        # these pages carry the sign-in's own token: never for a shared
        # cache, even with no cookie set (/logins/otp)
        c.no_page_cache = True

    @validate(provider=VOneOf("provider", linked_logins.PROVIDER_ORDER),
              purpose=VOneOf("purpose", ("login", "link", "switch"),
                             default="login"),
              dest=nop("dest"),
              rem=VBoolean("rem"))
    def GET_start(self, provider, purpose, dest, rem):
        """Off to the provider to sign in (or to link an account, or to add
        the account it's linked to to the account switcher: "switch")."""
        if not provider:
            return self.abort404()
        if purpose in ("link", "switch") and not c.user_is_loggedin:
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
        if record["purpose"] == "switch":
            return self._switch_to_linked(record, provider, name, identity,
                                          account_id)
        if not account_id:
            # nobody linked it: offer to log in with a password and link it
            token = linked_logins.hold_unlinked(record, provider, identity)
            c.cookies[linked_logins.LINK_COOKIE] = Cookie(
                value=token, httponly=True, secure=True,
                expires=datetime.utcnow() + timedelta(
                    seconds=linked_logins.STATE_TTL))
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginLink(
                                  token, name, identity.get("email"),
                                  person_name=identity.get("name"))).render()
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

    def _switch_to_linked(self, record, provider, name, identity, account_id):
        """Back from the provider with the account switcher's "sign in
        with": that outside account's account here joins the switcher, as
        adding one with its password does (POST /api/switch_add)."""
        from r2.lib import account_switcher
        back = linked_logins.safe_dest(record["dest"])
        if not c.user_is_loggedin:
            return self.redirect("/login")
        try:
            account = Account._byID(account_id, data=True) if account_id else None
        except NotFound:
            account = None
        if not account or account._deleted or account._banned:
            return _message(_("That %(name)s account isn't linked to an account "
                              "here. Link it in that account's preferences "
                              "(security) first.") % {"name": name},
                            back, _("back"))
        if account._id == c.user._id:
            return _message(_("That's the account you're using."), back, _("back"))
        if not (account_switcher.allowed() or account_switcher.qualifies(account)):
            return _message(_("The account switcher is for tippr gold members "
                              "and admins."), back, _("back"))
        if len(account_switcher.accounts()) >= account_switcher.MAX_ACCOUNTS:
            return _message(_("You can keep at most %(n)d other accounts.") % {
                "n": account_switcher.MAX_ACCOUNTS}, back, _("back"))
        account_switcher.remember_current()
        record = dict(record, rem=True, switch=True)
        if account_switcher.needs_code(account):
            token = linked_logins.hold_for_otp(account, record, provider,
                                               identity["subject"])
            return BoringPage(_("sign in"), show_sidebar=False,
                              content=LinkedLoginOtp(token)).render()
        return self._finish_login(account, True, record["dest"], provider,
                                  identity["subject"], switch=True)

    def _finish_login(self, account, rem, dest, provider, subject,
                      code_entered=False, switch=False):
        if switch:
            # added to the account switcher: the account in use was kept
            # (account_switcher.remember_current), and admin mode belongs
            # to it, not this one
            c.cookies[g.admin_cookie] = Cookie(value="", expires=DELETE)
        c.user = account
        c.user_is_loggedin = True
        self.login(account, rem=rem)
        if provider:
            linked_logins.touch(provider, subject)
            g.log.info("linked logins: %s signed in with %s", account.name,
                       provider)
        if code_entered:
            # the code just typed counts in the new login session too, as
            # it would have after logging in (preferences, security)
            session = c.cookies.get(g.login_cookie)
            if session is not None:
                two_factor.mark_recent(account, session.value)
            if getattr(c, "two_factor_recovery_used", False):
                # a recovery code: probably a lost phone or key, so off to
                # where it can be replaced
                return self.redirect("/prefs/security?recovered=1")
        return self.redirect(linked_logins.safe_dest(dest))

    @validate(dest=nop("dest"))
    def GET_otp(self, dest):
        """A password login waiting for the two-factor code (the login
        form sends the browser here; r2.controllers.login)."""
        token = request.cookies.get(linked_logins.OTP_COOKIE)
        held = linked_logins.pending(token)
        # (logged in: only adding an account to the switcher)
        if not held or (c.user_is_loggedin and not held.get("switch")):
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
                                  wrong=True,
                                  person_name=held["identity"].get("name"))).render()
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

    def _link_and_login(self, account, rem, dest, provider, identity,
                        code_entered=False):
        try:
            linked_logins.link(account, provider, identity)
        except linked_logins.LoginError as e:
            return _message(str(e), "/login", _("log in"))
        g.log.info("linked logins: %s linked %s while signing in",
                   account.name, provider)
        return self._finish_login(account, rem, dest, provider,
                                  identity["subject"],
                                  code_entered=code_entered)

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
    def POST_passkey_signin_options(self):
        """The login form's passkey sign-in (autofill, or its button): the
        options for the browser to offer any of this site's passkeys."""
        from r2.lib import passkeys
        if c.user_is_loggedin:
            return self._passkey_json({"error": _("You're logged in.")})
        options, token = passkeys.signin_options()
        return self._passkey_json({"options": json.loads(options),
                                   "token": token})

    @csrf_exempt
    @validate(token=VLength("token", 200, empty_error=None),
              credential=VLength("credential", 20000, empty_error=None),
              rem=VBoolean("rem"),
              dest=nop("dest"))
    def POST_passkey_signin(self, token, credential, rem, dest):
        """The browser's passkey answer on the login form: signs in to the
        account it belongs to, with no password or code (the passkey
        checked the person: r2.lib.passkeys.signin)."""
        from r2.lib import passkeys, ratelimit
        if c.user_is_loggedin:
            return self._passkey_json({"error": _("You're logged in.")})
        if not g.disable_ratelimit:
            tries = ratelimit.SimpleRateLimit(
                name="passkey_signin_" + (request.ip or ""), seconds=600,
                limit=30)
            if not tries.record_and_check():
                return self._passkey_json({"error": _(
                    "Too many tries. Please wait a few minutes and try "
                    "again.")})
        if not (token and credential):
            return self._passkey_json({"error": _(
                "We couldn't check your passkey. Try again.")})
        try:
            account = passkeys.signin(token, credential)
        except passkeys.PasskeyError as e:
            return self._passkey_json({"error": _(str(e))})
        if account._deleted or account._banned:
            return self._passkey_json({"error": _(
                "That account can't be logged into.")})
        if account.name in g.admins or getattr(account, "employee", False):
            # staff tools (admin mode, the support queue) want the password
            # and a second step: a passkey alone is one device
            g.log.info("passkeys: %s (staff) tried to sign in with a "
                       "passkey alone", account.name)
            return self._passkey_json({"error": _(
                "Staff accounts sign in with their password, then a code "
                "or passkey.")})
        c.user = account
        c.user_is_loggedin = True
        self.login(account, rem=rem)
        # the passkey checked the person just now: preferences, security
        # opens without another code for a while
        session = c.cookies.get(g.login_cookie)
        if session is not None:
            two_factor.mark_recent(account, session.value)
        g.log.info("passkeys: %s signed in with a passkey", account.name)
        return self._passkey_json({"ok": True,
                                   "dest": linked_logins.safe_dest(dest)})

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
                                        held["link_identity"],
                                        code_entered=True)
        return self._finish_login(account, held["rem"], held["dest"],
                                  held["provider"], held["subject"],
                                  code_entered=True,
                                  switch=held.get("switch", False))
