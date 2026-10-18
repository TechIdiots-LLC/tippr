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
"""CleanTalk statistics and account status for /admin/antispam.

Every spam check (r2.lib.antispam._cleantalk) is recorded here: when, which
check, how long CleanTalk took and what it said (allow, spam or error). The
page shows the last check and the last 7 days; rows older than 30 days are
removed. The account status (paid until, trial, the account's email as
CleanTalk shows it) comes from CleanTalk's key check, cached for 10 minutes.
"""

from datetime import datetime, timedelta, timezone

import requests
import sqlalchemy as sa
from pylons import app_globals as g

from r2.lib.db.tdb_sql import create_table, index_str, make_metadata

KEEP_DAYS = 30
SUMMARY_DAYS = 7
ACCOUNT_CACHE_SECONDS = 600

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

requests_table = sa.Table(
    "cleantalk_requests", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("time", sa.DateTime(timezone=True), nullable=False),
    # check_newuser, check_message
    sa.Column("method", sa.String, nullable=False),
    # allow, spam, error
    sa.Column("outcome", sa.String, nullable=False),
    sa.Column("seconds", sa.Float, nullable=True),
)
create_table(requests_table, [index_str(requests_table, "time", "time")])


def record(method, outcome, seconds=None):
    """Note one check. Never raises: statistics mustn't get in the way of
    the check itself."""
    try:
        with ENGINE.begin() as conn:
            conn.execute(requests_table.insert().values(
                time=datetime.now(g.tz), method=method, outcome=outcome,
                seconds=seconds))
    except Exception:
        g.log.exception("cleantalk_stats: couldn't record a check")


def summary():
    """What /admin/antispam shows: the last check, and for the last 7 days
    the number of checks by outcome and the average response time."""
    now = datetime.now(g.tz)
    since = now - timedelta(days=SUMMARY_DAYS)
    with ENGINE.begin() as conn:
        conn.execute(requests_table.delete().where(
            requests_table.c.time < now - timedelta(days=KEEP_DAYS)))
        last = conn.execute(sa.select(requests_table)
                            .order_by(requests_table.c.time.desc())
                            .limit(1)).mappings().first()
        by_outcome = dict(conn.execute(
            sa.select(requests_table.c.outcome, sa.func.count())
            .where(requests_table.c.time >= since)
            .group_by(requests_table.c.outcome)).all())
        by_method = dict(conn.execute(
            sa.select(requests_table.c.method, sa.func.count())
            .where(requests_table.c.time >= since,
                   requests_table.c.outcome == "spam")
            .group_by(requests_table.c.method)).all())
        average = conn.execute(
            sa.select(sa.func.avg(requests_table.c.seconds))
            .where(requests_table.c.time >= since,
                   requests_table.c.outcome != "error")).scalar()
    if last:
        # PostgreSQL hands times back in the server's zone; pages say UTC
        last = dict(last)
        last["time"] = last["time"].astimezone(timezone.utc)
    return {
        "last": last,
        "days": SUMMARY_DAYS,
        "checks": sum(by_outcome.values()),
        "allowed": by_outcome.get("allow", 0),
        "spam": by_outcome.get("spam", 0),
        "errors": by_outcome.get("error", 0),
        "spam_signups": by_method.get("check_newuser", 0),
        "spam_content": by_method.get("check_message", 0),
        "average_seconds": float(average) if average is not None else None,
    }


def account_status(auth_key):
    """CleanTalk's account details for the key, or {"error": ...}; cached
    for 10 minutes. Fields used when CleanTalk sends them: valid, moderate,
    paid_till, trial, account_name_ob (the account's email, partly
    hidden)."""
    from r2.lib.antispam import CLEANTALK_KEY_URL, TIMEOUT
    if not auth_key:
        return None
    import hashlib
    cache_key = "cleantalk_account_" + hashlib.sha1(
        auth_key.encode("utf-8")).hexdigest()[:16]
    cached = g.gencache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(CLEANTALK_KEY_URL, timeout=TIMEOUT, params={
            "method_name": "notice_paid_till", "auth_key": auth_key})
        data = resp.json().get("data") or {}
        if not isinstance(data, dict):
            raise ValueError("unexpected answer")
        status = {k: data.get(k) for k in
                  ("valid", "moderate", "paid_till", "trial",
                   "account_name_ob", "product_id")}
    except (requests.RequestException, ValueError, AttributeError) as e:
        # don't cache a failure for long
        status = {"error": "couldn't reach CleanTalk: %s" % e}
        g.gencache.set(cache_key, status, time=60)
        return status
    g.gencache.set(cache_key, status, time=ACCOUNT_CACHE_SECONDS)
    return status
