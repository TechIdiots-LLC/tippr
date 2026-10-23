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

"""The "X-Year Club" trophies, as on reddit: a member who has been here N
years has the N-Year Club award (only the latest; the one before is taken
back).

tippr-job-year_clubs runs every day and looks at the members whose
anniversary (cake day) was in the last few days, so a missed day is caught
up. update_all() looks at everyone, for a site's first run (the installer
does that through scripts/create_default_awards.py).

The awards are made as members first reach them ("1_year_club", "2-Year
Club", ...), with icons in r2/public/static/awards for 1 to MAX_ICON years
(MAX_ICON's says "+" and is used beyond it).
"""

import datetime
import re

from pylons import app_globals as g

from r2.lib.db.operators import asc, desc
from r2.lib.utils import fetch_things2

MAX_ICON = 20
CODENAME = "%d_year_club"
CODENAME_RE = re.compile(r"^(\d+)_year_club$")
# how far back the daily run looks, so a day or two without it is caught up
CATCH_UP_DAYS = 3


def anniversary(created, years):
    """The day an account made at `created` is `years` old (a 29 February
    account has its anniversaries on 28 February in other years)."""
    try:
        return created.replace(year=created.year + years)
    except ValueError:
        return created.replace(year=created.year + years, day=28)


def years_old(created, now):
    years = now.year - created.year
    if years > 0 and anniversary(created, years) > now:
        years -= 1
    return max(years, 0)


def icon_url(years):
    return "/static/awards/year_club_%d-%%d.png" % min(years, MAX_ICON)


def award_for(years):
    """The N-Year Club award, made the first time someone reaches it."""
    from r2.models import Award, NotFound
    codename = CODENAME % years
    try:
        return Award._by_codename(codename)
    except NotFound:
        Award._new(codename, "%d-Year Club" % years, "regular",
                   icon_url(years), True)
        return Award._by_codename(codename)


def update(account, now=None):
    """Give the account its current year club and take back older ones.
    Returns the number of years (0: not a year yet)."""
    from r2.models import Award, Trophy
    if account._deleted or account._spam or getattr(account, "_banned", False):
        return 0
    now = now or datetime.datetime.now(g.tz)
    years = years_old(account._date, now)
    have = set()
    for trophy in Trophy.by_account(account):
        match = CODENAME_RE.match(trophy._thing2.codename or "")
        if match:
            have.add(int(match.group(1)))
    if years >= 1 and years not in have:
        award_for(years)
        Award.give_if_needed(CODENAME % years, account)
    for old in have - {years}:
        Award.take_away(CODENAME % old, account)
    return years


def _accounts_between(start, end):
    from r2.models import Account
    query = Account._query(Account.c._date >= start, Account.c._date < end,
                           Account.c._deleted == False,
                           sort=asc("_date"), data=True)
    return fetch_things2(query)


def update_recent(now=None):
    """The daily run: members whose cake day was in the last CATCH_UP_DAYS
    days. Returns how many were looked at."""
    from r2.models import Account
    now = now or datetime.datetime.now(g.tz)
    oldest = list(Account._query(sort=asc("_date"), limit=1, data=True))
    if not oldest:
        return 0
    seen = 0
    for years in range(1, years_old(oldest[0]._date, now) + 1):
        # accounts made `years` years before the last few days
        end = now.replace(year=now.year - years) if not (
            now.month == 2 and now.day == 29) else now.replace(
                year=now.year - years, day=28)
        start = end - datetime.timedelta(days=CATCH_UP_DAYS)
        for account in _accounts_between(start, end + datetime.timedelta(seconds=1)):
            update(account, now)
            seen += 1
    return seen


def update_all(now=None):
    """Every member (a site's first run). Returns how many were looked at."""
    from r2.models import Account
    now = now or datetime.datetime.now(g.tz)
    seen = 0
    query = Account._query(Account.c._deleted == False, sort=desc("_date"),
                           data=True)
    for account in fetch_things2(query):
        update(account, now)
        seen += 1
    return seen


def run():
    """tippr-job-year_clubs (and the Early Member award's catch-up)"""
    seen = update_recent()
    g.log.info("year clubs: looked at %d members with an anniversary", seen)
    from r2.lib import early_member
    g.log.info("early members: %d", early_member.update())
