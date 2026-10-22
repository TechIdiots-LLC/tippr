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
like, a [prefix] for the posts' titles, separated by tabs, commas or spaces.
A line can also mark the feed's posts: "nsfw" marks them NSFW, and
"ai:human", "ai:assisted" or "ai:generated" gives them that AI label (it
must be one the vault accepts). Anything else on a line is ignored, and a line without a vault uses the
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
    FEEDS_STARTER   the installer's starter feeds (TIPPR_STARTER_FEEDS):
                    1 or 0 turns them on or off for the site (remembered),
                    auto keeps the remembered choice (first time: yes on a
                    new site, or one that has them already). Adds only the
                    feeds new to the list since the last run, so a feed an
                    admin removed isn't added back (r2.lib.starter_content).
    FEEDS_SYNC=1    also remove FEEDS_BOT's feeds that aren't in the list (or
                    are listed for another vault), so its feeds match the
                    list after reorganizing it. Feeds still in the list are
                    left alone, so they don't post their latest items again;
                    removed feeds' posts stay.

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
from r2.lib import ai_content, feeds, starter_content
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
NSFW_RE = re.compile(r"(?:^|[\s|,;])nsfw(?=$|[\s|,;])", re.I)
AI_RE = re.compile(r"(?:^|[\s|,;])ai[:=](%s)(?=$|[\s|,;])"
                   % "|".join(ai_content.LABELS), re.I)
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
    """[(line number, vault name, address, prefix, nsfw, AI label)]"""
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
                rest = line.replace(url_match.group(0), " ")
                ai_label = AI_RE.search(rest)
                entries.append((number, vault_name,
                                url_match.group(0).rstrip(".;)"),
                                prefix.group(1) if prefix else None,
                                bool(NSFW_RE.search(rest)),
                                ai_label.group(1).lower() if ai_label else None))
            elif url_match:
                print("SKIPPED  line %-3d no vault before it" % number)
    return entries


def sync(bot, wanted, removing, counts):
    """Remove bot's feeds that aren't in wanted ((vault id, address))."""
    from r2.models import Account
    try:
        account = Account._by_name(bot)
    except NotFound:
        return
    names = {}
    for f in feeds.all_feeds():
        if f["account_id"] != account._id:
            continue
        if (f["vault_id"], f["url"].rstrip("/").lower()) in wanted:
            continue
        if f["vault_id"] not in names:
            try:
                names[f["vault_id"]] = Vault._byID(f["vault_id"], data=True).name
            except NotFound:
                names[f["vault_id"]] = "?"
        if removing:
            feeds.remove(f["id"])
        result = "removed" if removing else "to remove"
        print("%-8s          /v/%-14s %s  (not in the list)"
              % (result.upper(), names[f["vault_id"]], f["url"]))
        counts[result] = counts.get(result, 0) + 1


def bot_feeds(bot):
    from r2.models import Account
    try:
        account = Account._by_name(bot)
    except NotFound:
        return []
    return [f for f in feeds.all_feeds() if f["account_id"] == account._id]


def starter_entries(choice, bot, entries):
    """The installer's starter feeds (FEEDS_STARTER): whether to add them
    (1, 0, or auto: remembered, else yes on a new site or one that has
    them already), and the list entries not offered to this site before
    (r2.lib.starter_content), so a feed an admin removed isn't added back.
    None: don't add any."""
    if choice in ("1", "0"):
        on = choice == "1"
        starter_content.set_feeds_on(on)
    else:
        on = starter_content.feeds_on()
        if on is None:
            on = starter_content.new_site() or bool(bot_feeds(bot))
            starter_content.set_feeds_on(on)
    if not on:
        print("Starter feeds are off for this site (TIPPR_STARTER_FEEDS=1 "
              "turns them on)")
        return None
    offered = starter_content.offered_feeds()
    if offered is None:
        # a site from before this was remembered: what its vaults with
        # starter feeds have is the admin's choice; vaults without any
        # get theirs
        have = {f["vault_id"] for f in bot_feeds(bot)}
        names = {}
        for _number, vault_name, url, *_flags in entries:
            if vault_name not in names:
                try:
                    names[vault_name] = Vault._by_name(vault_name)._id
                except NotFound:
                    names[vault_name] = None
        offered = {starter_content.feed_key(vault_name, url)
                   for _number, vault_name, url, *_flags in entries
                   if names[vault_name] in have}
        starter_content.record_feeds(offered)
    new = [e for e in entries
           if starter_content.feed_key(e[1], e[2]) not in offered]
    print("Starter feeds: %d in the list, %d not offered to this site before\n"
          % (len(entries), len(new)))
    return new


