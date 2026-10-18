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

"""Add many feeds to /admin/feeds at once, from a list.

Each line of the list has a vault (/v/name), a feed address and, if you
like, a [prefix] for the posts' titles, separated by tabs, commas or spaces;
anything else on a line is ignored, and a line without a vault uses the
vault of the line above (so a table copied from a page or a spreadsheet
works). Lines starting with # are skipped. An address can be a site's page
instead of its feed: if the page links to its feed, that's what is added.

It only reports what it would do, unless FEEDS_ADD=1:

    sudo tippr-run /home/tippr/src/tippr/scripts/import_feeds.py
    sudo env FEEDS_ADD=1 tippr-run /home/tippr/src/tippr/scripts/import_feeds.py

Settings (environment variables):

    FEEDS_FILE      the list (default: scripts/starter_feeds.txt, feeds for
                    the vaults scripts/create_default_vaults.py makes)
    FEEDS_BOT       the account that posts them, made if it doesn't exist
                    (default: news_bot); its posts show [bot]
    FEEDS_INTERVAL  minutes between checks of each feed (default: 60)
    FEEDS_ADD=1     add them (otherwise it's a dry run); TIPPR_ALLOW_MUTATE=1
                    works too, as for the other scripts here

Safe to re-run: feeds already on a vault are left alone. Vaults must exist;
missing ones are reported, so make them and run it again. Once added, the
feeds are on /admin/feeds like any other, and tippr-job-feeds posts the
newest few items of each within 15 minutes.
"""

import os
import re
from urllib.parse import urljoin

import requests
from lxml import html

import r2
from r2.lib import feeds
from r2.lib.db.thing import NotFound
from r2.models import Vault

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(r2.__file__)))), "scripts",
    "starter_feeds.txt")
FEED_TYPES = ("application/rss+xml", "application/atom+xml",
              "application/rdf+xml")
URL_RE = re.compile(r"https?://[^\s|<>\"',]+")
VAULT_RE = re.compile(r"(?:^|[\s|,;])/?v/([A-Za-z0-9_]{2,21})\b")
PREFIX_RE = re.compile(r"(\[[^\[\]\t|]{1,38}\])")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tippr-feeds/1.0)"}


def _get(url):
    resp = requests.get(url, timeout=20, headers=HEADERS)
    resp.raise_for_status()
    return resp.url, resp.content


def resolve(url):
    """(feed address, feed title, number of items) for a feed, or for a
    page that links to one."""
    final_url, content = _get(url)
    try:
        title, items = feeds.parse(content)
        return url, title, len(items)
    except feeds.FeedError:
        pass
    try:
        doc = html.fromstring(content)
    except Exception:
        doc = None
    for link in (doc.iter("link") if doc is not None else ()):
        rel = (link.get("rel") or "").lower().split()
        kind = (link.get("type") or "").lower().split(";")[0].strip()
        if "alternate" in rel and kind in FEED_TYPES and link.get("href"):
            feed_url = urljoin(final_url, link.get("href").strip())
            title, items = feeds.parse(_get(feed_url)[1])
            return feed_url, title, len(items)
    raise feeds.FeedError("not a feed, and the page doesn't link to one")


def read_list(path):
    """[(line number, vault name, address, prefix)]"""
    entries, vault_name = [], None
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            if line.lstrip().startswith("#"):
                continue
            vault_match = VAULT_RE.search(" " + line)
            if vault_match:
                vault_name = vault_match.group(1)
            url_match = URL_RE.search(line)
            if url_match and vault_name:
                prefix = PREFIX_RE.search(line)
                entries.append((number, vault_name,
                                url_match.group(0).rstrip(".;)"),
                                prefix.group(1) if prefix else None))
            elif url_match:
                print("SKIPPED  line %-3d no vault before it" % number)
    return entries


def main():
    path = os.environ.get("FEEDS_FILE") or DEFAULT_FILE
    bot = os.environ.get("FEEDS_BOT") or "news_bot"
    interval = int(os.environ.get("FEEDS_INTERVAL") or
                   feeds.DEFAULT_INTERVAL_MINUTES)
    adding = (os.environ.get("FEEDS_ADD") in ("1", "true", "yes") or
              os.environ.get("TIPPR_ALLOW_MUTATE") == "1")
    print("%s %s as %s, every %d minutes\n" % (
        "Adding feeds from" if adding else "Dry run (FEEDS_ADD=1 to add):",
        path, bot, max(interval, feeds.MIN_INTERVAL_MINUTES)))

    account = feeds.bot_account(bot) if adding else None
    existing = {(f["vault_id"], f["url"].rstrip("/").lower())
                for f in feeds.all_feeds()}
    counts = {}
    for number, vault_name, url, prefix in read_list(path):
        try:
            vault = Vault._by_name(vault_name)
        except NotFound:
            vault = None
        try:
            feed_url, title, n = resolve(url)
        except Exception as e:
            print("FAILED   line %-3d /v/%-14s %s  (%s)"
                  % (number, vault_name, url, e))
            counts["failed"] = counts.get("failed", 0) + 1
            continue
        found = "" if feed_url == url else "  (found from %s)" % url
        if vault is None:
            print("NO VAULT line %-3d /v/%-14s %s: make the vault first"
                  % (number, vault_name, feed_url))
            counts["no vault"] = counts.get("no vault", 0) + 1
            continue
        key = (vault._id, feed_url.rstrip("/").lower())
        if key in existing:
            print("EXISTS   line %-3d /v/%-14s %s"
                  % (number, vault.name, feed_url))
            counts["already there"] = counts.get("already there", 0) + 1
            continue
        if adding:
            feeds.add(feed_url, vault, account, interval, prefix)
            existing.add(key)
        result = "added" if adding else "to add"
        print("%-8s line %-3d /v/%-14s %-12s %s  \"%s\", %d items%s"
              % (result.upper(), number, vault.name, prefix or "", feed_url,
                 title, n, found))
        counts[result] = counts.get(result, 0) + 1
    print("\n" + (", ".join("%d %s" % (n, what) for what, n in counts.items())
                  or "no feeds in the list"))


main()
