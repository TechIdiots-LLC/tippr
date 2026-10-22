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
"""Counting what people do on the site, for the traffic pages: sign-ups,
logins, posts, comments, votes, reports, moderator actions and the like.

The site's event calls (g.events.login_event(...) and so on, which reddit
sent to its analytics pipeline with the member's id, address and browser)
are counted here instead (CountingEventQueue), for the whole site and,
where it applies, the vault, by hour, day and month. Only the counts are
kept: nothing about who did it.

Like the pageview counts (r2.lib.traffic_counter), they gather in memory in
each web process and a background thread adds them to PostgreSQL every
FLUSH_SECONDS, so several frontends add to the same rows. Hourly counts are
kept for KEEP_HOURS, daily and monthly ones indefinitely.
"""

import os
import threading
import time
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from pylons import app_globals as g
from sqlalchemy.dialects import postgresql

FLUSH_SECONDS = 30
MAX_PENDING = 2000
INTERVALS = ("hour", "day", "month")
KEEP_HOURS = timedelta(days=31)
PRUNE_SECONDS = 3600

# what's counted, in the order the pages show it: name -> (label, scopes)
# ("site": the whole site only; "both": also each vault's own)
METRICS = [
    ("new_visitors", "new visitors", "site"),
    ("signups", "sign-ups", "site"),
    ("failed_signups", "failed sign-ups", "site"),
    ("logins", "logins", "site"),
    ("failed_logins", "failed logins", "site"),
    ("password_resets", "password resets", "site"),
    ("posts", "posts", "both"),
    ("comments", "comments", "both"),
    ("upvotes", "upvotes", "both"),
    ("downvotes", "downvotes", "both"),
    ("reports", "reports", "both"),
    ("mod_actions", "moderator actions", "both"),
    ("messages", "private messages", "site"),
    ("modmail", "moderator mail", "both"),
    ("quarantine_opt_ins", "quarantined vaults entered", "site"),
    ("blocked_actions", "blocked (muted or in a timeout)", "site"),
]
# for the public, on a vault with public traffic: not reports or moderation
PUBLIC_VAULT_METRICS = ("posts", "comments", "upvotes", "downvotes")
MOD_ACTION_PREFIX = "mod:"   # mod:removelink and the like, by type

_lock = threading.Lock()
_pending = {}
_engine = None
_log = None
_tables_ready = False
_flusher_pid = None
_last_prune = 0.0
_METADATA = sa.MetaData()

counts_table = sa.Table(
    "activity_counts", _METADATA,
    sa.Column("kind", sa.String, primary_key=True),      # site or vault
    sa.Column("key", sa.String, primary_key=True),       # the vault's name
    sa.Column("name", sa.String, primary_key=True),      # what (METRICS)
    sa.Column("interval", sa.String, primary_key=True),  # hour, day, month
    sa.Column("period", sa.DateTime, primary_key=True),
    sa.Column("count", sa.BigInteger, nullable=False),
)


def _setup():
    """The engine and logger the writer thread uses (made where g is
    available; the thread can't reach g)."""
    global _engine, _log
    if _engine is None:
        from r2.models.traffic import engine
        _engine = sa.create_engine(engine.url, pool_size=1, max_overflow=1,
                                   pool_pre_ping=True)
        _log = g.log
    return _engine


def _ensure_tables(engine):
    global _tables_ready
    if not _tables_ready:
        counts_table.create(bind=engine, checkfirst=True)
        _tables_ready = True


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def period_start(when, interval):
    hour = when.replace(minute=0, second=0, microsecond=0)
    if interval == "hour":
        return hour
    if interval == "day":
        return hour.replace(hour=0)
    return hour.replace(day=1, hour=0)


def _start_flusher():
    global _flusher_pid
    if _flusher_pid == os.getpid():
        return
    _flusher_pid = os.getpid()
    _setup()

    def run():
        while True:
            time.sleep(FLUSH_SECONDS)
            try:
                flush(wait=True)
            except Exception:
                _log.exception("activity: flush failed")

    threading.Thread(target=run, name="activity-flusher", daemon=True).start()


def count(name, vault_name=None, now=None):
    """Count one of name, for the site and (given) the vault."""
    hour = period_start(now or _now(), "hour")
    _start_flusher()
    with _lock:
        key = ("site", "", name, hour)
        _pending[key] = _pending.get(key, 0) + 1
        if vault_name:
            key = ("vault", vault_name, name, hour)
            _pending[key] = _pending.get(key, 0) + 1
        too_many = len(_pending) >= MAX_PENDING
    if too_many:
        flush()


def flush(wait=False):
    global _pending
    engine = _setup()
    with _lock:
        pending, _pending = _pending, {}
    if not pending:
        return
    if wait:
        _write(engine, pending)
    else:
        threading.Thread(target=_write, args=(engine, pending),
                         name="activity-flush", daemon=True).start()