def main():
    path = os.environ.get("FEEDS_FILE") or DEFAULT_FILE
    bot = os.environ.get("FEEDS_BOT") or "news_bot"
    starter = os.environ.get("FEEDS_STARTER")
    interval = int(os.environ.get("FEEDS_INTERVAL") or
                   feeds.DEFAULT_INTERVAL_MINUTES)
    adding = (os.environ.get("FEEDS_ADD") in ("1", "true", "yes") or
              os.environ.get("TIPPR_ALLOW_MUTATE") == "1" or bool(starter))
    syncing = (os.environ.get("FEEDS_SYNC") in ("1", "true", "yes") and
               not starter)
    entries = read_list(path)
    if starter:
        entries = starter_entries(starter, bot, entries)
        if entries is None:
            return
    # starter feeds handled this run (added, or there already)
    done = []
    print("%s %s as %s, every %d minutes\n" % (
        "Adding feeds from" if adding else "Dry run (FEEDS_ADD=1 to add):",
        path, bot, max(interval, feeds.MIN_INTERVAL_MINUTES)))

    account = feeds.bot_account(bot) if adding else None
    existing = {(f["vault_id"], f["url"].rstrip("/").lower())
                for f in feeds.all_feeds()}
    counts = {}
    # (vault id, feed address) of everything in the list, for FEEDS_SYNC
    wanted = set()
    for number, vault_name, url, prefix, over_18, ai_label in entries:
        try:
            vault = Vault._by_name(vault_name)
        except NotFound:
            vault = None
        if vault is not None and (vault._id, url.rstrip("/").lower()) in existing:
            # there already: no need to fetch it
            print("EXISTS   line %-3d /v/%-14s %s" % (number, vault.name, url))
            counts["already there"] = counts.get("already there", 0) + 1
            wanted.add((vault._id, url.rstrip("/").lower()))
            done.append(starter_content.feed_key(vault_name, url))
            continue
        try:
            feed_url, title, n = resolve(url)
        except Exception as e:
            print("FAILED   line %-3d /v/%-14s %s  (%s)"
                  % (number, vault_name, url, e))
            counts["failed"] = counts.get("failed", 0) + 1
            # (an existing feed that's down today isn't removed)
            if vault is not None:
                wanted.add((vault._id, url.rstrip("/").lower()))
            continue
        found = "" if feed_url == url else "  (found from %s)" % url
        if vault is None:
            print("NO VAULT line %-3d /v/%-14s %s: make the vault first"
                  % (number, vault_name, feed_url))
            counts["no vault"] = counts.get("no vault", 0) + 1
            continue
        key = (vault._id, feed_url.rstrip("/").lower())
        wanted.add(key)
        wanted.add((vault._id, url.rstrip("/").lower()))
        if key in existing:
            print("EXISTS   line %-3d /v/%-14s %s"
                  % (number, vault.name, feed_url))
            counts["already there"] = counts.get("already there", 0) + 1
            done.append(starter_content.feed_key(vault_name, url))
            continue
        if ai_label and ai_label not in ai_content.allowed_labels(vault.ai_policy):
            print("REFUSED  line %-3d /v/%-14s %s: the vault doesn't accept "
                  "ai:%s posts" % (number, vault.name, feed_url, ai_label))
            counts["refused"] = counts.get("refused", 0) + 1
            continue
        if adding:
            feeds.add(feed_url, vault, account, interval, prefix,
                      over_18=over_18, ai_content=ai_label)
            existing.add(key)
            done.append(starter_content.feed_key(vault_name, url))
        result = "added" if adding else "to add"
        flags = "".join(("  nsfw" if over_18 else "",
                         "  ai:%s" % ai_label if ai_label else ""))
        print("%-8s line %-3d /v/%-14s %-12s %s  \"%s\", %d items%s%s"
              % (result.upper(), number, vault.name, prefix or "", feed_url,
                 title, n, flags, found))
        counts[result] = counts.get(result, 0) + 1

    if syncing:
        sync(bot, wanted, adding, counts)
    if starter:
        starter_content.record_feeds(done)

    print("\n" + (", ".join("%d %s" % (n, what) for what, n in counts.items())
                  or "no feeds in the list"))


main()
