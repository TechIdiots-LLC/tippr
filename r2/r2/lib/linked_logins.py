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
"""Signing in with a linked Google, Facebook, GitHub or Discord account.

A member links an outside account to theirs under preferences (security);
from then on the login page's "sign in with Google" (or Facebook) logs them
in without their password. Linking is the only way an outside account
reaches a tippr account: nothing is matched by email address (that would
let whoever controls an address take over an account). Signing in with an
outside account nobody linked offers to log in with a password and link
it, or to make a new account for it (the sign-up form's checks: open
sign-ups, the captcha, the spam check, a username and password). A member
with two-factor sign-in on still enters their code after signing in this
way.

Nothing is built in: an admin turns providers on at /admin/logins with the
site's own OAuth client ID and secret from each provider (settings saved
there override the ini, as payments_* and the like do).

The sign-in is OAuth 2 with the authorization code flow, done on the
server: the provider sends the browser back to /logins/callback/<provider>
with a code, which we exchange for an access token (with our secret, and
PKCE for Google) and use once to ask who signed in. The "state" we send
names a record in the cache and must match a cookie set in the same browser
when the sign-in started, so nobody can make someone else's browser sign in
to an account of theirs.

Links are in PostgreSQL (account_logins), one row per outside account.
"""

import base64
import hashlib
import secrets
from datetime import datetime
from urllib.parse import urlencode

import requests
import sqlalchemy as sa
from pylons import app_globals as g
from pylons.i18n import N_

from r2.lib import site_settings
from r2.lib.db.tdb_sql import create_table, index_str, make_metadata

GROUP = "logins"

# provider -> its settings and endpoints
PROVIDERS = {
    "google": {
        "name": N_("Google"),
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "pkce": True,
        "console": "https://console.cloud.google.com/apis/credentials",
    },
    "facebook": {
        "name": N_("Facebook"),
        "authorize": "https://www.facebook.com/dialog/oauth",
        "token": "https://graph.facebook.com/oauth/access_token",
        "userinfo": "https://graph.facebook.com/me?fields=id,name,email",
        "scope": "email public_profile",
        "pkce": False,
        "console": "https://developers.facebook.com/apps/",
    },
    # (GitHub's and Discord's say only who it is, not an email address)
    "github": {
        "name": N_("GitHub"),
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "scope": "read:user",
        "pkce": False,
        "console": "https://github.com/settings/developers",
        # what to show the member as the account's name, first found
        "name_keys": ("login", "name"),
    },
    "discord": {
        "name": N_("Discord"),
        "authorize": "https://discord.com/oauth2/authorize",
        "token": "https://discord.com/api/oauth2/token",
        "userinfo": "https://discord.com/api/users/@me",
        "scope": "identify",
        "pkce": False,
        "console": "https://discord.com/developers/applications",
        "name_keys": ("username", "global_name"),
    },
}
PROVIDER_ORDER = ["google", "facebook", "github", "discord"]

SETTINGS = {}
for _p in PROVIDER_ORDER:
    SETTINGS.update({_p + "_enabled": False, _p + "_client_id": "",
                     _p + "_client_secret": ""})
SECRET_SETTINGS = tuple(p + "_client_secret" for p in PROVIDER_ORDER)

STATE_COOKIE = "tippr_login_state"
STATE_TTL = 600            # seconds to finish signing in at the provider
PENDING_TTL = 300          # seconds to enter the two-factor code
TIMEOUT = 20


class LoginError(Exception):
    """Signing in with the provider failed (shown to the member)."""


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def login_settings():
    settings = {}
    for name, default in SETTINGS.items():
        value = g.config.get("logins_" + name)
        settings[name] = default if value in (None, "") else value
    for name, value in site_settings.get_settings(GROUP).items():
        if name in SETTINGS:
            settings[name] = value
    for name, default in SETTINGS.items():
        if isinstance(default, bool):
            settings[name] = _bool(settings[name])
        else:
            settings[name] = str(settings[name] or "").strip()
    return settings


def configured(provider, settings=None):
    settings = settings or login_settings()
    return bool(settings[provider + "_client_id"] and
                settings[provider + "_client_secret"])


def enabled_providers(settings=None):
    settings = settings or login_settings()
    return [p for p in PROVIDER_ORDER
            if settings[p + "_enabled"] and configured(p, settings)]


def callback_url(provider):
    return "%s/logins/callback/%s" % (g.https_endpoint.rstrip("/"), provider)


