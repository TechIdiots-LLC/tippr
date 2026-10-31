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

import html
import re
from datetime import datetime, timedelta, timezone

import requests
import sqlalchemy as sa
from lxml import etree
from pylons import app_globals as g
from pylons import tmpl_context as c
from sqlalchemy.dialects import postgresql

from r2.lib.db.tdb_sql import create_table, index_str, make_metadata
from r2.lib.memoize import memoize

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
    # flags put on every post: NSFW, and the AI label (r2.lib.ai_content;
    # None leaves the posts unlabelled)
    sa.Column("over_18", sa.Boolean, nullable=False, default=False,
              server_default=sa.false()),
    sa.Column("ai_content", sa.String, nullable=True),
    # deleted with its posts, which are still going (r2.lib.post_cleanup
    # remove_feed): "quiet" (the posts nobody voted on or commented on) or
    # "all"; the feed goes once they have
    sa.Column("removing", sa.String, nullable=True),
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

# reports on the posts a feed made, by reason: which feeds get reported,
# and what for (/admin/feeds). Counted as they're made (Report.new), so
# they include reports a moderator later dismissed.
feed_reports = sa.Table(
    "feed_reports", METADATA,
    sa.Column("feed_id", sa.Integer, primary_key=True),
    sa.Column("reason", sa.String, primary_key=True),
    sa.Column("count", sa.Integer, nullable=False, default=0),
    sa.Column("last", sa.DateTime(timezone=True), nullable=False),
)

# what members made of a feed's posts (/admin/feeds): votes and comments,
# added up from the posts by tippr-job-feed_stats (recount_stats), so
# votes changed or taken back count as they stand
feed_stats = sa.Table(
    "feed_stats", METADATA,
    sa.Column("feed_id", sa.Integer, primary_key=True),
    # its posts still up (not deleted, removed or cleaned up)
    sa.Column("posts", sa.Integer, nullable=False, default=0),
    # upvotes besides the bot's own, and downvotes
    sa.Column("ups", sa.Integer, nullable=False, default=0),
    sa.Column("downs", sa.Integer, nullable=False, default=0),
    sa.Column("comments", sa.Integer, nullable=False, default=0),
    # posts with a comment or a vote (r2.lib.post_cleanup's "interest")
    sa.Column("interested", sa.Integer, nullable=False, default=0),
    sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
)

create_table(feeds)
create_table(feed_items, [index_str(feed_items, "url", "url"),
                          index_str(feed_items, "link_id", "link_id")])
create_table(feed_reports)
create_table(feed_stats)


def _add_new_columns():
    """create_table doesn't change a table that exists: add the columns
    that came after it was made."""
    if not g.db_create_tables:
        return
    try:
        have = {col["name"] for col in sa.inspect(ENGINE).get_columns("feeds")}
        with ENGINE.begin() as conn:
            if "over_18" not in have:
                conn.execute(sa.text("ALTER TABLE feeds ADD COLUMN over_18 "
                                     "boolean NOT NULL DEFAULT false"))
            if "ai_content" not in have:
                conn.execute(sa.text("ALTER TABLE feeds ADD COLUMN ai_content "
                                     "varchar"))
            if "removing" not in have:
                conn.execute(sa.text("ALTER TABLE feeds ADD COLUMN removing "
                                     "varchar"))
            # (which feed a reported post came from: count_report)
            conn.execute(sa.text("CREATE INDEX IF NOT EXISTS "
                                 "idx_link_id_feed_items ON feed_items "
                                 "(link_id)"))
    except sa.exc.SQLAlchemyError as e:
        g.log.warning("feeds: couldn't add the new columns: %s", e)


_add_new_columns()


class FeedError(Exception):
    pass


def _now():
    return datetime.now(g.tz)


###############################################################################
# Parsing
###############################################################################

def _text(el):
    return (el.text or "").strip() if el is not None else ""


_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]{0,200}>")


