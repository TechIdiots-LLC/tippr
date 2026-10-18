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
"""Checking existing accounts against CleanTalk's blacklists (/admin/antispam).

Sign-ups are checked as they happen (r2.lib.antispam); this looks at the
accounts already here. Each run checks the next batch of accounts that
haven't been checked yet: their email address and the last address they
logged in from, through CleanTalk's spam_check method (up to 1000 values a
request). The answers are kept per account in cleantalk_user_checks, so the
next run carries on, and "start over" checks everyone again.

An account is flagged when CleanTalk has seen its email or address sending
spam elsewhere. Flagged accounts are listed for an admin to look at and act
on (suspend, remove as spam, or dismiss): CleanTalk's lists include shared
addresses and old reports, so nothing happens to an account by itself.
"""

from datetime import datetime

import requests
import sqlalchemy as sa
from pylons import app_globals as g

from r2.lib import antispam
from r2.lib.db.tdb_sql import create_table, index_str, make_metadata

SPAM_CHECK_URL = "https://api.cleantalk.org/"
MAX_VALUES_PER_REQUEST = 1000
DEFAULT_BATCH = 500
TIMEOUT = 20

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

checks = sa.Table(
    "cleantalk_user_checks", METADATA,
    sa.Column("account_id", sa.BigInteger, primary_key=True),
    sa.Column("checked", sa.DateTime(timezone=True), nullable=False),
    sa.Column("email", sa.String, nullable=True),
    sa.Column("ip", sa.String, nullable=True),
    sa.Column("email_appears", sa.Boolean, nullable=False, default=False),
    sa.Column("ip_appears", sa.Boolean, nullable=False, default=False),
    # how many sites reported it, and when CleanTalk last saw it
    sa.Column("email_frequency", sa.Integer, nullable=True),
    sa.Column("ip_frequency", sa.Integer, nullable=True),
    sa.Column("email_updated", sa.String, nullable=True),
    sa.Column("ip_updated", sa.String, nullable=True),
    sa.Column("flagged", sa.Boolean, nullable=False, default=False),
    # an admin looked and decided it's fine
    sa.Column("dismissed", sa.Boolean, nullable=False, default=False),
)
create_table(checks, [index_str(checks, "flagged", "flagged")])


class ScanError(Exception):
    pass


def _all_account_ids():
    """Every account's id, newest first (from the accounts' thing table)."""
    from r2.lib.db import tdb_sql
    from r2.models import Account
    thing_table = tdb_sql.get_thing_table(Account._type_id)[0]
    engine = tdb_sql.get_engine_from_table(thing_table)
    query = (sa.select(thing_table.c.thing_id)
             .where(thing_table.c.deleted == False)  # noqa: E712
             .order_by(thing_table.c.thing_id.desc()))
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(query)]


def _checked_ids():
    with ENGINE.connect() as conn:
        return {row[0] for row in conn.execute(sa.select(checks.c.account_id))}


def progress():
    """(checked, total, flagged and not dismissed)"""
    total = len(_all_account_ids())
    with ENGINE.connect() as conn:
        checked = conn.execute(
            sa.select(sa.func.count()).select_from(checks)).scalar()
        flagged = conn.execute(
            sa.select(sa.func.count()).select_from(checks).where(
                checks.c.flagged == True,  # noqa: E712
                checks.c.dismissed == False)).scalar()  # noqa: E712
    return checked, total, flagged


def _last_ip(account):
    from r2.models.ip import IPsByAccount
    for entry in IPsByAccount.get(account._id, column_count=1):
        for ip in entry.values():
            return ip
    return None