###############################################################################
# The links
###############################################################################

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

links_table = sa.Table(
    "account_logins", METADATA,
    sa.Column("provider", sa.String, primary_key=True),
    # the provider's id for the person (Google's "sub", the others' "id")
    sa.Column("subject", sa.String, primary_key=True),
    sa.Column("account_id", sa.BigInteger, nullable=False),
    # what the provider said when it was linked, to show the member which
    # account it is
    sa.Column("email", sa.String, nullable=True),
    sa.Column("display_name", sa.String, nullable=True),
    sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
)
create_table(links_table, [
    index_str(links_table, "account_id", "account_id"),
])


def safe_dest(dest):
    """Only addresses on this site (no //other.host), for where to go
    after signing in. Control characters and whitespace are refused too:
    urlsplit drops tabs and newlines before it parses, so "/\\t/evil.example"
    would come out as //evil.example, another site."""
    dest = (dest or "").strip()
    if (not dest.startswith("/") or dest.startswith("//") or "\\" in dest or
            any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7f
                for ch in dest)):
        return "/"
    return dest


def _now():
    return datetime.now(g.tz)


def links_for(account):
    with ENGINE.connect() as conn:
        return [dict(r) for r in conn.execute(
            sa.select(links_table)
            .where(links_table.c.account_id == account._id)
            .order_by(links_table.c.provider)).mappings()]


def account_id_for(provider, subject):
    with ENGINE.connect() as conn:
        row = conn.execute(sa.select(links_table.c.account_id).where(
            (links_table.c.provider == provider) &
            (links_table.c.subject == str(subject)))).first()
    return row[0] if row else None


def link(account, provider, identity):
    """Link an outside account; LoginError if it's linked to someone else
    (or this account already has one from that provider)."""
    other = account_id_for(provider, identity["subject"])
    if other and other != account._id:
        raise LoginError("That %s account is already linked to another "
                         "account here." % PROVIDERS[provider]["name"])
    if other == account._id:
        return
    if any(l["provider"] == provider for l in links_for(account)):
        raise LoginError("Your account already has a %s account linked; "
                         "unlink it first." % PROVIDERS[provider]["name"])
    with ENGINE.begin() as conn:
        conn.execute(links_table.insert().values(
            provider=provider, subject=str(identity["subject"]),
            account_id=account._id,
            email=(identity.get("email") or "")[:254] or None,
            display_name=(identity.get("name") or "")[:200] or None,
            created=_now()))


def unlink(account, provider):
    with ENGINE.begin() as conn:
        result = conn.execute(links_table.delete().where(
            (links_table.c.account_id == account._id) &
            (links_table.c.provider == provider)))
    return result.rowcount > 0


def unlink_all(account):
    """When an account is deleted."""
    with ENGINE.begin() as conn:
        conn.execute(links_table.delete().where(
            links_table.c.account_id == account._id))


def touch(provider, subject):
    with ENGINE.begin() as conn:
        conn.execute(links_table.update().where(
            (links_table.c.provider == provider) &
            (links_table.c.subject == str(subject))).values(last_used=_now()))


###############################################################################
# The OAuth flow
###############################################################################

def _state_key(token):
    return "linked_login_state:" + token


def start(provider, purpose, account=None, dest=None, rem=False):
    """(provider's sign-in address, state token for the cookie). purpose:
    "login", "link" (account: who's linking) or "switch" (the account
    switcher: signing in to the account it's linked to, kept alongside)."""
    settings = login_settings()
    if provider not in enabled_providers(settings):
        raise LoginError("Signing in with that isn't available.")
    info = PROVIDERS[provider]
    token = secrets.token_urlsafe(24)
    record = {"provider": provider, "purpose": purpose,
              "account_id": account._id if account else None,
              "dest": dest or "/", "rem": bool(rem)}
    params = {
        "client_id": settings[provider + "_client_id"],
        "redirect_uri": callback_url(provider),
        "response_type": "code",
        "scope": info["scope"],
        "state": token,
    }
    if info["pkce"]:
        verifier = secrets.token_urlsafe(48)
        record["verifier"] = verifier
        params["code_challenge"] = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        params["code_challenge_method"] = "S256"
    if provider == "google":
        params["prompt"] = "select_account"
    g.gencache.set(_state_key(token), record, time=STATE_TTL)
    return "%s?%s" % (info["authorize"], urlencode(params)), token


