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
"""Two-factor sign-in for members (an authenticator app's codes).

Anyone can turn it on under preferences, security. With it on, the code is
asked for:

- always, for what matters most: changing the password or email address,
  linking or unlinking a Google/Facebook sign-in, turning two-factor off
  and deleting the account (the last two want a code typed then and there);
- and where the member chooses (preferences, security): when logging in
  (by password or a linked account), when saving preferences, and when
  submitting a post.

A code entered counts for RECENT_MINUTES in that login session, so they
aren't asked again and again. Logging in can also remember the device for
DEVICE_DAYS (a signed cookie that stops working when the password or the
two-factor secret changes).

Apps signed in with OAuth are never asked: they can't type a code, and an
app's access was granted by the member.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

RECENT_MINUTES = 15
DEVICE_DAYS = 30
DEVICE_COOKIE = "tippr_otp_device"
RECOVERY_CODES = 10
MAX_TRIES = 10  # codes checked per account per 10 minutes
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"

# actions -> the preference that makes them ask (None: always)
ACTIONS = {
    "password": None,
    "email": None,
    "linked_logins": None,
    "login": "pref_otp_login",
    "settings": "pref_otp_settings",
    "post": "pref_otp_post",
}


def enabled(account):
    return bool(getattr(account, "otp_secret", None))


def from_app():
    """An app (OAuth) is making this request, not the website."""
    return bool(getattr(c, "oauth_user", None))


###############################################################################
# "Entered a code a moment ago": per login session
###############################################################################

def _session_key(account):
    session = request.cookies.get(g.login_cookie, "") or ""
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:20]
    return "otp:recent_%s_%s" % (account._id36, digest)


def mark_recent(account):
    g.gencache.set(_session_key(account), True, time=RECENT_MINUTES * 60)


def recent(account):
    return bool(g.gencache.get(_session_key(account)))


def needs_code(account, action):
    """Whether doing action now needs a code typed in."""
    if not enabled(account) or from_app():
        return False
    pref = ACTIONS[action]
    if pref and not getattr(account, pref, False):
        return False
    return not recent(account)


###############################################################################
# Checking a code: the authenticator's, or a recovery code
###############################################################################

def _hash_recovery(code):
    normalized = code.replace("-", "").replace(" ", "").lower()
    return hashlib.sha256(
        (g.secrets["SECRET"] if isinstance(g.secrets["SECRET"], str)
         else g.secrets["SECRET"].decode("latin-1")).encode("utf-8") +
        b":" + normalized.encode("utf-8")).hexdigest()


def new_recovery_codes(account):
    """Make a new set of recovery codes (replacing any old ones), keep only
    their hashes, and return the codes to show once."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    codes = ["".join(secrets.choice(alphabet) for _ in range(4)) + "-" +
             "".join(secrets.choice(alphabet) for _ in range(4))
             for _ in range(RECOVERY_CODES)]
    account.otp_recovery_codes = [_hash_recovery(code) for code in codes]
    account._commit()
    return codes


def recovery_codes_left(account):
    return len(getattr(account, "otp_recovery_codes", None) or [])


def use_recovery_code(account, code):
    """True if code is one of the account's unused recovery codes (which
    is then used up)."""
    if not code or len(code.replace("-", "").replace(" ", "")) != 8:
        return False
    hashes = list(getattr(account, "otp_recovery_codes", None) or [])
    wanted = _hash_recovery(code)
    for h in hashes:
        if hmac.compare_digest(h, wanted):
            hashes.remove(h)
            account.otp_recovery_codes = hashes
            account._commit()
            g.log.info("two-factor: %s used a recovery code (%d left)",
                       account.name, len(hashes))
            return True
    return False


def check_code(account, code):
    """An authenticator code or a recovery code for account; marks the
    session as recently checked when it's right."""
    from r2.lib.validator import VOneTimePassword
    code = (code or "").strip()
    if not enabled(account) or not code:
        return False
    # a few tries at a time, so the codes can't be guessed
    if not g.disable_ratelimit:
        from r2.lib import ratelimit
        tries = ratelimit.SimpleRateLimit(
            name="two_factor_tries_" + account._id36, seconds=600,
            limit=MAX_TRIES)
        if not tries.record_and_check():
            return False
    # validate_otp remembers used codes per c.user
    previous = c.user
    c.user = account
    try:
        ok = (VOneTimePassword.validate_otp(account.otp_secret, code) or
              use_recovery_code(account, code))
    finally:
        c.user = previous
    if ok:
        mark_recent(account)
    return ok


###############################################################################
# "Don't ask on this device"
###############################################################################

def _device_signature(account, timestamp):
    parts = [timestamp, request.user_agent or "", account.otp_secret or "",
             account.password or ""]
    data = ",".join(p if isinstance(p, str) else p.decode("utf-8", "replace")
                    for p in parts).encode("utf-8")
    secret = g.secrets["SECRET"]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, b"device:" + data, hashlib.sha256).hexdigest()


def device_cookie_name(account):
    return "%s_%s" % (account.name, DEVICE_COOKIE)


def remember_device(account):
    from r2.lib.cookies import Cookie
    timestamp = datetime.utcnow().strftime(TIMESTAMP_FORMAT)
    c.cookies[device_cookie_name(account)] = Cookie(
        value="%s,%s" % (timestamp, _device_signature(account, timestamp)),
        expires=datetime.utcnow() + timedelta(days=DEVICE_DAYS),
        httponly=True, secure=True)


def device_remembered(account):
    value = request.cookies.get(device_cookie_name(account), "")
    try:
        timestamp, signature = value.split(",")
        when = datetime.strptime(timestamp, TIMESTAMP_FORMAT)
    except ValueError:
        return False
    if datetime.utcnow() - when > timedelta(days=DEVICE_DAYS):
        return False
    return hmac.compare_digest(signature, _device_signature(account, timestamp))


def login_needs_code(account):
    """Logging in (by password or a linked account) asks for the code."""
    return (enabled(account) and getattr(account, "pref_otp_login", False)
            and not device_remembered(account))
