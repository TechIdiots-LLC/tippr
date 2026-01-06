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
import itertools
from datetime import datetime, timedelta

from pylons import app_globals as g

from r2.config import feature
from r2.lib.db.queries import CachedResults, _get_links
from r2.lib.db.sorts import epoch_seconds

MAX_PER_Vault = 150
MAX_LINKS = 1000


def get_hot_tuples(vault_ids, ageweight=None):
    queries_by_sr_id = {vault_id: _get_links(vault_id, sort='hot', time='all')
                        for vault_id in vault_ids}
    CachedResults.fetch_multi(list(queries_by_sr_id.values()), stale=True)
    tuples_by_srid = {vault_id: [] for vault_id in vault_ids}

    now_seconds = epoch_seconds(datetime.now(g.tz))

    for vault_id, q in queries_by_sr_id.items():
        if not q.data:
            continue

        hot_factor = get_hot_factor(q.data[0], now_seconds, ageweight)

        for link_name, hot, timestamp in q.data[:MAX_PER_Vault]:
            effective_hot = hot / hot_factor
            # heapq.merge sorts from smallest to largest so we need to flip
            # ehot and hot to get the hottest links first
            tuples_by_srid[vault_id].append(
                (-effective_hot, -hot, link_name, timestamp)
            )

    return tuples_by_srid


def get_hot_factor(qdata, now, ageweight):
    """Return a "hot factor" score for a link's hot tuple.

    Recalculate the item's hot score as if it had been submitted
    more recently than it was. This will cause the `effective_hot` value in
    get_hot_tuples to move older first items back

    ageweight should be a float from 0.0 - 1.0, which "scales" how far
    between the original submission time and "now" to use as the base
    for the new hot score. Smaller values will favor older #1 posts in
    multireddits; larger values will drop older posts further in the ranking
    (or possibly off the ranking entirely).

    """
    ageweight = float(ageweight or 0.0)
    link_name, hot, timestamp = qdata
    return max(hot + ((now - timestamp) * ageweight) / 45000.0, 1.0)


def normalized_hot(vault_ids, obey_age_limit=True, ageweight=None):
    timer = g.stats.get_timer("normalized_hot")
    timer.start()

    if not vault_ids:
        return []

    if not feature.is_enabled("scaled_normalized_hot"):
        ageweight = None

    tuples_by_srid = get_hot_tuples(vault_ids, ageweight=ageweight)

    if obey_age_limit:
        cutoff = datetime.now(g.tz) - timedelta(days=g.HOT_PAGE_AGE)
        oldest = epoch_seconds(cutoff)
    else:
        oldest = 0.

    merged = heapq.merge(*list(tuples_by_srid.values()))
    generator = (link_name for ehot, hot, link_name, timestamp in merged
                           if timestamp > oldest)
    ret = list(itertools.islice(generator, MAX_LINKS))
    timer.stop()
    return ret