def _spam_check(values):
    """CleanTalk's answers for emails/addresses: {value: {...}}."""
    key = antispam.settings()["cleantalk_auth_key"]
    if not key:
        raise ScanError("set a CleanTalk access key first")
    try:
        resp = requests.post(SPAM_CHECK_URL, timeout=TIMEOUT, data={
            "method_name": "spam_check",
            "auth_key": key,
            "data": ",".join(values),
        })
        body = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise ScanError("couldn't reach CleanTalk: %s" % e)
    if not isinstance(body, dict):
        raise ScanError("CleanTalk sent an answer tippr doesn't understand")
    if body.get("error_message") or body.get("error_no"):
        raise ScanError("CleanTalk: %s" % (body.get("error_message") or
                                           body.get("error_no")))
    data = body.get("data")
    if not isinstance(data, dict):
        raise ScanError("CleanTalk sent no results")
    return {str(k).lower(): v for k, v in data.items() if isinstance(v, dict)}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run(limit=DEFAULT_BATCH):
    """Check up to `limit` accounts not checked yet. Returns (checked now,
    flagged now)."""
    from r2.models import Account
    if not antispam.settings()["cleantalk_auth_key"]:
        raise ScanError("set a CleanTalk access key first")
    limit = max(1, min(int(limit or DEFAULT_BATCH), 5000))
    done = _checked_ids()
    ids = [i for i in _all_account_ids() if i not in done][:limit]
    if not ids:
        return 0, 0
    accounts = Account._byID(ids, data=True, return_dict=False,
                             ignore_missing=True)

    targets = []   # (account, email, ip)
    for account in accounts:
        email = (account.email or "").strip().lower() or None
        targets.append((account, email, _last_ip(account)))

    # one request per MAX_VALUES_PER_REQUEST values
    answers = {}
    batch = []
    for _account, email, ip in targets:
        for value in (email, ip):
            if value and value not in answers and value not in batch:
                batch.append(value)
        if len(batch) >= MAX_VALUES_PER_REQUEST - 1:
            answers.update(_spam_check(batch))
            batch = []
    if batch:
        answers.update(_spam_check(batch))

    now = datetime.now(g.tz)
    flagged_now = 0
    with ENGINE.begin() as conn:
        for account, email, ip in targets:
            e = answers.get(email, {}) if email else {}
            i = answers.get(ip, {}) if ip else {}
            email_appears = str(e.get("appears", "0")) == "1"
            ip_appears = str(i.get("appears", "0")) == "1"
            flagged = email_appears or ip_appears
            flagged_now += flagged
            conn.execute(checks.delete().where(
                checks.c.account_id == account._id))
            conn.execute(checks.insert().values(
                account_id=account._id, checked=now, email=email, ip=ip,
                email_appears=email_appears, ip_appears=ip_appears,
                email_frequency=_int(e.get("frequency")),
                ip_frequency=_int(i.get("frequency")),
                email_updated=e.get("updated"), ip_updated=i.get("updated"),
                flagged=flagged, dismissed=False))
    g.log.info("cleantalk scan: checked %d accounts, %d flagged",
               len(targets), flagged_now)
    return len(targets), flagged_now


def reset():
    """Forget every result, so the next runs check everyone again."""
    with ENGINE.begin() as conn:
        conn.execute(checks.delete())


def flagged_accounts(limit=200):
    """[(Account, check row)] flagged and not dismissed, most reported
    first."""
    from r2.models import Account
    with ENGINE.connect() as conn:
        rows = [dict(row) for row in conn.execute(
            sa.select(checks).where(checks.c.flagged == True,  # noqa: E712
                                    checks.c.dismissed == False)  # noqa: E712
            .order_by(checks.c.checked.desc()).limit(limit)).mappings()]
    if not rows:
        return []
    accounts = Account._byID([r["account_id"] for r in rows], data=True,
                             return_dict=True, ignore_missing=True)
    result = [(accounts[r["account_id"]], r) for r in rows
              if r["account_id"] in accounts]
    result.sort(key=lambda pair: -((pair[1]["email_frequency"] or 0) +
                                   (pair[1]["ip_frequency"] or 0)))
    return result


def dismiss(account_ids):
    with ENGINE.begin() as conn:
        conn.execute(checks.update().where(
            checks.c.account_id.in_(list(account_ids))).values(dismissed=True))
