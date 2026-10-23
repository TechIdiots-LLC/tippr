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
"""Two-factor sign-in for members.

Anyone can turn it on under preferences, security, with one or more
methods (the two_factor_methods table): authenticator apps (TOTP codes)
and passkeys (r2.lib.passkeys). Adding or removing a method needs one the
member has already (or the password, for the first one). With it on, a
code (or a passkey) is asked for:

- always, for what matters most: changing the password or email address,
  linking or unlinking a Google/GitHub/etc. sign-in, turning two-factor off
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
import time
from datetime import datetime, timedelta

import sqlalchemy as sa
from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

RECENT_MINUTES = 15
DEVICE_DAYS = 30
DEVICE_COOKIE = "tippr_otp_device"
RECOVERY_CODES = 10
MAX_TRIES = 10  # codes checked per account per 10 minutes

# actions -> the preference that makes them ask (None: always)
ACTIONS = {
    "password": None,
    "email": None,
    "linked_logins": None,
    "two_factor_prefs": None,  # where it asks (below)
    "login": "pref_otp_login",
    "settings": "pref_otp_settings",
    "post": "pref_otp_post",
}


MAX_METHODS = 10  # per account, of each kind
PASSKEY_TOKEN_SECONDS = 120  # a passkey check counts as a code this long


###############################################################################
# The methods: authenticator apps and passkeys
###############################################################################

_db = {}


def _engine():
    """The database, and the methods table (made on first use, so
    importing this needs no database)."""
    if "engine" not in _db:
        from r2.lib.db.tdb_sql import create_table, index_str, make_metadata
        engine = g.dbm.get_engine("main")
        table = _methods_table(make_metadata(engine))
        create_table(table, [
            index_str(table, "account_id", "account_id"),
            index_str(table, "credential_id", "credential_id"),
        ])
        _db.update(engine=engine, table=table)
    return _db["engine"]


def _table():
    _engine()
    return _db["table"]


def _methods_table(metadata):
    return sa.Table(
    "two_factor_methods", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("account_id", sa.BigInteger, nullable=False),
    sa.Column("kind", sa.String, nullable=False),  # "totp" or "passkey"
    sa.Column("name", sa.String, nullable=False),  # what the member calls it
    sa.Column("secret", sa.String, nullable=True),  # totp: the shared secret
    # passkey (base64url): the credential's id and public key (COSE)
    sa.Column("credential_id", sa.String, nullable=True),
    sa.Column("public_key", sa.Text, nullable=True),
    sa.Column("sign_count", sa.BigInteger, nullable=True),
    sa.Column("transports", sa.String, nullable=True),
    sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
    )

KIND_NAMES = {"totp": "authenticator app", "passkey": "passkey"}


def _now():
    return datetime.now(g.tz)


###############################################################################
# Authenticator app secrets, encrypted in the database
###############################################################################
# An authenticator app's code comes from a secret the site keeps too, so a
# copy of the database (a stolen backup) would make codes for every account.
# The secrets are kept encrypted (AES-GCM) with a key from the site's
# [secrets] SECRET, which backups carry separately (secrets.json) and a
# restore puts back. Secrets kept before this are encrypted the next time
# the account's methods are read.

_SEALED = "enc1:"


def _secret_key():
    secret = g.secrets["SECRET"]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, b"two-factor authenticator secrets",
                    hashlib.sha256).digest()


def _aad(account_id):
    # bound to the account: a secret copied to another account's row
    # doesn't open
    return ("totp:%d" % account_id).encode("ascii")


def _seal(secret, account_id):
    import base64
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        g.log.warning("two-factor: the cryptography package is missing, so "
                      "authenticator secrets are kept unencrypted")
        return secret
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_secret_key()).encrypt(nonce, secret.encode("ascii"),
                                           _aad(account_id))
    return _SEALED + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def _open(value, account_id):
    """The secret from its kept form (sealed, or plain from before)."""
    import base64
    if not value or not value.startswith(_SEALED):
        return value
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.urlsafe_b64decode(value[len(_SEALED):].encode("ascii"))
    return AESGCM(_secret_key()).decrypt(raw[:12], raw[12:],
                                         _aad(account_id)).decode("ascii")


def _seal_old_secrets(account, rows):
    """Encrypt the secrets of rows kept before they were encrypted."""
    for row in rows:
        if row["kind"] != "totp" or not row["secret"] or \
                row["secret"].startswith(_SEALED):
            continue
        sealed = _seal(row["secret"], account._id)
        if sealed == row["secret"]:
            return
        with _engine().begin() as conn:
            conn.execute(_table().update()
                         .where(_table().c.id == row["id"])
                         .values(secret=sealed))
        row["secret"] = sealed


def enabled(account):
    """Whether account has two-factor sign-in on (no database query: the
    account keeps how many methods it has)."""
    return bool(getattr(account, "two_factor_methods", 0) or
                getattr(account, "otp_secret", None))


def _migrate(account):
    """Before several methods, an account had one authenticator app's
    secret (otp_secret): make it the first method."""
    secret = getattr(account, "otp_secret", None)
    if not secret:
        return
    with _engine().begin() as conn:
        conn.execute(_table().insert().values(
            id=secrets.token_hex(8), account_id=account._id, kind="totp",
            name=KIND_NAMES["totp"], secret=_seal(secret, account._id),
            created=_now()))
    account.otp_secret = ""
    _changed(account)


def methods(account, kind=None):
    """account's methods (dicts), oldest first."""
    _migrate(account)
    query = (sa.select(_table())
             .where(_table().c.account_id == account._id)
             .order_by(_table().c.created))
    if kind:
        query = query.where(_table().c.kind == kind)
    with _engine().connect() as conn:
        rows = [dict(r) for r in conn.execute(query).mappings()]
    _seal_old_secrets(account, rows)
    return rows


