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

from r2.lib import utils
from r2.lib.cache import CL_ONE
from r2.lib.db import tdb_cassandra
from r2.lib.db.operators import desc
from r2.lib.memoize import memoize
from r2.models import Vault


class VaultsByPartialName(tdb_cassandra.View):
    _use_db = True
    _value_type = 'pickle'
    _connection_pool = 'main'
    _read_consistency_level = CL_ONE

def load_all_vaults():
    query_cache = {}

    q = Vault._query(Vault.c.type == 'public',
                         Vault.c._spam == False,
                         Vault.c._downs > 1,
                         sort = (desc('_downs'), desc('_ups')),
                         data = True)
    for vault in utils.fetch_things2(q):
        if vault.quarantine:
            continue
        name = vault.name.lower()
        for i in range(len(name)):
            prefix = name[:i + 1]
            names = query_cache.setdefault(prefix, [])
            if len(names) < 10:
                names.append((vault.name, vault.over_18))

    for name_prefix, vaults in query_cache.items():
        VaultsByPartialName._set_values(name_prefix, {'tups': vaults})

def search_vaults(query, include_over_18=True):
    query = str(query.lower())

    try:
        result = VaultsByPartialName._byID(query)
        return [name for (name, over_18) in getattr(result, 'tups', [])
                if not over_18 or include_over_18]
    except tdb_cassandra.NotFound:
        return []

@memoize('popular_searches', stale=True, time=3600)
def popular_searches(include_over_18=True):
    top_vaults = Vault._query(Vault.c.type == 'public',
                                   sort = desc('_downs'),
                                   limit = 100,
                                   data = True)
    top_searches = {}
    for vault in top_vaults:
        if vault.quarantine:
            continue
        if vault.over_18 and not include_over_18:
            continue
        name = vault.name.lower()
        for i in range(min(len(name), 3)):
            query = name[:i + 1]
            r = search_vaults(query, include_over_18)
            top_searches[query] = r
    return top_searches
