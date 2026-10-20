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

"""Fix the titles of feed posts that show HTML codes ("&#8216;Trump
Accounts&#8217;").

Some feeds escape their titles twice, which the feed importer didn't undo
before (r2.lib.feeds now does). This decodes the titles of the posts the
feed accounts already made (and drops any HTML tags in them, as the
importer does now).

    tippr-run scripts/fix_feed_titles.py

FIX_DRY_RUN=1 only lists what would change. Safe to re-run.
"""

import os

from r2.lib import feeds
from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2
from r2.models import Account, Link

dry_run = os.environ.get("FIX_DRY_RUN") == "1"


class _Text:
    def __init__(self, text):
        self.text = text


account_ids = {f["account_id"] for f in feeds.all_feeds() if f["account_id"]}
checked = fixed = 0
for account_id in sorted(account_ids):
    account = Account._byID(account_id, data=True)
    query = Link._query(Link.c.author_id == account_id, sort=desc("_date"),
                        data=True)
    for link in fetch_things2(query):
        checked += 1
        if "&" not in link.title and "<" not in link.title:
            continue
        title = feeds._title(_Text(link.title))
        if title and title != link.title:
            fixed += 1
            print("%s %s\n    -> %s" % ("would fix" if dry_run else "fixed",
                                        link.title, title))
            if not dry_run:
                link.title = title
                link._commit()
                try:
                    link.update_search_index()
                except Exception:
                    pass
    print("%s: checked their posts" % account.name)

print("%d posts checked, %d titles %s"
      % (checked, fixed, "to fix" if dry_run else "fixed"))
