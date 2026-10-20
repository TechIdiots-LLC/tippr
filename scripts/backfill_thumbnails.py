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

"""Find thumbnails for recent link posts that don't have one.

The thumbnail finder (tippr-consumer-scraper_q, r2.lib.media) failed on
every post under Python 3, so posts made before it was fixed have none.
This queues the link posts of the last THUMB_DAYS days (default 3) that
have no thumbnail; the scraper_q consumer then finds one for each, as for
a new post.

    tippr-run scripts/backfill_thumbnails.py

THUMB_DAYS=7 goes further back. Safe to re-run.
"""

import os
from datetime import datetime, timedelta

from pylons import app_globals as g

from r2.lib import amqp
from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2
from r2.models import Link

days = int(os.environ.get("THUMB_DAYS", "3"))
cutoff = datetime.now(g.tz) - timedelta(days=days)

query = Link._query(sort=desc("_date"), data=True)
checked = queued = 0
for link in fetch_things2(query):
    if link._date < cutoff:
        break
    checked += 1
    if (link.is_self or link._deleted or link._spam or link.promoted or
            getattr(link, "has_thumbnail", False) or
            getattr(link, "media_object", None)):
        continue
    amqp.add_item("scraper_q", link._fullname)
    queued += 1

amqp.worker.join()
print("%d posts from the last %d days checked, %d queued for a thumbnail"
      % (checked, days, queued))
