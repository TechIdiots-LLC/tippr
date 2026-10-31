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
"""Cleaning up posts nobody took an interest in (/admin/cleanup).

A post qualifies when it's older than its rule's age and has no comments
and no votes besides its author's own, and isn't stickied, gilded,
promoted, reported or removed by a moderator. Feed bots' posts (accounts
that post a feed, r2.lib.feeds) and members' posts have rules of their
own, each off until turned on; tippr-job-cleanup_posts runs the ones that
are on each day, at most max_per_run posts a run. /admin/cleanup also
finds posts that qualify and cleans up the ones picked.

Cleaning up a post deletes it as its author would (out of the listings,
search and its vault's stickies) and deletes its thumbnail and preview
image when no other live post uses them. Those files are named after
their content, so posts with the same image share one: a thumbnail is
kept while another post's thumbnail_url is it (an indexed lookup), a
preview while LinksByImage has another live post for it. The feed's
record of the item stays, so the feed doesn't post it again.
"""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from pylons import app_globals as g

from r2.lib.db.tdb_sql import create_table, make_metadata

GROUP = "post_cleanup"

DEFAULTS = {
    "feeds_enabled": False,
    "feeds_days": 60,
    "members_enabled": False,
    "members_days": 730,
    "max_per_run": 500,
}

KINDS = ("feeds", "members")

# posts looked at in one go, and at most in one run (most old posts with
# no votes qualify, so a run seldom gets near it)
BATCH = 500
MAX_CHECKED = 50000
# posts picked on /admin/cleanup, cleaned up in one request
MAX_SELECTED = 100

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

