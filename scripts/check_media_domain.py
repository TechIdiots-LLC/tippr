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

"""Look for media addresses saved with the wrong domain, of every kind.

scripts/fix_media_domain.py repairs the posts' thumbnail addresses. Media is
saved with an address built from the site's domain, so everything uploaded
while the installer had the wrong one (default tippr.local) has the wrong
address. This only reads, and reports by kind what it finds:

  - posts: thumbnail, preview image, mobile ad image
  - vaults: header, icon, banner, stylesheet, and the images the stylesheet uses
  - the site's logo, favicon and share image
  - OAuth apps' icons

    tippr-run scripts/check_media_domain.py

Settings, in the environment:
    OLD_DOMAIN   the wrong domain (default tippr.local)
    DAYS         how far back to look at posts (default 30)

Each kind is checked on its own, so one that can't be read is reported and
the rest still run.
"""

import os
from datetime import datetime, timedelta

from pylons import app_globals as g

from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2

old = os.environ.get("OLD_DOMAIN", "tippr.local")
days = int(os.environ.get("DAYS", "30"))
needle = "//%s/" % old
SHOW = 5

found = {}


def hit(kind, where, value):
    """Count a value if it has the wrong domain in it."""
    if value and needle in str(value):
        found.setdefault(kind, []).append((where, str(value)[:140]))


def section(kind, function):
    try:
        function()
    except Exception as e:
        print("%-24s couldn't be checked: %s: %s" % (kind, type(e).__name__, e))


def posts():
    from r2.models import Link
    cutoff = datetime.now(g.tz) - timedelta(days=days)
    n = 0
    for link in fetch_things2(Link._query(sort=desc("_date"), data=True)):
        if link._date < cutoff:
            break
        n += 1
        hit("post thumbnails", link._fullname, getattr(link, "thumbnail_url", None))
        hit("post preview images", link._fullname, getattr(link, "preview_object", None))
        hit("post mobile ad images", link._fullname, getattr(link, "mobile_ad_url", None))
    print("%-24s %d posts of the last %d days looked at" % ("posts", n, days))


def vaults():
    from r2.models import Vault
    from r2.models.wiki import ImagesByWikiPage
    n = 0
    for vault in fetch_things2(Vault._query(sort=desc("_date"), data=True)):
        n += 1
        for attr in ("header", "icon_img", "banner_img", "stylesheet_url",
                     "stylesheet_url_http", "stylesheet_url_https"):
            hit("vault " + attr, vault.name, getattr(vault, attr, None))
        try:
            images = ImagesByWikiPage.get_images(vault, "config/stylesheet")
        except Exception:
            images = {}
        for name, url in images.items():
            hit("vault stylesheet images", "%s/%s" % (vault.name, name), url)
    print("%-24s %d vaults looked at" % ("vaults", n))


def site_images():
    for setting in ("site_logo", "site_favicon", "share_image"):
        hit("site images", setting, getattr(g, setting, None))
    print("%-24s logo, favicon and share image looked at" % "site")


def oauth_icons():
    from r2.models.token import OAuth2Client
    n = 0
    for client in OAuth2Client._all():
        n += 1
        hit("oauth app icons", client._id, getattr(client, "icon_url", None))
    print("%-24s %d apps looked at" % ("oauth apps", n))


print("Looking for %s in media addresses (nothing is changed)" % needle)
section("posts", posts)
section("vaults", vaults)
section("site images", site_images)
section("oauth apps", oauth_icons)

print()
if not found:
    print("None on %s." % old)
for kind, items in sorted(found.items()):
    print("%-26s %d" % (kind, len(items)))
    for where, value in items[:SHOW]:
        print("    %s  %s" % (where, value))
    if len(items) > SHOW:
        print("    ... and %d more" % (len(items) - SHOW))