def _title(el):
    """An item's title as plain text. Feeds often escape their titles
    twice (The Verge's say "&amp;#8216;", which is "&#8216;" once read),
    and some put HTML in them (Atom's type="html"): decode what's left and
    drop the tags."""
    title = _text(el)
    for _ in range(3):
        decoded = html.unescape(_TAG_RE.sub("", title))
        if decoded == title:
            break
        title = decoded
    return re.sub(r"\s+", " ", title).strip()


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
                          "title": _title(_child(entry, "title"))})
    elif kind in ("rss", "RDF"):                      # RSS 2.0 / 1.0
        channel = _child(root, "channel")
        title = _text(_child(channel, "title")) if channel is not None else ""
        holder = channel if kind == "rss" else root
        for item in _children(holder, "item") if holder is not None else []:
            url = _text(_child(item, "link")) or None
            key = _text(_child(item, "guid")) or url
            items.append({"key": key, "url": url,
                          "title": _title(_child(item, "title"))})
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


@memoize("feeds.bot_ids", time=300)
def _bot_ids():
    with ENGINE.connect() as conn:
        return sorted(r[0] for r in conn.execute(
            sa.select(feeds.c.account_id).distinct()))


@memoize("feeds.bot_names", time=300)
def bot_names():
    """The names of the accounts that post feeds (for search, which
    indexes authors by name)."""
    from r2.models import Account
    ids = _bot_ids()
    if not ids:
        return []
    return sorted(a.name for a in
                  Account._byID(ids, data=True, return_dict=False))


def hides(user, link):
    """Whether the user's preference (pref_hide_feed_bots) hides this post:
    one a feed bot posted. The bots are looked up once a request, and kept
    a few minutes, so a new feed's bot can take that long to be hidden."""
    if not user or not getattr(user, "pref_hide_feed_bots", False):
        return False
    # (c gives "" for attributes that were never set)
    ids = getattr(c, "_feed_bot_ids", None)
    if not isinstance(ids, frozenset):
        ids = c._feed_bot_ids = frozenset(_bot_ids())
    return link.author_id in ids


def get_feed(feed_id):
    with ENGINE.connect() as conn:
        row = conn.execute(sa.select(feeds).where(
            feeds.c.id == feed_id)).mappings().first()
    return dict(row) if row else None


def add(url, vault, account, interval_minutes=DEFAULT_INTERVAL_MINUTES,
        title_prefix=None, over_18=False, ai_content=None):
    interval = max(MIN_INTERVAL_MINUTES, int(interval_minutes or
                                             DEFAULT_INTERVAL_MINUTES))
    with ENGINE.begin() as conn:
        result = conn.execute(feeds.insert().values(
            url=url, vault_id=vault._id, account_id=account._id,
            enabled=True, interval_minutes=interval,
            title_prefix=(title_prefix or "").strip() or None,
            over_18=bool(over_18), ai_content=ai_content or None,
            created=_now(), posted=0))
        return result.inserted_primary_key[0]


def update(feed_id, **values):
    with ENGINE.begin() as conn:
        conn.execute(feeds.update().where(feeds.c.id == feed_id).values(**values))


def remove(feed_id):
    with ENGINE.begin() as conn:
        conn.execute(feed_items.delete().where(feed_items.c.feed_id == feed_id))
        conn.execute(feed_reports.delete().where(
            feed_reports.c.feed_id == feed_id))
        conn.execute(feed_stats.delete().where(
            feed_stats.c.feed_id == feed_id))
        conn.execute(feeds.delete().where(feeds.c.id == feed_id))


def posted_link_ids(feed_id):
    """The ids of the posts the feed made."""
    with ENGINE.connect() as conn:
        return [r[0] for r in conn.execute(
            sa.select(feed_items.c.link_id)
            .where(feed_items.c.feed_id == feed_id)
            .where(feed_items.c.link_id.isnot(None)))]


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
                        sendreplies=False,
                        ai_content=feed.get("ai_content") or None)
    if feed.get("over_18") and not link.over_18:
        link.over_18 = True
        link._commit()
    queries.new_link(link)
    try:
        link.update_search_index()
    except Exception:
        g.log.exception("feeds: couldn't index %s", link._fullname)
    return link


def _mark_seen(feed_id, item, link_id=None):
    with ENGINE.begin() as conn:
        conn.execute(feed_items.insert().values(
            feed_id=feed_id, item_key=item["key"], url=item["url"],
            link_id=link_id, seen=_now()))


def _collect(feed):
    """Fetch one feed: (vault, account, the items to post oldest first,
    the feed's title). The rest of its new items (the backlog on a first
    fetch, or more than the cap) are marked seen, not posted, so older
    items don't land on top of newer ones at the next check."""
    from r2.models import Account, Vault
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
    for item in new[len(to_post):]:
        _mark_seen(feed["id"], item)
    # oldest first, so the newest ends up on top
    return vault, account, list(reversed(to_post)), title