def _write(engine, pending):
    global _last_prune
    try:
        _ensure_tables(engine)
        rows = []
        for (kind, key, name, hour), n in pending.items():
            for interval in INTERVALS:
                rows.append(dict(kind=kind, key=key, name=name,
                                 interval=interval,
                                 period=period_start(hour, interval), count=n))
        # one row per key and period (the same day from several hours)
        merged = {}
        for row in rows:
            k = (row["kind"], row["key"], row["name"], row["interval"],
                 row["period"])
            if k in merged:
                merged[k]["count"] += row["count"]
            else:
                merged[k] = row
        stmt = postgresql.insert(counts_table).values(list(merged.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=["kind", "key", "name", "interval", "period"],
            set_={"count": counts_table.c.count + stmt.excluded.count})
        with engine.begin() as conn:
            conn.execute(stmt)
            if time.time() - _last_prune > PRUNE_SECONDS:
                _last_prune = time.time()
                conn.execute(counts_table.delete().where(
                    counts_table.c.interval == "hour",
                    counts_table.c.period < _now() - KEEP_HOURS))
    except Exception:
        (_log or g.log).exception("activity: couldn't write %d counts",
                                  len(pending))


###############################################################################
# Reading, for the traffic pages
###############################################################################

def totals(kind="site", key="", since=None, names=None):
    """{name: count} since (a datetime), from the hourly counts (so up to
    KEEP_HOURS back)."""
    engine = _setup()
    _ensure_tables(engine)
    t = counts_table
    query = (sa.select(t.c.name, sa.func.sum(t.c.count))
             .where(t.c.kind == kind, t.c.key == (key or ""),
                    t.c.interval == "hour", t.c.period >= since)
             .group_by(t.c.name))
    if names:
        query = query.where(t.c.name.in_(list(names)))
    with engine.connect() as conn:
        return {name: int(n) for name, n in conn.execute(query)}


def history(kind="site", key="", interval="day", periods=30, names=None):
    """[(period, {name: count})], oldest first, for the last periods
    intervals (each one there, with zeros where nothing happened)."""
    engine = _setup()
    _ensure_tables(engine)
    t = counts_table
    end = period_start(_now(), interval)
    if interval == "hour":
        starts = [end - timedelta(hours=i) for i in range(periods)]
    elif interval == "day":
        starts = [end - timedelta(days=i) for i in range(periods)]
    else:
        starts, month = [], end
        for _ in range(periods):
            starts.append(month)
            month = (month - timedelta(days=1)).replace(day=1)
    starts.reverse()
    query = (sa.select(t.c.period, t.c.name, t.c.count)
             .where(t.c.kind == kind, t.c.key == (key or ""),
                    t.c.interval == interval, t.c.period >= starts[0]))
    if names:
        query = query.where(t.c.name.in_(list(names)))
    by_period = {s: {} for s in starts}
    with engine.connect() as conn:
        for period, name, n in conn.execute(query):
            if period in by_period:
                by_period[period][name] = int(n)
    return [(s, by_period[s]) for s in starts]


###############################################################################
# The events
###############################################################################

def _vault_name(vault_id):
    if not vault_id:
        return None
    from r2.models import Vault
    try:
        return Vault._byID(vault_id, data=True, stale=True).name
    except Exception:
        return None


def _vault_of(thing):
    return _vault_name(getattr(thing, "vault_id", None))


def count_event(event, args, kwargs):
    """Count one of the site's event calls (g.events.<event>(...))."""
    def arg(index, name):
        if name in kwargs:
            return kwargs[name]
        return args[index] if len(args) > index else None

    if event == "loid_event":
        if arg(1, "action_name") == "create_loid":
            count("new_visitors")
    elif event == "login_event":
        action, error = arg(0, "action_name"), arg(1, "error_msg")
        if action == "login_attempt":
            count("logins" if error is None else "failed_logins")
        elif action == "register_attempt":
            count("signups" if error is None else "failed_signups")
        elif action == "password_reset" and error is None:
            count("password_resets")
    elif event == "vote_event":
        vote = arg(0, "vote")
        if getattr(vote, "is_upvote", False):
            count("upvotes", _vault_of(getattr(vote, "thing", None)))
        elif getattr(vote, "is_downvote", False):
            count("downvotes", _vault_of(getattr(vote, "thing", None)))
    elif event == "submit_event":
        count("posts", _vault_of(arg(0, "new_post")))
    elif event == "comment_event":
        count("comments", _vault_of(arg(0, "new_comment")))
    elif event == "report_event":
        vault = arg(2, "vault")
        count("reports", getattr(vault, "name", None))
    elif event == "mod_event":
        modaction, vault = arg(0, "modaction"), arg(1, "vault")
        vault_name = getattr(vault, "name", None)
        count("mod_actions", vault_name)
        action = getattr(modaction, "action", None)
        if action:
            count(MOD_ACTION_PREFIX + action, vault_name)
    elif event == "message_event":
        if arg(1, "event_type") in (None, "ss.send_message"):
            count("messages")
    elif event == "modmail_event":
        count("modmail", _vault_of(arg(0, "message")))
    elif event == "quarantine_event":
        if arg(0, "event_type") == "quarantine_opt_in":
            count("quarantine_opt_ins")
    elif event in ("muted_forbidden_event", "timeout_forbidden_event"):
        count("blocked_actions")


class CountingEventQueue:
    """g.events: counts each event (count_event), and passes it on to an
    event collector service if the site has one (events_collector_url,
    r2.lib.eventcollector.EventQueue)."""

    def __init__(self, forward=None):
        self._forward = forward

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        forward = getattr(self._forward, name) if self._forward else None

        def event(*args, **kwargs):
            if name.endswith("_event"):
                try:
                    count_event(name, args, kwargs)
                except Exception:
                    g.log.exception("activity: couldn't count %s", name)
            if forward:
                return forward(*args, **kwargs)
            return None
        return event
