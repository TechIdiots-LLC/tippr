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
"""Complete sitemaps, for a site too big for the recent ones.

With "every post" chosen on /admin/site, tippr-job-sitemaps runs build()
each day: every listable vault and post (r2.lib.sitemaps.live's rules) goes
into sitemaps of up to 50,000 addresses each (the protocol's limit),
vaults-1, vaults-2, ... and posts-1, posts-2, ..., stored compressed in the
permacache (Cassandra, so every web server has them). /sitemap.xml then
lists those and /sitemaps/<name>.xml serves each.
"""

import time
import zlib
from datetime import datetime, timezone

from pylons import app_globals as g

from r2.lib.sitemaps import live
from r2.lib.utils import in_chunks

URLS_PER_SITEMAP = 50000
INDEX_KEY = "sitemap-complete-index"


def _key(name):
    return "sitemap-complete-" + name


def enabled():
    from r2.lib import site_info
    return site_info.sitemaps_complete()


def _index():
    return g.permacache.get(INDEX_KEY) or {}


def built():
    """When the last build finished (epoch seconds), or None."""
    return _index().get("built")


def part_names():
    return [name for name, count in _index().get("parts", [])]


def status():
    """For /admin/site: {"built": datetime or None, "urls": int, "parts": int}."""
    index = _index()
    stamp = index.get("built")
    return {
        "built": (datetime.fromtimestamp(stamp, timezone.utc)
                  if stamp else None),
        "urls": sum(count for name, count in index.get("parts", [])),
        "parts": len(index.get("parts", [])),
    }


def get(name):
    """The XML for "index" or a part, or None if there isn't one built."""
    index = _index()
    if not index.get("built"):
        return None
    if name == "index":
        lastmod = datetime.fromtimestamp(index["built"], timezone.utc)
        return live.sitemap_index((part, lastmod)
                                  for part, count in index["parts"])
    if name not in {part for part, count in index["parts"]}:
        return None
    data = g.permacache.get(_key(name))
    return zlib.decompress(data).decode("utf-8") if data else None


def build():
    """Write the sitemaps, then swap the index over to them and remove
    the parts the new set no longer has."""
    started = time.time()
    parts = []
    for kind, entries in (("vaults", live.listable_vaults()),
                          ("posts", live.listable_posts())):
        for i, chunk in enumerate(in_chunks(entries, URLS_PER_SITEMAP), 1):
            name = "%s-%d" % (kind, i)
            xml = live.urlset(chunk)
            g.permacache.set(_key(name), zlib.compress(xml.encode("utf-8")))
            parts.append((name, len(chunk)))
            g.log.info("sitemaps: %s, %d addresses", name, len(chunk))
    old = part_names()
    g.permacache.set(INDEX_KEY, {"built": time.time(), "parts": parts})
    for name in set(old) - {name for name, count in parts}:
        g.permacache.delete(_key(name))
    g.log.info("sitemaps: %d sitemaps, %d addresses, in %ds", len(parts),
               sum(count for name, count in parts), time.time() - started)


def build_if_enabled():
    """What tippr-job-sitemaps runs: build when the site uses them."""
    if enabled():
        build()
