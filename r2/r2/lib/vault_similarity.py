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

"""Which vaults are like which: "people who subscribe to X also subscribe
to Y", worked out from the site's own subscriptions.

The explore page's personalized part and the "similar vaults" suggestions
for multivaults read these from VaultRecommendation (r2.lib.recommender).
reddit filled that from an offline data job of its own; here
tippr-job-vault_similarity does it every day:

- each member's subscriptions (not deleted or suspended accounts) give
  every pair of vaults they subscribe to one shared subscriber
- a pair's score is its shared subscribers over the geometric mean of the
  two vaults' subscribers (cosine similarity), so a vault everyone is in
  (the front page defaults new accounts join) doesn't come out as like
  everything
- each vault keeps its MAX_RECS best, ranked; vaults that aren't public,
  are banned or quarantined, or are the site's own working vaults aren't
  recommended

The recommender leaves out what you already subscribe to, the defaults and
what you've dismissed, so with few members the page can still come up
short; it fills in as the site grows.
"""

import math
from collections import Counter, defaultdict
from itertools import combinations

from pylons import app_globals as g

from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2, to36

MAX_RECS = 20
# vaults with fewer subscribers than this aren't worth comparing
MIN_SUBSCRIBERS = 1
# members subscribed to more vaults than this don't say much about which
# go together (and would make the pair count grow fast)
MAX_SUBSCRIPTIONS = 200


def similarities(subscription_sets):
    """{vault id: [(similar vault id, score), ...] best first} from an
    iterable of each member's set of subscribed vault ids."""
    totals = Counter()
    shared = Counter()
    for ids in subscription_sets:
        ids = sorted(set(ids))
        if not ids or len(ids) > MAX_SUBSCRIPTIONS:
            continue
        totals.update(ids)
        shared.update(combinations(ids, 2))

    similar = defaultdict(list)
    for (a, b), both in shared.items():
        if totals[a] < MIN_SUBSCRIBERS or totals[b] < MIN_SUBSCRIBERS:
            continue
        score = both / math.sqrt(totals[a] * totals[b])
        similar[a].append((b, score))
        similar[b].append((a, score))
    for vault_id in similar:
        # best first; ties by id, for a stable order
        similar[vault_id].sort(key=lambda pair: (-pair[1], pair[0]))
    return similar


def _subscription_sets():
    from r2.models import Account, Vault
    query = Account._query(Account.c._deleted == False, sort=desc("_date"),
                           data=True)
    for account in fetch_things2(query):
        if account._spam or getattr(account, "_banned", False):
            continue
        yield Vault.subscribed_ids_by_user(account)


def _recommendable(vault_ids):
    """The ids of those vaults that can be recommended to anyone."""
    from r2.models import Vault
    working = set(Vault.not_random_vault_ids())
    promo = Vault.get_promote_vault_id()
    if promo:
        working.add(promo)
    vaults = Vault._byID(list(vault_ids), data=True, return_dict=False,
                         ignore_missing=True)
    return {
        v._id for v in vaults
        if v.type in ("public", "restricted") and not v._spam
        and not v.quarantine and v._id not in working
    }


def update():
    """Work out the similar vaults and store them for the recommender.
    Returns how many vaults got recommendations."""
    from r2.lib.recommender import (
        SRC_EXPLORE,
        SRC_MULTIVAULTS,
        VaultRecommendation,
    )
    similar = similarities(_subscription_sets())
    ok = _recommendable(set(similar) | {b for recs in similar.values()
                                         for b, _score in recs})
    stored = 0
    for vault_id, recs in similar.items():
        if vault_id not in ok:
            continue
        ranked = [to36(b) for b, _score in recs if b in ok][:MAX_RECS]
        if not ranked:
            continue
        stored += 1
        for source in (SRC_EXPLORE, SRC_MULTIVAULTS):
            rowkey = "{}.{}".format(source, to36(vault_id))
            VaultRecommendation._set_values(
                rowkey, {rank: id36 for rank, id36 in enumerate(ranked)})
            # a shorter list than last time: drop the old ranks past it
            try:
                old = VaultRecommendation._byID(rowkey)._values()
            except Exception:
                old = {}
            stale = [rank for rank in old if int(rank) >= len(ranked)]
            if stale:
                VaultRecommendation._remove(rowkey, stale)
    return stored


def run():
    """tippr-job-vault_similarity"""
    stored = update()
    g.log.info("vault similarity: recommendations for %d vaults", stored)
