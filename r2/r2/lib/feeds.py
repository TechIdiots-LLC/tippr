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
"""Feed bots (/admin/feeds): post new items from RSS or Atom feeds to vaults.

Each feed has a vault and an account that posts its items (a bot account,
named as one, e.g. "techidiots_bot"). tippr-job-feeds checks the feeds that
are due every 15 minutes and posts new items as link posts, through the same
path as a member's submission.

So a new feed doesn't flood its vault, the first fetch posts only the newest
FIRST_FETCH_POSTS items, and later fetches the newest MAX_POSTS_PER_FETCH;
the rest are marked as seen and never posted. An item is posted once: by its id (guid / Atom id),
or failing that its link.
"""

import re
from datetime import datetime, timedelta, timezone

import requests
import sqlalchemy as sa
from lxml import etree
from pylons import app_globals as g

from r2.lib.db.tdb_sql import create_table, index_str, make_metadata

FIRST_FETCH_POSTS = 3
MAX_POSTS_PER_FETCH = 5
MAX_FEED_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT = 20
MIN_INTERVAL_MINUTES = 15
DEFAULT_INTERVAL_MINUTES = 60
USER_AGENT = "tippr-feeds/1.0 (+%s)"

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

feeds = sa.Table(
    "feeds", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("url", sa.String, nullable=False),
    sa.Column("vault_id", sa.BigInteger, nullable=False),
    # the account that posts the items
    sa.Column("account_id", sa.BigInteger, nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False, default=True),
    sa.Column("interval_minutes", sa.Integer, nullable=False,
              default=DEFAULT_INTERVAL_MINUTES),
    sa.Column("title_prefix", sa.String, nullable=True),
    sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_error", sa.Text, nullable=True),
    sa.Column("posted", sa.Integer, nullable=False, default=0),
    # the feed's own title, from the last fetch
    sa.Column("feed_title", sa.String, nullable=True),
)

feed_items = sa.Table(
    "feed_items", METADATA,
    sa.Column("feed_id", sa.Integer, primary_key=True),
    sa.Column("item_key", sa.String, primary_key=True),
    sa.Column("url", sa.String, nullable=True),
    # the post made for it (None: seen on the first fetch, not posted)
    sa.Column("link_id", sa.BigInteger, nullable=True),
    sa.Column("seen", sa.DateTime(timezone=True), nullable=False),
)

create_table(feeds)
create_table(feed_items, [index_str(feed_items, "url", "url")])


class FeedError(Exception):
    pass


def _now():
    return datetime.now(g.tz)


###############################################################################
# Parsing
###############################################################################

def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(el, name):
    return [ch for ch in el if _local(ch.tag) == name]


def _child(el, name):
    found = _children(el, name)
    return found[0] if found else None


