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

"""Fix thumbnail and preview-image addresses saved with the wrong domain.

A thumbnail's address is saved with its post when it's made, built from the
site's domain (s3_public_url, docs/STORAGE.md). If the installer was run
without TIPPR_DOMAIN (or with the wrong one) the domain was the default,
tippr.local, and posts made until it was corrected have thumbnails at
https://tippr.local/media/... that no browser can load, although the files
are in the bucket under the same names. This rewrites those addresses to the
site's domain (g.domain).

The first run is a dry run: it counts the affected posts and lists some. Then:

    tippr-run scripts/fix_media_domain.py
    TIPPR_ALLOW_MUTATE=1 tippr-run scripts/fix_media_domain.py
    tippr-flush        # pages render from the cache; this empties it

Settings, in the environment:
    OLD_DOMAIN   the wrong domain (default tippr.local)
    NEW_DOMAIN   the right one (default the site's own, g.domain)
    DAYS         how far back to look (default 30)

Only the posts' thumbnail and preview-image addresses are changed. Safe to re-run.
"""

import os
import sys
from datetime import datetime, timedelta

from pylons import app_globals as g

from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2
from r2.models import Link

old = os.environ.get("OLD_DOMAIN", "tippr.local")
new = os.environ.get("NEW_DOMAIN") or g.domain
days = int(os.environ.get("DAYS", "30"))
fixing = os.environ.get("TIPPR_ALLOW_MUTATE") == "1"

if old == new:
    sys.exit("OLD_DOMAIN and NEW_DOMAIN are both %s" % new)

print("%s thumbnail and preview addresses on %s -> %s, posts of the last %d days" % (
    "Rewriting" if fixing else "Dry run (TIPPR_ALLOW_MUTATE=1 to rewrite):",
    old, new, days))

cutoff = datetime.now(g.tz) - timedelta(days=days)
query = Link._query(sort=desc("_date"), data=True)
bad = "//%s/" % old
checked = thumbs = previews = 0
for link in fetch_things2(query):
    if link._date < cutoff:
        break
    checked += 1
    changed = False

    url = getattr(link, "thumbnail_url", None) or ""
    if bad in url:
        thumbs += 1
        fixed = url.replace(bad, "//%s/" % new)
        if thumbs <= 10 or fixing:
            print("%s  thumbnail %s -> %s" % (link._fullname, url, fixed))
        if fixing:
            link.thumbnail_url = fixed
            changed = True

    # the preview image, a small record with its own address
    preview = getattr(link, "preview_object", None)
    if isinstance(preview, dict) and bad in str(preview.get("url", "")):
        previews += 1
        fixed = dict(preview, url=preview["url"].replace(bad, "//%s/" % new))
        if previews <= 10 or fixing:
            print("%s  preview %s -> %s" % (
                link._fullname, preview["url"], fixed["url"]))
        if fixing:
            link.set_preview_object(fixed)
            changed = True

    if changed:
        link._commit()

print("%d posts checked: %d thumbnails and %d preview images on %s%s" % (
    checked, thumbs, previews, old, ", rewritten" if fixing else ""))
if fixing and (thumbs or previews):
    print("Now run tippr-flush so the pages show the new addresses.")
