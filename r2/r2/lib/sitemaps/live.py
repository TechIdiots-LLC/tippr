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
"""Sitemaps served by the site itself (/sitemap.xml).

By default ("recent" on /admin/site) they're made on request and cached
for an hour:

  /sitemap.xml           the index, pointing at the two below
  /sitemaps/vaults.xml   public vaults, most subscribed first
  /sitemaps/posts.xml    the newest posts in public vaults

Set to "every post", the site serves the complete sitemaps that
tippr-job-sitemaps builds each day instead (r2.lib.sitemaps.complete),
falling back to these until the first build is done.

Only what a logged-out visitor can see is listed: no private or quarantined
vaults, nothing marked NSFW, spam or deleted, and no ads.
"""

from lxml import etree
from pylons import app_globals as g

from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2

SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
PARTS = ("vaults", "posts")
MAX_VAULTS = 50000          # the protocol's limit per file
MAX_POSTS = 10000
CACHE_SECONDS = 3600


def _url(path):
    return g.https_endpoint.rstrip("/") + path


def _xml(root):
    return etree.tostring(root, xml_declaration=True,
                          encoding="UTF-8").decode("utf-8")


def urlset(entries):
    """A sitemap of entries: (path, lastmod datetime or None)."""
    urlset = etree.Element("urlset", xmlns=SITEMAP_NAMESPACE)
    for path, lastmod in entries:
        url = etree.SubElement(urlset, "url")
        etree.SubElement(url, "loc").text = _url(path)
        if lastmod:
            etree.SubElement(url, "lastmod").text = lastmod.strftime("%Y-%m-%d")
    return _xml(urlset)


def sitemap_index(parts):
    """A sitemap index of parts: (name, lastmod datetime or None)."""
    root = etree.Element("sitemapindex", xmlns=SITEMAP_NAMESPACE)
    for name, lastmod in parts:
        sitemap = etree.SubElement(root, "sitemap")
        etree.SubElement(sitemap, "loc").text = _url(
            "/sitemaps/%s.xml" % name)
        if lastmod:
            etree.SubElement(sitemap, "lastmod").text = lastmod.strftime(
                "%Y-%m-%d")
    return _xml(root)


def _listable(vault):
    return (vault.type in ("public", "restricted", "archived") and
            not vault._spam and not vault.over_18 and
            not getattr(vault, "quarantine", False))


def listable_vaults():
    """(path, None) for each listable vault, most subscribed first."""
    from r2.models import Vault
    query = Vault._query(Vault.c.type == ("public", "restricted", "archived"),
                         Vault.c._spam == False,
                         sort=(desc("_downs"), desc("_ups")),
                         data=True)
    for vault in fetch_things2(query, chunk_size=1000):
        if _listable(vault):
            yield ("/v/%s/" % vault.name, None)


def listable_posts():
    """(permalink, date) for each listable post, newest first."""
    from r2.models import Link, Vault
    query = Link._query(Link.c._spam == False,
                        Link.c._deleted == False,
                        sort=desc("_date"),
                        data=True)
    for links in fetch_things2(query, chunk_size=1000, chunks=True):
        links = [link for link in links
                 if link.promoted is None and not link.over_18]
        vaults = Vault._byID({link.vault_id for link in links},
                             data=True, return_dict=True)
        for link in links:
            vault = vaults.get(link.vault_id)
            if vault and _listable(vault):
                yield (link.make_permalink(vault), link._date)


def _first(entries, count):
    for i, entry in enumerate(entries):
        if i >= count:
            break
        yield entry


BUILDERS = {
    "index": lambda: sitemap_index((part, None) for part in PARTS),
    "vaults": lambda: urlset(_first(listable_vaults(), MAX_VAULTS)),
    "posts": lambda: urlset(_first(listable_posts(), MAX_POSTS)),
}


def exists(name):
    """Whether /sitemaps/<name>.xml (or the index) is there to serve."""
    from r2.lib.sitemaps import complete
    if complete.enabled() and complete.built():
        return name == "index" or name in complete.part_names()
    return name == "index" or name in PARTS


def sitemap(name):
    """The XML for "index" or one of the parts."""
    from r2.lib.sitemaps import complete
    if complete.enabled():
        xml = complete.get(name)
        if xml is not None:
            return xml
    key = "sitemap-live-" + name
    xml = g.gencache.get(key)
    if xml is None:
        xml = BUILDERS[name]()
        g.gencache.set(key, xml, time=CACHE_SECONDS)
    return xml