def parse(content):
    """(feed title, [item]) from RSS 2.0, RSS 1.0 or Atom; each item is a
    dict with key, title and url, newest first as the feed lists them."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True,
                             huge_tree=False, recover=True)
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as e:
        raise FeedError("not a feed tippr can read: %s" % e)
    if root is None:
        raise FeedError("the address didn't return a feed")
    kind = _local(root.tag)
    items = []
    if kind == "feed":                                # Atom
        title = _text(_child(root, "title"))
        for entry in _children(root, "entry"):
            url = None
            for link in _children(entry, "link"):
                if link.get("rel", "alternate") == "alternate" and link.get("href"):
                    url = link.get("href")
                    break
            key = _text(_child(entry, "id")) or url
            items.append({"key": key, "url": url,
                          "title": _text(_child(entry, "title"))})
    elif kind in ("rss", "RDF"):                      # RSS 2.0 / 1.0
        channel = _child(root, "channel")
        title = _text(_child(channel, "title")) if channel is not None else ""
        holder = channel if kind == "rss" else root
        for item in _children(holder, "item") if holder is not None else []:
            url = _text(_child(item, "link")) or None
            key = _text(_child(item, "guid")) or url
            items.append({"key": key, "url": url,
                          "title": _text(_child(item, "title"))})
    else:
        raise FeedError("not an RSS or Atom feed")
    items = [i for i in items if i["key"] and i["url"] and i["title"]]
    for item in items:
        item["key"], item["url"] = item["key"][:1000], item["url"][:2000]
    return title, items


def fetch(url):
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT, stream=True, headers={
            "User-Agent": USER_AGENT % g.https_endpoint})
        resp.raise_for_status()
        content = resp.raw.read(MAX_FEED_BYTES + 1, decode_content=True)
    except requests.RequestException as e:
        raise FeedError("couldn't fetch the feed: %s" % e)
    if len(content) > MAX_FEED_BYTES:
        raise FeedError("the feed is larger than 5 MB")
    return parse(content)


###############################################################################
# Feeds
###############################################################################

def all_feeds():
    with ENGINE.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            sa.select(feeds).order_by(feeds.c.id)).mappings()]
    for row in rows:
        for col in ("created", "last_checked"):
            if row[col]:
                row[col] = row[col].astimezone(timezone.utc)
    return rows


def get_feed(feed_id):
    with ENGINE.connect() as conn:
        row = conn.execute(sa.select(feeds).where(
            feeds.c.id == feed_id)).mappings().first()
    return dict(row) if row else None


def add(url, vault, account, interval_minutes=DEFAULT_INTERVAL_MINUTES,
        title_prefix=None):
    interval = max(MIN_INTERVAL_MINUTES, int(interval_minutes or
                                             DEFAULT_INTERVAL_MINUTES))
    with ENGINE.begin() as conn:
        result = conn.execute(feeds.insert().values(
            url=url, vault_id=vault._id, account_id=account._id,
            enabled=True, interval_minutes=interval,
            title_prefix=(title_prefix or "").strip() or None,
            created=_now(), posted=0))
        return result.inserted_primary_key[0]


def update(feed_id, **values):
    with ENGINE.begin() as conn:
        conn.execute(feeds.update().where(feeds.c.id == feed_id).values(**values))


def remove(feed_id):
    with ENGINE.begin() as conn:
        conn.execute(feed_items.delete().where(feed_items.c.feed_id == feed_id))
        conn.execute(feeds.delete().where(feeds.c.id == feed_id))


def _seen_keys(conn, feed_id):
    rows = conn.execute(sa.select(feed_items.c.item_key, feed_items.c.url)
                        .where(feed_items.c.feed_id == feed_id))
    keys, urls = set(), set()
    for key, url in rows:
        keys.add(key)
        if url:
            urls.add(url)
    return keys, urls


def _post(feed, vault, account, item):
    from r2.lib.db import queries
    from r2.models import Link
    title = item["title"]
    if feed.get("title_prefix"):
        title = "%s %s" % (feed["title_prefix"], title)
    title = re.sub(r"\s+", " ", title).strip()[:300]
    link = Link._submit(is_self=False, title=title, content=item["url"],
                        author=account, vault=vault, ip="0.0.0.0",
                        sendreplies=False)
    queries.new_link(link)
    try:
        link.update_search_index()
    except Exception:
        g.log.exception("feeds: couldn't index %s", link._fullname)
    return link


def check(feed):
    """Fetch one feed and post its new items. Returns how many were posted;
    records the time and any error on the feed."""
    from r2.models import Account, Vault
    try:
        title, items = fetch(feed["url"])
        vault = Vault._byID(feed["vault_id"], data=True)
        account = Account._byID(feed["account_id"], data=True)
        if account._deleted or account._banned:
            raise FeedError("the posting account is deleted or suspended")
        with ENGINE.connect() as conn:
            keys, urls = _seen_keys(conn, feed["id"])
        first_fetch = not keys
        new = []
        for item in items:
            if item["key"] not in keys and item["url"] not in urls:
                new.append(item)
                keys.add(item["key"])       # a feed that repeats an item
                urls.add(item["url"])
        to_post = new[:FIRST_FETCH_POSTS if first_fetch else MAX_POSTS_PER_FETCH]
        # oldest first, so the newest ends up on top
        posted = 0
        for item in reversed(to_post):
            link = _post(feed, vault, account, item)
            posted += 1
            with ENGINE.begin() as conn:
                conn.execute(feed_items.insert().values(
                    feed_id=feed["id"], item_key=item["key"],
                    url=item["url"], link_id=link._id, seen=_now()))
        # the rest (the feed's backlog on a first fetch, or more new items
        # than the cap): seen, not posted, so older items don't land on top
        # of newer ones at the next check
        with ENGINE.begin() as conn:
            for item in new[len(to_post):]:
                conn.execute(feed_items.insert().values(
                    feed_id=feed["id"], item_key=item["key"],
                    url=item["url"], link_id=None, seen=_now()))
        update(feed["id"], last_checked=_now(), last_error=None,
               posted=feed["posted"] + posted, feed_title=(title or "")[:300])
        return posted
    except Exception as e:
        if not isinstance(e, FeedError):
            g.log.exception("feeds: checking feed %s failed", feed["id"])
        update(feed["id"], last_checked=_now(), last_error=str(e)[:1000])
        return 0


def run_due():
    """Check every enabled feed whose interval has passed (tippr-job-feeds)."""
    now = _now()
    for feed in all_feeds():
        if not feed["enabled"]:
            continue
        last = feed["last_checked"]
        if last and now - last < timedelta(minutes=feed["interval_minutes"]):
            continue
        posted = check(feed)
        g.log.info("feeds: %s: %d posted", feed["url"], posted)


def bot_account(name):
    """The account named `name`, made if it doesn't exist (with a random
    password: it only ever posts through feeds), marked as a bot: its posts
    and comments show [bot] beside its name."""
    from r2.lib.db.thing import NotFound
    from r2.lib.utils import randstr
    from r2.models import Account
    from r2.models.account import register
    try:
        account = Account._by_name(name)
    except NotFound:
        account = register(name, randstr(32), "0.0.0.0")
    if not getattr(account, "feed_bot", False):
        account.feed_bot = True
        account._commit()
    return account
