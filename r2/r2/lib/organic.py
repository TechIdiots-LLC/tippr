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
#  Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026 
#  TechIdiots LLC. All Rights Reserved.
# 
#  Contributor(s): TechIdiots LLC
###############################################################################

import random

from r2.lib import count
from r2.lib.normalized_hot import normalized_hot
from r2.models import *

organic_max_length= 50


def cached_organic_links(*vault_ids):
    vault_count = count.get_link_counts()
    #only use links from reddits that you're subscribed to
    link_names = [n for n in list(vault_count.keys()) if vault_count[n][1] in vault_ids]
    link_names.sort(key = lambda n: vault_count[n][0])

    if not link_names and g.debug:
        q = All.get_links('new', 'all')
        q._limit = 100 # this decomposes to a _query
        link_names = [x._fullname for x in q if x.promoted is None]
        g.log.debug('Used inorganic links')

    #potentially add an up and coming link
    if random.choice((True, False)) and vault_ids:
        vault_id = random.choice(vault_ids)
        fnames = normalized_hot([vault_id])
        if fnames:
            if len(fnames) == 1:
                new_item = fnames[0]
            else:
                new_item = random.choice(fnames[1:4])
            link_names.insert(0, new_item)

    return link_names

def organic_links(user):
    vault_ids = Vault.user_vaults(user)
    # make sure that these are sorted so the cache keys are constant
    vault_ids.sort()

    # get the default vaults if the user is not logged in
    user_id = None if isinstance(user, FakeAccount) else user
    vault_ids = Vault.user_vaults(user, True)

    # pass the cached function a sorted list so that we can guarantee
    # cachability
    vault_ids.sort()
    return cached_organic_links(*vault_ids)[:organic_max_length]