def _interleave(batches):
    """The posting order for one run: batches is [(vault id, feed, [item])],
    and the result [(feed, item)] takes one item from each vault in turn,
    and within a vault from each of its feeds in turn, so a run doesn't put
    a block of one feed's posts together on /v/all (posts made in the same
    run rank by the order they were made in). Each feed's items keep their
    order."""
    by_vault = {}
    for vault_id, feed, items in batches:
        by_vault.setdefault(vault_id, []).append(
            [(feed, item) for item in items])

    def round_robin(queues):
        queues = [list(q) for q in queues if q]
        out = []
        while queues:
            for q in queues:
                out.append(q.pop(0))
            queues = [q for q in queues if q]
        return out

    return round_robin(round_robin(queues) for queues in by_vault.values())


def _normal_title(title):
    return re.sub(r"\W+", " ", title).strip().lower()


def _already_in_vault(vault, url):
    from r2.lib.db.thing import NotFound
    from r2.models import Link
    try:
        return bool(Link._by_url(url, vault))
    except NotFound:
        return False


def check_feeds(feed_list):
    """Fetch the feeds, then post their new items interleaved (_interleave).
    An item whose link, or title, is already in the vault (another feed of
    the same story) is marked seen instead. Returns {feed id: how many were
    posted}, and records the time and any error on each feed."""
    batches, titles, posted = [], {}, {}

    def failed(feed, e):
        if not isinstance(e, FeedError):
            g.log.exception("feeds: checking feed %s failed", feed["id"])
        update(feed["id"], last_checked=_now(), last_error=str(e)[:1000])

    for feed in feed_list:
        try:
            vault, account, items, titles[feed["id"]] = _collect(feed)
        except Exception as e:
            failed(feed, e)
            continue
        batches.append((vault._id, (feed, vault, account), items))
        posted[feed["id"]] = 0

    vault_titles = {}
    broken = set()
    for (feed, vault, account), item in _interleave(batches):
        if feed["id"] in broken:
            continue
        seen = vault_titles.setdefault(vault._id, set())
        title = _normal_title(item["title"])
        try:
            if title in seen or _already_in_vault(vault, item["url"]):
                _mark_seen(feed["id"], item)
                continue
            link = _post(feed, vault, account, item)
            seen.add(title)
            _mark_seen(feed["id"], item, link._id)
            posted[feed["id"]] += 1
        except Exception as e:
            broken.add(feed["id"])
            failed(feed, e)

    for _, (feed, _, _), _ in batches:
        if feed["id"] not in broken:
            update(feed["id"], last_checked=_now(), last_error=None,
                   posted=feed["posted"] + posted[feed["id"]],
                   feed_title=(titles[feed["id"]] or "")[:300])
    return posted


def check(feed):
    """Fetch one feed and post its new items. Returns how many were posted."""
    return check_feeds([feed]).get(feed["id"], 0)


def run_due():
    """Check every enabled feed whose interval has passed (tippr-job-feeds),
    after going on with the feeds being deleted with their posts."""
    from r2.lib import post_cleanup
    try:
        post_cleanup.finish_feed_removals()
    except Exception:
        g.log.exception("feeds: couldn't go on deleting feeds' posts")
    now = _now()
    due = []
    for feed in all_feeds():
        if not feed["enabled"]:
            continue
        last = feed["last_checked"]
        if last and now - last < timedelta(minutes=feed["interval_minutes"]):
            continue
        due.append(feed)
    by_url = {feed["id"]: feed["url"] for feed in due}
    for feed_id, posted in check_feeds(due).items():
        g.log.info("feeds: %s: %d posted", by_url[feed_id], posted)


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


###############################################################################
# Reports on feeds' posts
###############################################################################

REPORT_REASON_LENGTH = 100


def _reason(reason):
    return (reason or "").strip()[:REPORT_REASON_LENGTH] or "no reason given"


def count_report(link, reason):
    """One more report on link, if a feed posted it, under its reason (the
    rule reported, or "other" for the reporter's own words)."""
    with ENGINE.begin() as conn:
        feed_id = conn.execute(
            sa.select(feed_items.c.feed_id)
            .where(feed_items.c.link_id == link._id).limit(1)).scalar()
        if feed_id is None:
            return
        stmt = postgresql.insert(feed_reports).values(
            feed_id=feed_id, reason=_reason(reason), count=1, last=_now())
        stmt = stmt.on_conflict_do_update(
            index_elements=["feed_id", "reason"],
            set_={"count": feed_reports.c.count + 1,
                  "last": stmt.excluded.last})
        conn.execute(stmt)


