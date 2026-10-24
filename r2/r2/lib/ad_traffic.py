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
"""Counting ads, for /traffic/adverts and a sponsored post's traffic page.

reddit counted ad impressions and clicks from its tracking pixel's and
click tracker's logs, in its Hadoop pipeline. tippr counts them as they
happen, into the same tables, with the pageview counter
(r2.lib.traffic_counter):

- a sponsored post, when the site serves it into a listing
  (/api/request_promo): by post, and by campaign and the vault it showed in
- a click on one, at /click: the link's address goes through it, signed
  with the post's tracking name (r2.lib.promote.add_trackers), and it
  counts the click and sends the browser on
- AdSense units, as the site puts them on a page (templates/adsense.html):
  by kind of unit. What Google then shows in them, and their clicks and
  earnings, are in the AdSense account, not here.

Bots aren't counted.
"""

import hashlib
import hmac

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c
from pylons.i18n import N_

from r2.lib import traffic_counter
from r2.lib.utils import constant_time_compare

ADSENSE_PREFIX = "adsense_"
ADSENSE_UNITS = {
    "sidebar": N_("AdSense: sidebar unit"),
    "listing": N_("AdSense: in-feed units"),
    "auto": N_("AdSense: Auto ads pages"),
}


def _visitor():
    """This request's visitor key, or None for a bot."""
    user_agent = request.user_agent or ""
    if traffic_counter.is_bot(user_agent):
        return None
    user = c.user if c.user_is_loggedin else None
    return traffic_counter.visitor_key(user, request.ip, user_agent)


def split_tracking_name(tracking_name):
    """(post fullname, campaign fullname or None, vault name or "") from a
    tracking name, "fullname-campaign[-vault]"."""
    parts = tracking_name.split("-", 2)
    fullname = parts[0]
    campaign = parts[1] if len(parts) > 1 else None
    if campaign == "NO_CAMPAIGN":  # (r2.lib.promote.NO_CAMPAIGN)
        campaign = None
    vault = parts[2] if len(parts) > 2 else ""
    return fullname, campaign, vault


def _scopes(kind, target_kind, tracking_name):
    fullname, campaign, vault = split_tracking_name(tracking_name)
    scopes = [(kind, fullname)]
    if campaign:
        scopes.append((target_kind, "%s\t%s" % (campaign, vault)))
    return scopes


def count_impressions(items, vault):
    """Count the sponsored posts in items as shown (once add_trackers has
    given them their tracking names)."""
    visitor = _visitor()
    if not visitor:
        return
    scopes = []
    for item in items:
        name = getattr(item, "tracking_name", None)
        if name:
            scopes += _scopes("ad", "adtarget", name)
    if scopes:
        traffic_counter.record(scopes, visitor)


def click_hash(url, tracking_name):
    hashable = (url + tracking_name).encode("utf-8")
    secret = g.tracking_secret
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, hashable, hashlib.sha1).hexdigest()


def valid_click(url, tracking_name, observed):
    """Whether a /click's address is the one signed for this ad (so /click
    can't send people anywhere else)."""
    if not (url and tracking_name and observed):
        return False
    if not url.lower().startswith(("http://", "https://", "/")):
        return False
    return constant_time_compare(click_hash(url, tracking_name), observed)


def count_click(tracking_name):
    visitor = _visitor()
    if visitor:
        traffic_counter.record(_scopes("click", "clicktarget", tracking_name),
                               visitor)