def _changed(account):
    """After adding or removing a method: the count enabled() reads, and a
    new stamp, which signs the cookies that skip the code (remembered
    devices, admin mode), so they stop working."""
    with _engine().connect() as conn:
        kinds = [r[0] for r in conn.execute(
            sa.select(_table().c.kind)
            .where(_table().c.account_id == account._id))]
    count = len(kinds)
    account.two_factor_methods = count
    account.two_factor_passkeys = kinds.count("passkey")
    account.two_factor_stamp = secrets.token_hex(8)
    if not count:
        # two-factor is off: nothing to recover
        account.otp_recovery_codes = []
    account._commit()


def stamp(account):
    """What changes whenever the methods do (for signing cookies)."""
    return (getattr(account, "two_factor_stamp", "") or
            getattr(account, "otp_secret", "") or "")


def _name(name, kind, account, default=None):
    """The name given, or default (else the kind's), numbered when the
    account has one by that name already ("Windows Hello 2")."""
    name = " ".join((name or "").split())[:40]
    if name:
        return name
    taken = {m["name"] for m in methods(account)}
    base, n = default or KIND_NAMES[kind], 1
    while (base if n == 1 else "%s %d" % (base, n)) in taken:
        n += 1
    return base if n == 1 else "%s %d" % (base, n)


class TooManyMethods(Exception):
    pass


def _add(account, kind, name, default_name=None, **values):
    if len(methods(account, kind)) >= MAX_METHODS:
        raise TooManyMethods
    first = not enabled(account)
    with _engine().begin() as conn:
        conn.execute(_table().insert().values(
            id=secrets.token_hex(8), account_id=account._id, kind=kind,
            name=_name(name, kind, account, default_name), created=_now(),
            **values))
    _changed(account)
    g.log.info("two-factor: %s added a %s", account.name, kind)
    return first


def add_totp(account, secret, name=None):
    """Add an authenticator app. Returns whether it's the first method
    (so two-factor just turned on)."""
    return _add(account, "totp", name, secret=_seal(secret, account._id))


