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
"""Changing the live config from /admin/config.

The live config ([live_config] in the ini: the admin list, captcha and
vault creation thresholds, sidebar messages and so on) is read once at
startup. Values saved on /admin/config are overrides kept in ZooKeeper
(site settings group "live_config"); every web process applies them to its
g.live_config as soon as they change, so no restart is needed. Removing an
override goes back to the ini's value. Each change is recorded, with who
made it, in the "live_config_log" group (the newest LOG_SIZE entries).

g.live_config is updated in place rather than replaced, because other
objects hold on to it (g.admins and friends read "employees" from it).

When the site reads its live config from ZooKeeper instead
(liveconfig_source = zookeeper, reddit's own setup), this page only shows
the values: they're managed with scripts/write_live_config.
"""

import threading
from datetime import datetime

from pylons import app_globals as g
from pylons.i18n import N_

from r2.lib import site_settings
from r2.lib.configparse import ConfigValue, ConfigValueParser

GROUP = "live_config"
LOG_GROUP = "live_config_log"
LOG_SIZE = 200
MAX_VALUE_LENGTH = 10000

# The settings worth knowing about on a self-hosted site, in the order the
# page shows them; everything else is under "other settings".
COMMON = [
    ("employees", N_(
        "Who has staff permissions: name:level pairs, comma-separated, where "
        "the level is admin, sponsor or employee. Admins can turn on admin "
        "mode. You can't remove your own admin permission here.")),
    ("require_two_factor_staff", N_(
        "Moderators and staff (employees, and admins for admin mode) need "
        "two-factor sign-in turned on (preferences, security) to use their "
        "tools; until then they see a notice asking them to. Members "
        "without it are unaffected.")),
    ("captcha_exempt_link_karma", N_(
        "Accounts with at least this much post karma skip the captcha.")),
    ("captcha_exempt_comment_karma", N_(
        "Accounts with at least this much comment karma skip the captcha.")),
    ("create_vault_account_age_days", N_(
        "How old an account must be, in days, to create a vault (admins "
        "can always create one).")),
    ("create_vault_link_karma", N_(
        "Post karma needed to create a vault (this, or the comment karma "
        "below).")),
    ("create_vault_comment_karma", N_(
        "Comment karma needed to create a vault (this, or the post karma "
        "above).")),
    ("sidebar_message", N_(
        "A notice in every page's sidebar. Blank: none.")),
    ("welcomebar_messages", N_(
        "Messages for the \"new here?\" bar shown to logged-out visitors, "
        "each in double quotes; one is picked at random. \" / \" splits a "
        "message into a heading and a smaller second line, e.g. "
        "\"Welcome! / Pick a few vaults to subscribe to.\"")),
    ("announcement_message", N_(
        "A message in the info bar at the top of listings. For a site-wide "
        "banner, use the announcement on /admin/site instead.")),
    ("discovery_vaults", N_(
        "Vaults that help people find more vaults, for the explore tab: "
        "names, comma-separated.")),
    ("apps_require_approval", N_(
        "New API apps (registered on /prefs/apps) work only for their own "
        "developers until an admin approves them on /admin/apps.")),
    ("app_create_min_account_age_days", N_(
        "How old an account must be, in days, to register an API app.")),
    ("app_create_min_karma", N_(
        "Total karma (posts and comments) needed to register an API app.")),
    ("app_create_require_verified_email", N_(
        "Whether registering an API app needs a verified email address.")),
    ("cflag_min_votes", N_(
        "Votes a post or comment needs before it can count as controversial.")),
    ("cflag_lower_bound", N_(
        "Controversial: the lowest share of upvotes (0 to 1).")),
    ("cflag_upper_bound", N_(
        "Controversial: the highest share of upvotes (0 to 1).")),
]

_TYPE_NAMES = {
    ConfigValue.bool: N_("true or false"),
    ConfigValue.int: N_("whole number"),
    ConfigValue.float: N_("number"),
    ConfigValue.tuple: N_("comma-separated list"),
    ConfigValue.str: N_("text"),
    ConfigValue.messages: N_("quoted messages"),
}

_lock = threading.Lock()
_installed = False
_base_raw = {}      # the ini's values, as written there
_parsers = {}       # key -> parser, for the keys that have a type


def editable():
    """Whether this site keeps its live config in the ini (and so this
    page can override it)."""
    return isinstance(_live_config(), ConfigValueParser)


def _live_config():
    real_g = g._current_obj() if hasattr(g, "_current_obj") else g
    return real_g.live_config


