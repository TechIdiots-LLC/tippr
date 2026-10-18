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

reddit's sitemaps (the rest of this package) were built offline and
uploaded to S3. A self-hosted site has neither, so these are made on
request and cached for an hour:

  /sitemap.xml           the index, pointing at the two below
  /sitemaps/vaults.xml   public vaults, most subscribed first
  /sitemaps/posts.xml    the newest posts in public vaults

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


def _urlset(entries):
    """entries: (path, lastmod datetime or None)"""
    urlset = etree.Element("urlset", xmlns=SITEMAP_NAMESPACE)
    for path, lastmod in entries:
        url = etree.SubElement(urlset, "url")
        etree.SubElement(url, "loc").text = _url(path)
        if lastmod:
            etree.SubElement(url, "lastmod").text = lastmod.strftime("%Y-%m-%d")
    return _xml(urlset)


def _index():
    root = etree.Element("sitemapindex", xmlns=SITEMAP_NAMESPACE)
    for part in PARTS:
        sitemap = etree.SubElement(root, "sitemap")
        etree.SubElement(sitemap, "loc").text = _url(
            "/sitemaps/%s.xml" % part)
    return _xml(root)


def _listable(vault):
    return (vault.type in ("public", "restricted", "archived") and
            not vault._spam and not vault.over_18 and
            not getattr(vault, "quarantine", False))


def _vaults():
    from r2.models import Vault
    query = Vault._query(Vault.c.type == ("public", "restricted", "archived"),
                         Vault.c._spam == False,
                         sort=(desc("_downs"), desc("_ups")),
                         data=True)
    entries = []
    for vault in fetch_things2(query, chunk_size=1000):
        if not _listable(vault):
            continue
        entries.append(("/v/%s/" % vault.name, None))
        if len(entries) >= MAX_VAULTS:
            break
    return _urlset(entries)


def _posts():
    from r2.models import Link, Vault
    query = Link._query(Link.c._spam == False,
                        Link.c._deleted == False,
                        sort=desc("_date"),
                        limit=MAX_POSTS * 2,
                        data=True)
    links = [link for link in query
             if link.promoted is None and not link.over_18]
    vaults = Vault._byID({link.vault_id for link in links},
                         data=True, return_dict=True)
    entries = []
    for link in links:
        vault = vaults.get(link.vault_id)
        if not vault or not _listable(vault):
            continue
        entries.append((link.make_permalink(vault), link._date))
        if len(entries) >= MAX_POSTS:
            break
    return _urlset(entries)


BUILDERS = {"index": _index, "vaults": _vaults, "posts": _posts}


def sitemap(name):
    """The XML for "index" or one of PARTS (cached)."""
    key = "sitemap-live-" + name
    xml = g.gencache.get(key)
    if xml is None:
        xml = BUILDERS[name]()
        g.gencache.set(key, xml, time=CACHE_SECONDS)
    return xml