def report_counts():
    """{feed id: [(reason, count), ...]}, the most reported reason first."""
    counts = {}
    with ENGINE.connect() as conn:
        rows = conn.execute(sa.select(feed_reports.c.feed_id,
                                      feed_reports.c.reason,
                                      feed_reports.c.count))
        for feed_id, reason, count in rows:
            counts.setdefault(feed_id, []).append((reason, count))
    for reasons in counts.values():
        reasons.sort(key=lambda rc: (-rc[1], rc[0]))
    return counts


def recount_reports(batch=500):
    """Count the reports on feeds' posts again from the reports themselves
    (for the reports made before feeds counted them):
      tippr-run -c 'from r2.lib import feeds; print(feeds.recount_reports())'
    Reasons given in a reporter's own words are each their own reason here
    (only new reports know they were "other")."""
    from r2.models import Account, Link
    from r2.models.report import Report
    rel = Report.rel(Account, Link)
    with ENGINE.connect() as conn:
        feed_of = dict(conn.execute(
            sa.select(feed_items.c.link_id, feed_items.c.feed_id)
            .where(feed_items.c.link_id.isnot(None))).all())
    totals = {}
    link_ids = list(feed_of)
    for start in range(0, len(link_ids), batch):
        ids = link_ids[start:start + batch]
        for report in rel._query(rel.c._thing2_id == ids, data=True):
            key = (feed_of[report._thing2_id],
                   _reason(getattr(report, "reason", None)))
            count, last = totals.get(key, (0, report._date))
            totals[key] = (count + 1, max(last, report._date))
    with ENGINE.begin() as conn:
        conn.execute(feed_reports.delete())
        if totals:
            conn.execute(feed_reports.insert(), [
                dict(feed_id=feed_id, reason=reason, count=count, last=last)
                for (feed_id, reason), (count, last) in totals.items()])
    return sum(count for count, _ in totals.values())


###############################################################################
# Votes and comments (/admin/feeds)
###############################################################################

def _add_up(totals, link):
    """Add one of a feed's posts to its totals."""
    ups = max(link._ups - 1, 0)    # (not the bot's own upvote)
    downs = link._downs
    comments = getattr(link, "num_comments", 0) or 0
    totals["posts"] += 1
    totals["ups"] += ups
    totals["downs"] += downs
    totals["comments"] += comments
    if ups or downs or comments:
        totals["interested"] += 1


def recount_stats(batch=500):
    """Add up the votes and comments on every feed's posts (still up) and
    store them for /admin/feeds; tippr-job-feed_stats does this each hour.
    Returns the number of posts counted."""
    from r2.models import Link
    with ENGINE.connect() as conn:
        feed_of = dict(conn.execute(
            sa.select(feed_items.c.link_id, feed_items.c.feed_id)
            .where(feed_items.c.link_id.isnot(None))).all())
        feed_ids = [r[0] for r in conn.execute(sa.select(feeds.c.id))]
    empty = dict(posts=0, ups=0, downs=0, comments=0, interested=0)
    totals = {feed_id: dict(empty) for feed_id in feed_ids}
    link_ids = list(feed_of)
    for start in range(0, len(link_ids), batch):
        links = Link._byID(link_ids[start:start + batch], data=True,
                           return_dict=False, ignore_missing=True)
        for link in links:
            if link._deleted or link._spam:
                continue
            feed_id = feed_of[link._id]
            if feed_id in totals:
                _add_up(totals[feed_id], link)
    now = _now()
    with ENGINE.begin() as conn:
        conn.execute(feed_stats.delete())
        if totals:
            conn.execute(feed_stats.insert(), [
                dict(t, feed_id=feed_id, updated=now)
                for feed_id, t in totals.items()])
    return sum(t["posts"] for t in totals.values())


def stats():
    """{feed id: its totals (recount_stats)}, as last added up."""
    with ENGINE.connect() as conn:
        return {row["feed_id"]: dict(row) for row in
                conn.execute(sa.select(feed_stats)).mappings()}
