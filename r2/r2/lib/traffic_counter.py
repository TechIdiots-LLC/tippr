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
"""Counting traffic on the site itself, for the traffic pages (/traffic, a
vault's /about/traffic).

reddit filled the traffic tables (r2.models.traffic) from a Hadoop pipeline
over its tracking-pixel logs, which a self-hosted site doesn't have. Instead,
each page a person views (an HTML GET that worked, not from a bot) is
counted here, for the whole site, for its vault, and for the viewer's
language, by hour, day and month: pageviews, and unique visitors.

Counts gather in memory in each web process and are written to PostgreSQL
in one go every FLUSH_SECONDS, by a background thread with its own
database engine (the request's is traced, and its trace has ended by then),
adding to the same rows the traffic pages read. A unique visitor is counted the first time their key is seen in a
period: the key is a salted hash of their account (or, logged out, their address
and browser), so no address is stored, and keys are deleted once their period is over.
"""

import hashlib
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from pylons import app_globals as g
from sqlalchemy.dialects import postgresql

FLUSH_SECONDS = 30
MAX_PENDING = 5000          # flush sooner if this many scope-hours pile up
PRUNE_SECONDS = 3600
INTERVALS = ("hour", "day", "month")
# how long a period's visitor keys are kept after the period starts
KEEP = {"hour": timedelta(hours=2), "day": timedelta(days=2),
        "month": timedelta(days=33)}

_BOT_RE = re.compile(
    r"bot\b|bot/|spider|crawl|slurp|archiver|facebookexternalhit|"
    r"embedly|preview|feedfetcher|monitor|uptime|curl/|wget/|python-|"
    r"httpclient|okhttp|java/|go-http|libwww|headless|scrapy|tippr-feeds",
    re.I)

_lock = threading.Lock()
# (kind, key, hour) -> [pageviews, {visitor keys}]
_pending = {}
_last_flush = time.time()
_last_prune = 0.0
_tables_ready = False
_engine = None
_log = None
_METADATA = sa.MetaData()


def _setup():
    """The engine and logger the writer thread uses (made in a request,
    where g is available; the thread can't reach g)."""
    global _engine, _log
    if _engine is None:
        from r2.models.traffic import engine
        _engine = sa.create_engine(engine.url, pool_size=1, max_overflow=1,
                                   pool_pre_ping=True)
        _log = g.log
    return _engine


def _visitors_table():
    if "traffic_visitors" in _METADATA.tables:
        return _METADATA.tables["traffic_visitors"]
    return sa.Table(
        "traffic_visitors", _METADATA,
        # site, vault or lang
        sa.Column("kind", sa.String, primary_key=True),
        # the vault's name or the language ("" for the site)
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("interval", sa.String, primary_key=True),
        sa.Column("period", sa.DateTime, primary_key=True),
        sa.Column("visitor", sa.String, primary_key=True),
    )


def _ensure_tables(engine):
    global _tables_ready
    if _tables_ready:
        return
    from r2.models.traffic import (PageviewsByLanguage, PageviewsByVault,
                                   PageviewsByVaultAndPath,
                                   SitewidePageviews)
    table = _visitors_table()
    for t in (table, SitewidePageviews.__table__, PageviewsByVault.__table__,
              PageviewsByLanguage.__table__,
              PageviewsByVaultAndPath.__table__):
        t.create(bind=engine, checkfirst=True)
    _tables_ready = True


def is_bot(user_agent):
    return not user_agent or bool(_BOT_RE.search(user_agent))


def visitor_key(user, ip, user_agent):
    """A salted hash standing for one visitor (not reversible to who): their
    account, or logged out, their address and browser. (Not the loid
    cookie: a visitor's first page comes before they have one, so they'd
    count twice.)"""
    if user is not None:
        raw = "u:%s" % user._id36
    else:
        raw = "a:%s:%s" % (ip, user_agent)
    salt = g.secrets["SECRET"]
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    return hashlib.sha256(salt + raw.encode("utf-8")).hexdigest()[:20]


def _hour(now):
    return now.replace(minute=0, second=0, microsecond=0)


def period_start(hour, interval):
    if interval == "hour":
        return hour
    if interval == "day":
        return hour.replace(hour=0)
    return hour.replace(day=1, hour=0)


_flusher_pid = None


def _start_flusher():
    """A thread in this process that writes the counts every FLUSH_SECONDS,
    so a quiet process doesn't sit on them (one per process: web servers
    fork after import)."""
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
                _log.exception("traffic: flush failed")

    threading.Thread(target=run, name="traffic-flusher", daemon=True).start()


