# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

import datetime
import heapq

from pylons import app_globals as g

from r2.lib import utils
from r2.lib.db.operators import desc
from r2.lib.sgm import sgm
from r2.models.link import Link

# how many of the period's newest posts are looked at
MAX_LINKS = 2000
# how quickly a post sinks as it gets older (as on Hacker News)
GRAVITY = 1.5


def activity(link):
    """What's happened on a post since it went up: other people's votes
    (not the submitter's own upvote) and comments."""
    votes = link._ups - link._downs - 1
    return max(votes, 0) + (link.num_comments or 0)


def rising_score(link, now=None):
    """Activity for its age: a post with a few votes or comments in its
    first hour beats one that took a day to get them.

    reddit divided votes by the post's page views, counted by its own
    infrastructure, which tippr doesn't have; the site's sizes vary too
    much for a fixed number of votes to mean the same everywhere.
    """
    now = now or datetime.datetime.now(g.tz)
    age_hours = max((now - link._date).total_seconds() / 3600, 0)
    return activity(link) / (age_hours + 2) ** GRAVITY


def calc_rising():
    """The posts of the last rising_period that people have voted on or
    commented on, best first: [(fullname, score, vault id)]."""
    links = Link._query(Link.c._date >= utils.timeago(g.rising_period),
                        Link.c._spam == False,
                        Link.c._deleted == False,
                        sort=desc('_date'), limit=MAX_LINKS, data=True)
    now = datetime.datetime.now(g.tz)
    rising = []
    for link in links:
        if getattr(link, "promoted", None) or not activity(link):
            continue
        rising.append((link._fullname, rising_score(link, now), link.vault_id))
    return sorted(rising, key=lambda x: x[1], reverse=True)


def set_rising():
    g.gencache.set("all:rising", calc_rising())


def get_all_rising():
    return g.gencache.get("all:rising", [], stale=True)


def get_rising(vault):
    rising = get_all_rising()
    return [link for link, score, vault_id in rising if vault.keep_for_rising(vault_id)]


def get_rising_tuples(vault_ids):
    rising = get_all_rising()

    tuples_by_vault_id = {vault_id: [] for vault_id in vault_ids}
    top_rising = {}

    for link, score, vault_id in rising:
        if vault_id not in vault_ids:
            continue

        if vault_id not in top_rising:
            top_rising[vault_id] = score

        norm_score = score / top_rising[vault_id]
        tuples_by_vault_id[vault_id].append((-norm_score, -score, link))

    return tuples_by_vault_id


def normalized_rising(vault_ids):
    if not vault_ids:
        return []

    tuples_by_vault_id = sgm(
        cache=g.gencache,
        keys=vault_ids,
        miss_fn=get_rising_tuples,
        prefix='rising:',
        time=90,
    )

    merged = heapq.merge(*list(tuples_by_vault_id.values()))

    return [link_name for norm_score, score, link_name in merged]
