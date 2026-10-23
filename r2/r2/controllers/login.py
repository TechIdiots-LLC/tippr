# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################
from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

from r2.lib import amqp, emailer, hooks, newsletter
from r2.lib.base import abort
from r2.lib.errors import errors, tippr_http_error
from r2.lib.validator import VRatelimit
from r2.models.account import AccountExists, register


def handle_login(
    controller, form, responder, user, rem=None, signature=None, **kwargs
):
    def _event(error):
        g.events.login_event(
            'login_attempt',
            error_msg=error,
            user_name=request.urlvars.get('url_user'),
            remember_me=rem,
            signature=signature,
            request=request,
            context=c)

    if signature and not signature.is_valid():
        _event(error="SIGNATURE")
        abort(403)

    hook_error = hooks.get_hook("account.login").call_until_return(
        responder=responder,
        request=request,
        context=c,
    )
    # if any of the hooks returned an error, abort the login.  The
    # set_error in this case also needs to exist in the hook.
    if hook_error:
        _event(error=hook_error)
        return

    exempt_ua = (request.user_agent and
                 any(ua in request.user_agent for ua
                     in g.config.get('exempt_login_user_agents', ())))
    if (errors.LOGGED_IN, None) in c.errors:
        if user == c.user or exempt_ua:
            # Allow funky clients to re-login as the current user.
            c.errors.remove((errors.LOGGED_IN, None))
        else:
            _event(error='LOGGED_IN')
            abort(tippr_http_error(409, errors.LOGGED_IN))

    if responder.has_errors("ratelimit", errors.RATELIMIT):
        _event(error='RATELIMIT')

    elif responder.has_errors("passwd", errors.WRONG_PASSWORD):
        _event(error='WRONG_PASSWORD')

    elif not _two_factor_ok(responder, user, rem):
        _event(error='TWO_FACTOR_REQUIRED')

    else:
        controller._login(responder, user, rem)
        _event(error=None)


def _two_factor_ok(responder, user, rem):
    """Whether logging in can go ahead, for an account that wants its
    two-factor code at login (r2.lib.two_factor.login_needs_code). The code
    can come with the password (the `otp` parameter, for scripts); the
    website instead holds the sign-in and asks for it next, on /logins/otp
    (c.two_factor_pending)."""
    from datetime import datetime, timedelta

    from r2.lib import linked_logins, two_factor
    from r2.lib.cookies import Cookie

    if two_factor.from_app() or not two_factor.login_needs_code(user):
        return True
    code = request.params.get("otp")
    if code:
        if two_factor.check_code(user, code):
            return True
    else:
        token = linked_logins.hold_for_otp(
            user, {"dest": request.params.get("dest"), "rem": rem},
            None, None)
        c.cookies[linked_logins.OTP_COOKIE] = Cookie(
            value=token, httponly=True, secure=True,
            expires=datetime.utcnow() + timedelta(
                seconds=linked_logins.PENDING_TTL))
        c.two_factor_pending = True
        responder._send_data(two_factor="/logins/otp")
    c.errors.add(errors.TWO_FACTOR_REQUIRED, field="otp")
    responder.has_errors("otp", errors.TWO_FACTOR_REQUIRED)
    return False


def handle_register(
    controller, form, responder, name, email,
    password, rem=None, newsletter_subscribe=False,
    sponsor=False, signature=None, **kwargs
):

    def _event(error):
        g.events.login_event(
            'register_attempt',
            error_msg=error,
            user_name=request.urlvars.get('url_user'),
            email=request.POST.get('email'),
            remember_me=rem,
            newsletter=newsletter_subscribe,
            signature=signature,
            request=request,
            context=c)

    if signature and not signature.is_valid():
        _event(error="SIGNATURE")
        abort(403)

    if responder.has_errors('user', errors.USERNAME_TOO_SHORT):
        _event(error='USERNAME_TOO_SHORT')

    elif responder.has_errors('user', errors.USERNAME_INVALID_CHARACTERS):
        _event(error='USERNAME_INVALID_CHARACTERS')

    elif responder.has_errors('user', errors.USERNAME_TAKEN_DEL):
        _event(error='USERNAME_TAKEN_DEL')

    elif responder.has_errors('user', errors.USERNAME_TAKEN):
        _event(error='USERNAME_TAKEN')

    elif responder.has_errors('email', errors.BAD_EMAIL):
        _event(error='BAD_EMAIL')

    elif responder.has_errors('passwd', errors.SHORT_PASSWORD):
        _event(error='SHORT_PASSWORD')

    elif responder.has_errors('passwd', errors.BAD_PASSWORD):
        # BAD_PASSWORD is set when SHORT_PASSWORD is set
        _event(error='BAD_PASSWORD')

    elif responder.has_errors('passwd2', errors.BAD_PASSWORD_MATCH):
        _event(error='BAD_PASSWORD_MATCH')

    elif responder.has_errors('ratelimit', errors.RATELIMIT):
        _event(error='RATELIMIT')

    elif (not g.disable_captcha and
            responder.has_errors('captcha', errors.BAD_CAPTCHA)):
        _event(error='BAD_CAPTCHA')

    elif newsletter_subscribe and not email:
        c.errors.add(errors.NEWSLETTER_NO_EMAIL, field="email")
        form.has_errors("email", errors.NEWSLETTER_NO_EMAIL)
        _event(error='NEWSLETTER_NO_EMAIL')

    elif sponsor and not email:
        c.errors.add(errors.SPONSOR_NO_EMAIL, field="email")
        form.has_errors("email", errors.SPONSOR_NO_EMAIL)
        _event(error='SPONSOR_NO_EMAIL')

    else:
        from r2.lib import antispam, site_info
        if not site_info.signups_open():
            c.errors.add(errors.SIGNUPS_CLOSED, field="user")
            form.has_errors("user", errors.SIGNUPS_CLOSED)
            _event(error='SIGNUPS_CLOSED')
            return
        allowed, reason = antispam.check_signup(name, email)
        if not allowed:
            c.errors.add(errors.SPAM_SIGNUP, field="user")
            form.has_errors("user", errors.SPAM_SIGNUP)
            _event(error='SPAM_SIGNUP')
            return
        try:
            user = register(name, password, request.ip)
        except AccountExists:
            c.errors.add(errors.USERNAME_TAKEN, field="user")
            form.has_errors("user", errors.USERNAME_TAKEN)
            _event(error='USERNAME_TAKEN')
            return

        VRatelimit.ratelimit(rate_ip=True, prefix="rate_register_")

        # anything else we know (email, languages)?
        if email:
            user.set_email(email)
            emailer.verify_email(user)

        user.pref_lang = c.lang
        user._commit()

        from r2.lib import early_member
        early_member.on_register(user)

        amqp.add_item('new_account', user._fullname)

        hooks.get_hook("account.registered").call(user=user)

        reject = hooks.get_hook("account.spotcheck").call(account=user)
        if any(reject):
            _event(error='ACCOUNT_SPOTCHECK')
            return

        if newsletter_subscribe and email:
            try:
                newsletter.add_subscriber(email, source="register")
            except newsletter.NewsletterError as e:
                g.log.warning("Failed to subscribe: %r" % e)

        controller._login(responder, user, rem)
        _event(error=None)