def install():
    """Start applying saved overrides (once per process; cheap to call on
    every request)."""
    global _installed
    if _installed:
        return
    with _lock:
        if _installed:
            return
        live_config = _live_config()
        if isinstance(live_config, ConfigValueParser):
            _base_raw.update(live_config.raw_data)
            _parsers.update(live_config.config_keys)
            site_settings.on_change(GROUP, lambda data: _apply(live_config, data))
        _installed = True


def _parse(key, raw):
    parser = _parsers.get(key)
    return parser(raw, key) if parser else raw


def _apply(live_config, overrides):
    for key in set(_base_raw) | set(overrides):
        raw = overrides.get(key, _base_raw.get(key))
        try:
            live_config[key] = _parse(key, raw)
        except Exception:
            # a bad saved value (it was checked when saved, so this means
            # the spec changed): keep the ini's
            g.log.exception("live config: can't use the saved %s", key)
            if key in _base_raw:
                live_config[key] = _parse(key, _base_raw[key])


def overrides():
    return site_settings.get_settings(GROUP)


def type_name(key):
    parser = _parsers.get(key)
    if parser is None:
        return N_("text")
    return _TYPE_NAMES.get(parser, N_("name:value pairs, comma-separated"))


def settings():
    """[(key, description or None, ini value, override or None)], the
    common settings first."""
    saved = overrides()
    keys = set(_base_raw) | set(_parsers) | set(saved)
    descriptions = dict(COMMON)
    ordered = [key for key, _ in COMMON if key in keys]
    ordered += sorted(keys - set(descriptions))
    return [(key, descriptions.get(key), _base_raw.get(key), saved.get(key))
            for key in ordered]


def check(key, raw, user):
    """An error message for setting key to raw, or None if it's fine."""
    if len(raw) > MAX_VALUE_LENGTH:
        return "too long"
    try:
        value = _parse(key, raw)
    except Exception as e:
        if _parsers.get(key) in _TYPE_NAMES:
            # int("abc") and friends: say what's expected instead
            return "this should be a %s" % type_name(key)
        # e.g. an unknown permission level in employees
        return (str(e).replace(" for None", "") or
                "not a valid %s" % type_name(key))
    if type_name(key) == "quoted messages" and raw.strip():
        # text without quotes parses to no messages at all, and a quote
        # left off pairs up the wrong ones ("a." "b." makes '." "' a
        # message): everything has to be inside a pair of quotes
        outside = ConfigValue.messages_re.sub("", raw).strip()
        if not value or outside or any(not m.strip() for m in value):
            return 'put each message in double quotes, e.g. "Welcome!" "Hello again!"'
    if key == "employees":
        # whoever saves the admin list keeps their own place on it, so the
        # site can't be left without someone able to change it back
        mine = [level for name, level in value.items()
                if name.lower() == user.name.lower()]
        if mine != ["admin"]:
            return "you can't remove your own admin permission"
    return None


def save(key, raw, user):
    """Override key with raw (None: back to the ini). Returns an error
    message, or None."""
    data = overrides()
    old = data.get(key, _base_raw.get(key))
    if raw is None:
        if key not in data:
            return None
        if key == "employees":
            error = check(key, _base_raw.get(key, ""), user)
            if error:
                return error
        data.pop(key)
        new = _base_raw.get(key)
    else:
        error = check(key, raw, user)
        if error:
            return error
        data[key] = raw
        new = raw
    site_settings.save_settings(GROUP, data)
    _log(user, key, old, new, reset=raw is None)
    return None


def save_many(values, user):
    """Save every setting in values ({key: raw}) whose value changed (one
    the form shows as it is, the ini's or a saved one, is left alone, so an
    untouched ini value doesn't become an override). Valid ones are saved
    even if others aren't. Returns ([saved keys], {key: error})."""
    known = {k for k, _d, _i, _o in settings()}
    saved, errors = [], {}
    for key, raw in values.items():
        if key not in known:
            continue
        raw = (raw or "").replace("\r\n", "\n").strip()
        current = overrides().get(key, _base_raw.get(key))
        if raw == (current or "").replace("\r\n", "\n").strip():
            continue
        error = save(key, raw, user)
        if error:
            errors[key] = error
        else:
            saved.append(key)
    return saved, errors


def _log(user, key, old, new, reset):
    log = site_settings.get_settings(LOG_GROUP)
    entries = log.get("entries", [])
    entries.insert(0, {
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "user": user.name,
        "key": key,
        "old": old,
        "new": new,
        "reset": reset,
    })
    site_settings.save_settings(LOG_GROUP, {"entries": entries[:LOG_SIZE]})


def log_entries():
    return site_settings.get_settings(LOG_GROUP).get("entries", [])