def add_passkey(account, credential_id, public_key, sign_count,
                transports="", name=None, default_name=None):
    """Add a passkey (r2.lib.passkeys). Returns whether it's the first
    method. default_name (where it was saved) is used when no name is
    given."""
    return _add(account, "passkey", name, default_name=default_name,
                credential_id=credential_id, public_key=public_key,
                sign_count=sign_count or 0, transports=transports or None)


def passkey_by_credential(credential_id):
    """The passkey method with this credential id (base64url), if any (for
    signing in with a passkey alone, r2.lib.passkeys.signin)."""
    query = (sa.select(_table())
             .where((_table().c.kind == "passkey") &
                    (_table().c.credential_id == credential_id)))
    with _engine().connect() as conn:
        row = conn.execute(query).mappings().first()
    return dict(row) if row else None


def has_passkeys(account):
    """Whether "use a passkey" can be offered (no database query)."""
    return bool(getattr(account, "two_factor_passkeys", 0))


def passkey_used(method_id, sign_count):
    """After a passkey signed: its counter (a lower one later would mean a
    copied key) and when it was used."""
    with _engine().begin() as conn:
        conn.execute(_table().update()
                     .where(_table().c.id == method_id)
                     .values(sign_count=sign_count or 0, last_used=_now()))


def remove_method(account, method_id):
    """Remove one method; True if it was there."""
    _migrate(account)
    with _engine().begin() as conn:
        result = conn.execute(_table().delete().where(
            (_table().c.account_id == account._id) &
            (_table().c.id == method_id)))
    if result.rowcount:
        _changed(account)
        g.log.info("two-factor: %s removed a method", account.name)
    return result.rowcount > 0


def remove_all(account):
    """Turn two-factor off (the member, or an admin's reset)."""
    _migrate(account)
    with _engine().begin() as conn:
        conn.execute(_table().delete().where(
            _table().c.account_id == account._id))
    account.otp_secret = ""
    _changed(account)


def touch(method_id):
    with _engine().begin() as conn:
        conn.execute(_table().update()
                     .where(_table().c.id == method_id)
                     .values(last_used=_now()))


def from_app():
    """An app (OAuth) is making this request, not the website."""
    return bool(getattr(c, "oauth_user", None))


###############################################################################
# "Entered a code a moment ago": per login session
###############################################################################

def _session_key(account, session=None):
    """session: the login cookie's value as set (for one just set); by
    default the request's, which the browser sends quoted."""
    if session is None:
        from urllib.parse import unquote
        session = unquote(request.cookies.get(g.login_cookie, "") or "")
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:20]
    return "otp:recent_%s_%s" % (account._id36, digest)


def mark_recent(account, session=None):
    """A code was just entered in this login session (or in session, the
    login cookie just set, for a code typed while signing in)."""
    # kept: when it runs out (for "unlocked for N more minutes")
    g.gencache.set(_session_key(account, session),
                   int(time.time()) + RECENT_MINUTES * 60,
                   time=RECENT_MINUTES * 60)


def recent(account):
    return bool(g.gencache.get(_session_key(account)))


