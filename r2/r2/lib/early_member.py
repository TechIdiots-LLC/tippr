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

"""The "Early Member" award, for the site's first members: the first
early_member_count accounts made (/admin/config; 0 turns it off).

The site's own accounts (the system user, AutoModerator, feed bots) don't
take a place. Every other account does, in the order they were made, even
one that's later deleted or banned (which doesn't get the award), so the
places never move: the first 100 members stay the first 100.

A member gets it on signing up (handle_register), and tippr-job-year_clubs
catches anyone missed every day, which also gives it to the members a raised
count now includes. Lowering the count doesn't take it back; admins can
still give it and take it away from /admin/awards.
"""

from pylons import app_globals as g

from r2.lib.db.operators import asc
from r2.lib.utils import fetch_things2

CODENAME = "early_member"
DEFAULT_COUNT = 100
# memcache: the newest account with a place, for the count it was worked
# out for (newer accounts can't have one, so signups stop looking)
LAST_KEY = "early_member_last_%d"


def count():
    try:
        return max(int(g.live_config.get("early_member_count",
                                         DEFAULT_COUNT)), 0)
    except (TypeError, ValueError):
        return DEFAULT_COUNT


def is_site_account(account):
    """The site's own accounts, which don't take a place."""
    return (account.name in (g.system_user, g.automoderator_account) or
            getattr(account, "feed_bot", False) or
            # feed bots, before they're marked (r2.lib.feeds.bot_account)
            getattr(account, "registration_ip", None) == "0.0.0.0")


def can_have(account):
    return not (account._deleted or account._spam or
                getattr(account, "_banned", False))


def first_members(accounts, limit):
    """The first `limit` members of `accounts` (oldest first)."""
    places = []
    if limit <= 0:
        return places
    for account in accounts:
        if is_site_account(account):
            continue
        places.append(account)
        if len(places) >= limit:
            break
    return places


def _oldest_accounts():
    from r2.models import Account
    # deleted and spam accounts too, so the places don't move
    return fetch_things2(Account._query(Account.c._deleted == (True, False),
                                        Account.c._spam == (True, False),
                                        sort=asc("_date"), data=True))


def update():
    """Give the award to the first members who don't have it yet (the
    daily run). Returns how many have a place."""
    from r2.models import Award
    limit = count()
    places = first_members(_oldest_accounts(), limit)
    for account in places:
        if can_have(account):
            Award.give_if_needed(CODENAME, account)
    if len(places) >= limit > 0:
        g.gencache.set(LAST_KEY % limit, places[-1]._id)
    return len(places)


def on_register(account):
    """A new member gets it if they're one of the first."""
    from r2.models import Award
    limit = count()
    if limit <= 0 or is_site_account(account):
        return
    last = g.gencache.get(LAST_KEY % limit)
    if last is not None and account._id > last:
        return
    places = first_members(_oldest_accounts(), limit)
    if len(places) >= limit:
        g.gencache.set(LAST_KEY % limit, places[-1]._id)
    if any(place._id == account._id for place in places):
        Award.give_if_needed(CODENAME, account)