def record(scopes, visitor, now=None):
    """Count a pageview by visitor in each of scopes ([(kind, key)])."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    hour = _hour(now)
    _start_flusher()
    with _lock:
        for kind, key in scopes:
            entry = _pending.setdefault((kind, key or "", hour), [0, set()])
            entry[0] += 1
            entry[1].add(visitor)
        too_many = len(_pending) >= MAX_PENDING
    if too_many:
        flush()


def record_request(request, response, c):
    """Count this request if it's a page someone viewed (TipprController
    calls it after each request)."""
    from r2.models import FakeVault, Vault
    try:
        if request.method.upper() != "GET" or c.render_style != "html":
            return
        if (getattr(c, "is_exception_response", False) or
                getattr(response, "status_int", 200) != 200):
            return
        user_agent = request.user_agent or ""
        if is_bot(user_agent) or request.headers.get("Purpose") == "prefetch":
            return
        user = c.user if c.user_is_loggedin else None
        visitor = visitor_key(user, request.ip, user_agent)
        scopes = [("site", "")]
        site = c.site
        if isinstance(site, Vault) and not isinstance(site, FakeVault):
            scopes.append(("vault", site.name))
        lang = (c.lang or "en").split("-")[0]
        scopes.append(("lang", lang))
        # listing pages by vault ("" for the front page): what sponsored
        # posts are shown on, so the ad inventory is predicted from these
        # (r2.lib.inventory.update_prediction_data)
        routes = request.environ.get("pylons.routes_dict") or {}
        if routes.get("action_name", routes.get("action")) == "listing":
            from r2.models.vault import DefaultVault
            if isinstance(site, Vault) and not isinstance(site, FakeVault):
                scopes.append(("srpath", site.name + "-GET_listing"))
            elif isinstance(site, DefaultVault):
                scopes.append(("srpath", "-GET_listing"))
        record(scopes, visitor)
    except Exception:
        g.log.exception("traffic: couldn't count a pageview")


def flush(wait=False):
    """Write the counts gathered so far to the traffic tables, in the
    background (wait: in this thread, e.g. from a script)."""
    global _pending, _last_flush
    engine = _setup()
    with _lock:
        pending, _pending = _pending, {}
        _last_flush = time.time()
    if not pending:
        return
    if wait:
        _flush_now(engine, pending)
    else:
        threading.Thread(target=_flush_now, args=(engine, pending),
                         name="traffic-flush", daemon=True).start()


def _flush_now(engine, pending):
    try:
        _write(engine, pending)
    except Exception:
        _log.exception("traffic: couldn't write %d counts", len(pending))
    _maybe_prune(engine)


_TARGETS = {
    # kind: (table, key column or None, unique column, total column)
    "site": ("traffic_aggregate", None),
    "vault": ('"traffic_Vaults"', "vault"),
    "lang": ("traffic_lang", "lang"),
    "srpath": ("traffic_srpaths", "srpath"),
}


def _write(engine, pending):
    _ensure_tables(engine)
    visitors = _visitors_table()
    with engine.begin() as conn:
        for (kind, key, hour), (pageviews, keys) in pending.items():
            table, key_column = _TARGETS[kind]
            for interval in INTERVALS:
                period = period_start(hour, interval)
                rows = [dict(kind=kind, key=key, interval=interval,
                             period=period, visitor=v) for v in keys]
                new = 0
                if rows:
                    stmt = (postgresql.insert(visitors)
                            .values(rows).on_conflict_do_nothing()
                            .returning(visitors.c.visitor))
                    new = len(conn.execute(stmt).fetchall())
                key_cols = ("%s, " % key_column) if key_column else ""
                key_vals = ":key, " if key_column else ""
                conflict = ("%sdate, interval" % key_cols)
                conn.execute(sa.text(
                    'INSERT INTO %s (%sdate, interval, "unique", total) '
                    'VALUES (%s:date, :interval, :new, :pageviews) '
                    'ON CONFLICT (%s) DO UPDATE SET '
                    '"unique" = COALESCE(%s."unique", 0) + EXCLUDED."unique", '
                    'total = COALESCE(%s.total, 0) + EXCLUDED.total'
                    % (table, key_cols, key_vals, conflict, table, table)),
                    dict(key=key, date=period, interval=interval, new=new,
                         pageviews=pageviews))


def _maybe_prune(engine):
    global _last_prune
    if time.time() - _last_prune < PRUNE_SECONDS:
        return
    _last_prune = time.time()
    try:
        prune(engine)
    except Exception:
        _log.exception("traffic: couldn't prune visitor keys")


def prune(engine=None, now=None):
    """Delete visitor keys for periods that are over."""
    engine = engine or _setup()
    _ensure_tables(engine)
    visitors = _visitors_table()
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as conn:
        for interval, keep in KEEP.items():
            conn.execute(visitors.delete().where(
                visitors.c.interval == interval,
                visitors.c.period < now - keep))