def recent_minutes_left(account):
    """How many more minutes the code entered in this session counts (at
    least 1), or 0 if there's none."""
    until = g.gencache.get(_session_key(account))
    if not until:
        return 0
    if until is True:
        # kept before the end was
        return RECENT_MINUTES
    return max(1, -(-(until - int(time.time())) // 60))


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


def new_codes_key(account):
    """Where new codes wait (a few minutes) to be shown once."""
    return "otp:newcodes_" + account._id36


def take_new_codes(account):
    """The recovery codes just made, if any; shown only this once."""
    codes = g.gencache.get(new_codes_key(account))
    if codes:
        g.gencache.delete(new_codes_key(account))
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


def _check_totp(account, code):
    """A code from any of account's authenticator apps, each code good
    once. (Which app it's from is found first: marking a code used while
    trying a wrong app would keep the right one from taking it.)"""
    from r2.lib import totp
    from r2.lib.utils import constant_time_compare
    from r2.lib.validator import VOneTimePassword
    if not code.isdigit() or len(code) != 6:
        return False
    for method in methods(account, "totp"):
        try:
            secret = _open(method["secret"], account._id)
        except Exception:
            # sealed with another SECRET (restored without its secrets?)
            g.log.warning("two-factor: %s's authenticator %s can't be "
                          "decrypted", account.name, method["id"])
            continue
        if any(constant_time_compare(code, totp.make_totp(secret, skew=skew))
               for skew in VOneTimePassword.allowed_skew):
            # used up (kept a little longer than codes are accepted)
            used = g.gencache.add(
                "otp:used_%s_%s" % (account._id36, code), True,
                time=totp.PERIOD * (len(VOneTimePassword.allowed_skew) + 1))
            if used:
                touch(method["id"])
            return bool(used)
    return False


def passkey_token(account):
    """After a passkey check (r2.lib.passkeys): a one-use token that counts
    as a code for account, for the form that asked for one."""
    token = "pk-" + secrets.token_urlsafe(18)
    g.gencache.set("otp:pk_" + token, account._id, time=PASSKEY_TOKEN_SECONDS)
    return token


def _use_passkey_token(account, token):
    key = "otp:pk_" + token
    if g.gencache.get(key) != account._id:
        return False
    g.gencache.delete(key)
    return True


def check_code(account, code):
    """A code for account (from an authenticator app), a passkey token or a
    recovery code; marks the session as recently checked when it's right."""
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
        if code.startswith("pk-"):
            ok = _use_passkey_token(account, code)
        else:
            ok = _check_totp(account, code)
            if not ok and use_recovery_code(account, code):
                # (signing in this way suggests a lost device: the login
                # code page then shows what to do about it)
                ok = c.two_factor_recovery_used = True
    finally:
        c.user = previous
    if ok:
        mark_recent(account)
    return ok


###############################################################################
# "Don't ask on this device"
###############################################################################

def _device_signature(account, timestamp):
    parts = [timestamp, request.user_agent or "", stamp(account),
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
    """Don't ask for the code at login on this browser for DEVICE_DAYS."""
    from r2.lib.cookies import Cookie
    timestamp = str(int(time.time()))
    c.cookies[device_cookie_name(account)] = Cookie(
        value="%s.%s" % (timestamp, _device_signature(account, timestamp)),
        expires=datetime.utcnow() + timedelta(days=DEVICE_DAYS),
        httponly=True, secure=True)


def device_remembered(account):
    value = request.cookies.get(device_cookie_name(account), "")
    timestamp, _, signature = value.partition(".")
    if not timestamp.isdigit() or not signature:
        return False
    if time.time() - int(timestamp) > DEVICE_DAYS * 86400:
        return False
    return hmac.compare_digest(signature, _device_signature(account, timestamp))


###############################################################################
# Required for staff and moderators (/admin/config, off by default)
###############################################################################

def staff_required():
    """The site requires two-factor for staff and moderators."""
    return bool(g.live_config.get("require_two_factor_staff"))


def staff_tools_closed(account):
    """Moderator and staff tools are closed to account until it turns
    two-factor on (when the site requires it)."""
    return bool(account) and staff_required() and not enabled(account)


def is_staff_or_moderator(account):
    from r2.models import Vault
    return bool(account.name in g.admins or getattr(account, "employee", False)
                or Vault.reverse_moderator_ids(account))


def closed_for_current_user(account):
    """staff_tools_closed, for the member making this request (others'
    moderator status is never affected, only what this one can do)."""
    try:
        if not c.user_is_loggedin or account is None:
            return False
        if getattr(account, "_id", None) != c.user._id:
            return False
    except Exception:
        # scripts and jobs: no request
        return False
    return staff_tools_closed(account)


def login_needs_code(account):
    """Logging in (by password or a linked account) asks for the code."""
    return (enabled(account) and getattr(account, "pref_otp_login", False)
            and not device_remembered(account))