def finish(provider, code, state, cookie_state):
    """The provider sent the browser back: (state record, identity) where
    identity is {"subject", "email", "name"}. LoginError if anything's
    wrong (an old or replayed link, a different browser, a refusal)."""
    if not state or not cookie_state or not secrets.compare_digest(
            str(state), str(cookie_state)):
        raise LoginError("That sign-in link didn't come from this browser. "
                         "Please start again.")
    record = g.gencache.get(_state_key(state))
    g.gencache.delete(_state_key(state))
    if not record or record.get("provider") != provider:
        raise LoginError("That sign-in took too long. Please start again.")
    if not code:
        raise LoginError("The sign-in was cancelled.")
    settings = login_settings()
    info = PROVIDERS[provider]
    data = {
        "client_id": settings[provider + "_client_id"],
        "client_secret": settings[provider + "_client_secret"],
        "redirect_uri": callback_url(provider),
        "code": code,
        "grant_type": "authorization_code",
    }
    if info["pkce"]:
        data["code_verifier"] = record.get("verifier", "")
    try:
        response = requests.post(info["token"], data=data, timeout=TIMEOUT,
                                 headers={"Accept": "application/json"})
        token = response.json().get("access_token") if response.ok else None
        if not token:
            g.log.warning("linked logins: %s token exchange failed: %s %s",
                          provider, response.status_code, response.text[:200])
            raise LoginError("%s didn't accept the sign-in. Please try "
                             "again." % info["name"])
        response = requests.get(info["userinfo"], timeout=TIMEOUT,
                                headers={"Authorization": "Bearer " + token})
        response.raise_for_status()
        person = response.json()
    except (requests.RequestException, ValueError) as e:
        g.log.warning("linked logins: %s failed: %s", provider, e)
        raise LoginError("Couldn't reach %s. Please try again." % info["name"])
    subject = person.get("sub") or person.get("id")
    if not subject:
        raise LoginError("%s didn't say who signed in." % info["name"])
    name = None
    for key in info.get("name_keys", ("name",)):
        if person.get(key):
            name = str(person[key])
            break
    identity = {"subject": str(subject), "email": person.get("email"),
                "name": name}
    return record, identity


LINK_COOKIE = "tippr_link_pending"


def _unlinked_key(token):
    return "linked_login_unlinked:" + token


def hold_unlinked(record, provider, identity):
    """Signed in at the provider with an account nobody linked: keep who it
    was for a few minutes, so the member can log in with their password
    and link it in one go. Returns the token (also kept in a cookie: it
    must be the same browser)."""
    token = secrets.token_urlsafe(24)
    g.gencache.set(_unlinked_key(token), {
        "provider": provider, "identity": identity, "dest": record["dest"],
        "rem": record["rem"]}, time=STATE_TTL)
    return token


def unlinked(token, cookie_token):
    if not token or not cookie_token or not secrets.compare_digest(
            str(token), str(cookie_token)):
        return None
    return g.gencache.get(_unlinked_key(token))


def unlinked_done(token):
    g.gencache.delete(_unlinked_key(token))


# a password login waiting for its two-factor code (r2.controllers.login)
OTP_COOKIE = "tippr_otp_pending"


def _pending_key(token):
    return "linked_login_pending:" + token


def hold_for_otp(account, record, provider, subject, link_identity=None):
    """Signed in at the provider (or with a password: no provider), and
    the account wants its two-factor code, so keep the sign-in until the
    code is entered. With link_identity, that outside account is linked
    once the code is right. Returns the token."""
    token = secrets.token_urlsafe(24)
    g.gencache.set(_pending_key(token), {
        "account_id": account._id, "dest": record["dest"],
        "rem": record["rem"], "provider": provider, "subject": subject,
        "link_identity": link_identity, "tries": 0,
        # adding an account to the switcher (r2.lib.account_switcher): the
        # member is logged in to another one, kept to switch back to
        "switch": bool(record.get("switch"))}, time=PENDING_TTL)
    return token


def pending(token):
    return g.gencache.get(_pending_key(token)) if token else None


def pending_update(token, held):
    g.gencache.set(_pending_key(token), held, time=PENDING_TTL)


def pending_failed(token, held):
    held["tries"] = held.get("tries", 0) + 1
    if held["tries"] >= 5:
        g.gencache.delete(_pending_key(token))
    else:
        pending_update(token, held)


def pending_done(token):
    g.gencache.delete(_pending_key(token))
