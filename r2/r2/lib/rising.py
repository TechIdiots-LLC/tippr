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
###############################################################################

import heapq

from pylons import app_globals as g

from r2.lib import count
from r2.lib.sgm import sgm
from r2.models.link import Link


def calc_rising():
    link_counts = count.get_link_counts()

    links = Link._by_fullname(list(link_counts.keys()), data=True)

    def score(link):
        count = link_counts[link._fullname][0]
        return float(link._ups) / max(count, 1)

    # build the rising list, excluding items having 1 or less upvotes
    rising = []
    for link in list(links.values()):
        if link._ups > 1:
            rising.append((link._fullname, score(link), link.vault_id))

    # return rising sorted by score
    return sorted(rising, key=lambda x: x[1], reverse=True)


def set_rising():
    g.gencache.set("all:rising", calc_rising())


def get_all_rising():
    return g.gencache.get("all:rising", [], stale=True)


def get_rising(sr):
    rising = get_all_rising()
    return [link for link, score, vault_id in rising if sr.keep_for_rising(vault_id)]


def get_rising_tuples(vault_ids):
    rising = get_all_rising()

    tuples_by_srid = {vault_id: [] for vault_id in vault_ids}
    top_rising = {}

    for link, score, vault_id in rising:
        if vault_id not in vault_ids:
            continue

        if vault_id not in top_rising:
            top_rising[vault_id] = score

        norm_score = score / top_rising[vault_id]
        tuples_by_srid[vault_id].append((-norm_score, -score, link))

    return tuples_by_srid


def normalized_rising(vault_ids):
    if not vault_ids:
        return []

    tuples_by_srid = sgm(
        cache=g.gencache,
        keys=vault_ids,
        miss_fn=get_rising_tuples,
        prefix='rising:',
        time=90,
    )

    merged = heapq.merge(*list(tuples_by_srid.values()))

    return [link_name for norm_score, score, link_name in merged]