runs = sa.Table(
    "post_cleanup_runs", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("started", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished", sa.DateTime(timezone=True), nullable=True),
    # "schedule", or the admin who cleaned up the posts they picked
    sa.Column("trigger", sa.String, nullable=False),
    # feeds, members, or picked
    sa.Column("kind", sa.String, nullable=False),
    sa.Column("checked", sa.Integer, nullable=False, default=0),
    sa.Column("removed", sa.Integer, nullable=False, default=0),
    sa.Column("files", sa.Integer, nullable=False, default=0),
    sa.Column("error", sa.Text, nullable=True),
)

create_table(runs)

RUNS_SHOWN = 20


def _now():
    return datetime.now(timezone.utc)


def settings():
    """The rules: DEFAULTS with what /admin/cleanup saved."""
    from r2.lib import site_settings
    merged = dict(DEFAULTS)
    for name, value in site_settings.get_settings(GROUP).items():
        if name in DEFAULTS:
            merged[name] = value
    return merged


def save_settings(values):
    from r2.lib import site_settings
    site_settings.save_settings(GROUP, {name: values[name]
                                        for name in DEFAULTS
                                        if name in values})


def bot_ids():
    """The accounts that post feeds."""
    from r2.lib import feeds
    return {f["account_id"] for f in feeds.all_feeds()}


def _fails(link, vault, bots, kind):
    """Why link doesn't qualify for kind (the age and votes are the
    query's), or None when it does."""
    if link._deleted or link._spam:
        return "deleted or removed"
    if (link.author_id in bots) != (kind == "feeds"):
        return "someone else's"
    if getattr(link, "num_comments", 0):
        return "has comments"
    if link._ups > 1 or link._downs:
        return "has votes"
    if getattr(link, "gildings", 0):
        return "gilded"
    if getattr(link, "promoted", None) is not None:
        return "promoted"
    if getattr(link, "reported", 0):
        return "reported"
    if vault is not None and link._fullname in (vault.sticky_fullnames or ()):
        return "stickied"
    return None


def _candidates(kind, days, vault=None, author_ids=None, after=None):
    """A batch of old posts with no votes but their author's, oldest
    first: of the given authors (feed bots), or anyone's."""
    from r2.lib.db.operators import asc
    from r2.models import Link
    rules = [Link.c._date < _now() - timedelta(days=days),
             Link.c._ups <= 1, Link.c._downs == 0]
    if author_ids is not None:
        rules.append(Link.c.author_id == list(author_ids))
    if vault is not None:
        rules.append(Link.c.vault_id == vault._id)
    if after is not None:
        rules.append(Link.c._date > after)
    q = Link._query(*rules, sort=asc("_date"), limit=BATCH, data=True)
    return list(q)


def find(kind, days, vault=None, bot=None, limit=MAX_SELECTED,
         max_checked=MAX_CHECKED):
    """Posts that qualify for kind (feeds or members) at days old, oldest
    first: ([link, ...], how many were looked at, whether there are more
    to look at). vault and bot (an Account, feeds only) narrow it."""
    from r2.models import Vault
    bots = bot_ids()
    if kind == "feeds":
        authors = {bot._id} & bots if bot is not None else bots
        if not authors:
            return [], 0, False
    else:
        authors = None
    vaults = {}
    found, checked, after = [], 0, None
    while checked < max_checked:
        batch = _candidates(kind, days, vault, authors, after)
        if not batch:
            return found, checked, False
        after = batch[-1]._date
        missing = {l.vault_id for l in batch} - set(vaults)
        if missing:
            vaults.update(Vault._byID(missing, data=True, return_dict=True,
                                      ignore_missing=True))
        for link in batch:
            checked += 1
            if not _fails(link, vaults.get(link.vault_id), bots, kind):
                found.append(link)
                if len(found) >= limit:
                    return found, checked, True
        if len(batch) < BATCH:
            return found, checked, False
    return found, checked, True


def _purge(url):
    try:
        g.media_provider.purge(url)
        return True
    except Exception as e:
        # (gone already, or the store refused: the post is cleaned up
        # either way)
        g.log.warning("post_cleanup: couldn't delete %s: %s", url, e)
        return False


def _thumbnail_used(url):
    from r2.models import Link
    q = Link._query(Link.c.thumbnail_url == url, Link.c._spam == (True, False),
                    limit=1)
    return bool(list(q))


def _preview_used(uid):
    from r2.models import Link
    from r2.models.link import LinksByImage
    # (its removals are weakly guaranteed: the posts it lists are checked)
    id36s = list(LinksByImage.get_link_id36s(uid))
    if not id36s:
        return False
    links = Link._byID36(id36s, data=True, return_dict=False,
                         ignore_missing=True)
    return any(not l._deleted and
               (getattr(l, "preview_object", None) or {}).get("uid") == uid
               for l in links)


def clean_up(links):
    """Delete links as their authors would, then the thumbnails and
    preview images no other live post uses. Returns how many files were
    deleted."""
    from r2.lib import amqp
    from r2.lib.db import queries
    if not links:
        return 0
    files = []
    for link in links:
        thumbnail = (getattr(link, "thumbnail_url", None)
                     if link.has_thumbnail else None)
        preview = getattr(link, "preview_object", None) or {}
        files.append((link, thumbnail, preview))
        link._deleted = True
        link.cleaned_up = True
        if preview:
            # (out of LinksByImage, Link._commit)
            link.set_preview_object(None)
        link._commit()
        link.update_search_index()
        amqp.add_item("deleted_link", link._fullname)
    queries.delete(links)
    removed = 0
    for link, thumbnail, preview in files:
        if thumbnail and not _thumbnail_used(thumbnail) and _purge(thumbnail):
            removed += 1
            link.has_thumbnail = False
            link._commit()
        if (preview.get("url") and preview.get("uid") and
                not _preview_used(preview["uid"]) and _purge(preview["url"])):
            removed += 1
    g.log.info("post_cleanup: cleaned up %s (%d files)",
               " ".join(l._fullname for l in links), removed)
    return removed


def _start(trigger, kind):
    with ENGINE.begin() as conn:
        return conn.execute(runs.insert().values(
            started=_now(), trigger=trigger, kind=kind)).inserted_primary_key[0]


def _finish(run_id, checked, removed, files, error=None):
    with ENGINE.begin() as conn:
        conn.execute(runs.update().where(runs.c.id == run_id).values(
            finished=_now(), checked=checked, removed=removed, files=files,
            error=error))


def run(kind, days, limit, trigger="schedule"):
    """Clean up at most limit posts that qualify for kind, a batch at a
    time. Returns (removed, files)."""
    run_id = _start(trigger, kind)
    checked = removed = files = 0
    try:
        while removed < limit:
            found, looked, more = find(kind, days,
                                       limit=min(BATCH, limit - removed))
            checked += looked
            files += clean_up(found)
            removed += len(found)
            if not more or not found:
                break
    except Exception as e:
        _finish(run_id, checked, removed, files, error=str(e)[:500])
        raise
    _finish(run_id, checked, removed, files)
    return removed, files


def run_scheduled():
    """tippr-job-cleanup_posts: each rule that's on, with max_per_run posts
    between them."""
    rules = settings()
    left = int(rules["max_per_run"])
    for kind in KINDS:
        if not rules[kind + "_enabled"] or left <= 0:
            continue
        removed, files = run(kind, int(rules[kind + "_days"]), left)
        left -= removed
        g.log.info("post_cleanup: %s: %d posts, %d files", kind, removed,
                   files)


def clean_up_picked(fullnames, kind, days, admin):
    """The posts an admin picked on /admin/cleanup, each checked again
    (it may have had a comment or a vote since). Returns (removed,
    files)."""
    from r2.models import Link, Vault
    links = [l for l in Link._by_fullname(list(fullnames)[:MAX_SELECTED],
                                          data=True, return_dict=False,
                                          ignore_missing=True)
             if isinstance(l, Link)]
    bots = bot_ids()
    cutoff = _now() - timedelta(days=days)
    vaults = Vault._byID({l.vault_id for l in links}, data=True,
                         return_dict=True, ignore_missing=True)
    picked = [l for l in links if l._date < cutoff and
              not _fails(l, vaults.get(l.vault_id), bots, kind)]
    run_id = _start(admin.name, "picked")
    try:
        files = clean_up(picked)
    except Exception as e:
        _finish(run_id, len(links), 0, 0, error=str(e)[:500])
        raise
    _finish(run_id, len(links), len(picked), files)
    return len(picked), files


###############################################################################
# A feed deleted with its posts (/admin/feeds)
###############################################################################

# which of its posts go with it
REMOVE_QUIET = "quiet"    # the ones nobody voted on or commented on
REMOVE_ALL = "all"
REMOVE_CHOICES = (REMOVE_QUIET, REMOVE_ALL)
# posts deleted at a time: in the request that deletes the feed, then by
# tippr-job-feeds each run (finish_feed_removals) until they're gone
REMOVE_BATCH = 200


def _feed_posts_to_remove(feed):
    """The feed's posts still to delete for feed["removing"], oldest
    first."""
    from r2.lib import feeds
    from r2.models import Link, Vault
    links = []
    ids = feeds.posted_link_ids(feed["id"])
    for start in range(0, len(ids), BATCH):
        links.extend(Link._byID(ids[start:start + BATCH], data=True,
                                return_dict=False, ignore_missing=True))
    links = [l for l in links if not (l._deleted or l._spam)]
    if feed["removing"] == REMOVE_QUIET:
        vaults = Vault._byID({l.vault_id for l in links}, data=True,
                             return_dict=True, ignore_missing=True)
        links = [l for l in links if not _fails(
            l, vaults.get(l.vault_id), {l.author_id}, "feeds")]
    return sorted(links, key=lambda l: l._date)


def _go_on_removing(feed, trigger):
    """Delete the next REMOVE_BATCH of the feed's posts, and the feed once
    none are left. Returns how many are still to go."""
    from r2.lib import feeds
    links = _feed_posts_to_remove(feed)
    batch = links[:REMOVE_BATCH]
    if batch:
        run_id = _start(trigger, "feed")
        try:
            files = clean_up(batch)
        except Exception as e:
            _finish(run_id, len(links), 0, 0, error=str(e)[:500])
            raise
        _finish(run_id, len(links), len(batch), files)
    left = len(links) - len(batch)
    if not left:
        feeds.remove(feed["id"])
        g.log.info("post_cleanup: feed %s deleted with its posts (%s)",
                   feed["url"], feed["removing"])
    return left


def remove_feed(feed, which, admin):
    """Delete a feed from /admin/feeds, with its posts (which: one of
    REMOVE_CHOICES) or without (None). The posts go REMOVE_BATCH at a time;
    until they all have, the feed stays, paused and marked. Returns how
    many are still to go."""
    from r2.lib import feeds
    if which not in REMOVE_CHOICES:
        feeds.remove(feed["id"])
        return 0
    feeds.update(feed["id"], enabled=False, removing=which)
    return _go_on_removing(dict(feed, enabled=False, removing=which),
                           admin.name)


def finish_feed_removals():
    """Go on with the feeds being deleted with their posts (tippr-job-feeds,
    before it checks the feeds)."""
    from r2.lib import feeds
    for feed in feeds.all_feeds():
        if feed.get("removing"):
            _go_on_removing(feed, "schedule")


def recent_runs(n=RUNS_SHOWN):
    with ENGINE.connect() as conn:
        rows = conn.execute(sa.select(runs).order_by(runs.c.id.desc())
                            .limit(n)).mappings()
        return [dict(r) for r in rows]
