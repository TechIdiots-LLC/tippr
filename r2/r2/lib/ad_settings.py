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
"""Google AdSense settings.

Nothing is built in: the site owner enters their own publisher and ad unit
IDs, in the ini or on /admin/ads (saved settings override the ini and apply
without a restart). Ads are off until enabled with a publisher ID.

Two ways to place ads:

- "units": tippr's slots, each an ad unit created in AdSense: one in the
  sidebar, and one in listings after every Nth post (an in-feed unit, which
  is what phones see, since the sidebar is hidden on narrow screens).
- "auto": Google's Auto ads; AdSense decides where ads go.

Ads are never shown in NSFW or quarantined vaults, on NSFW posts, in
listings that include NSFW posts, in vaults that turned ads off, or to
gold members (ad-free by default; the "hide ads" preference lets them opt
back in).
"""

import re

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

from r2.lib import site_settings

MODES = ("units", "auto")

# setting name -> ini fallback name (older ini keys keep working)
SETTINGS = {
    "adsense_enabled": "use_adsense",
    "adsense_client": "adsense_id",
    "adsense_mode": "adsense_mode",
    "adsense_sidebar_slot": "adsense_sidebar_slot",
    "adsense_listing_slot": "adsense_listing_slot",
    "adsense_listing_layout_key": "adsense_listing_layout_key",
    # night mode's own units (dark colours, set up in AdSense), used instead
    # for members with night mode on; blank: the units above
    "adsense_sidebar_slot_night": "adsense_sidebar_slot_night",
    "adsense_listing_slot_night": "adsense_listing_slot_night",
    "adsense_listing_layout_key_night": "adsense_listing_layout_key_night",
    "adsense_listing_position": "adsense_listing_position",
    "adsense_test_mode": "adsense_test_mode",
}

DEFAULT_LISTING_POSITION = 5

_client_re = re.compile(r"^(?:ca-)?(pub-\d{10,20})$")
_slot_re = re.compile(r"^\d{5,20}$")
_layout_key_re = re.compile(r"^[-+\w]{1,40}$")


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def normalize_client(value):
    """'pub-123…' or 'ca-pub-123…' -> 'ca-pub-123…'; None if invalid."""
    m = _client_re.match((value or "").strip())
    return "ca-" + m.group(1) if m else None


def valid_slot(value):
    return bool(_slot_re.match((value or "").strip()))


def valid_layout_key(value):
    return bool(_layout_key_re.match((value or "").strip()))


def ad_settings():
    """The effective settings: the ini, overridden by /admin/ads."""
    raw = {name: g.config.get(ini_name) for name, ini_name in SETTINGS.items()}
    for name, value in site_settings.get_settings("ads").items():
        if name in SETTINGS:
            raw[name] = value

    try:
        position = int(raw["adsense_listing_position"] or 0)
    except (TypeError, ValueError):
        position = 0
    mode = raw["adsense_mode"] if raw["adsense_mode"] in MODES else "units"
    return {
        "adsense_enabled": _bool(raw["adsense_enabled"] or False),
        "adsense_client": normalize_client(raw["adsense_client"]) or "",
        "adsense_mode": mode,
        "adsense_sidebar_slot": (raw["adsense_sidebar_slot"] or "").strip(),
        "adsense_listing_slot": (raw["adsense_listing_slot"] or "").strip(),
        "adsense_listing_layout_key":
            (raw["adsense_listing_layout_key"] or "").strip(),
        "adsense_sidebar_slot_night":
            (raw["adsense_sidebar_slot_night"] or "").strip(),
        "adsense_listing_slot_night":
            (raw["adsense_listing_slot_night"] or "").strip(),
        "adsense_listing_layout_key_night":
            (raw["adsense_listing_layout_key_night"] or "").strip(),
        "adsense_listing_position": position if position > 0
            else DEFAULT_LISTING_POSITION,
        "adsense_test_mode": _bool(raw["adsense_test_mode"] or False),
    }


def adsense_configured():
    settings = ad_settings()
    return settings["adsense_enabled"] and bool(settings["adsense_client"])


def ads_allowed_here(nsfw_content=False):
    """Whether this page may show ads at all (any kind)."""
    if g.disable_ads:
        return False
    if c.admin_page or (request.path or "").startswith("/admin"):
        return False  # admin pages (AdminPage, /admin/...)
    if c.user_is_loggedin and c.user.gold and c.user.pref_hide_ads:
        return False
    site = c.site
    if not getattr(site, "allow_ads", True):
        return False  # the vault turned ads off, or it's quarantined
    if getattr(site, "over_18", False) or nsfw_content:
        return False  # AdSense policy: no ads next to adult content
    return True


def page_ads():
    """What AdSense should do on this page: None (no AdSense), or the
    settings plus which slots to fill. Worked out once per request."""
    cached = getattr(c, "_page_ads", None)
    if isinstance(cached, tuple):
        return cached[0]
    result = _page_ads(nsfw_content=bool(getattr(c, "page_nsfw", False)))
    c._page_ads = (result,)
    return result


def _page_ads(nsfw_content=False):
    if not adsense_configured() or not ads_allowed_here(nsfw_content):
        return None
    settings = ad_settings()
    if c.user_is_loggedin and getattr(c.user, "pref_nightmode", False):
        # Google draws the ads, and they can't be restyled, but AdSense
        # units can have their own colours: night mode's, where set
        if valid_slot(settings["adsense_sidebar_slot_night"]):
            settings["adsense_sidebar_slot"] = settings["adsense_sidebar_slot_night"]
        if valid_slot(settings["adsense_listing_slot_night"]):
            settings["adsense_listing_slot"] = settings["adsense_listing_slot_night"]
            settings["adsense_listing_layout_key"] = (
                settings["adsense_listing_layout_key_night"])
    units = settings["adsense_mode"] == "units"
    settings["sidebar"] = units and valid_slot(settings["adsense_sidebar_slot"])
    settings["listing"] = units and valid_slot(settings["adsense_listing_slot"])
    return settings


def ads_txt():
    """The /ads.txt line authorising Google to sell this site's ads."""
    client = ad_settings()["adsense_client"]
    if not client:
        return ""
    # f08c47fec0942fa0 is Google's certification authority ID for ads.txt
    return "google.com, %s, DIRECT, f08c47fec0942fa0\n" % client[len("ca-"):]
