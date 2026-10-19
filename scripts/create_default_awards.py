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

"""Create the starter awards (the trophies on members' profiles).

Run with tippr-run (install/tippr.sh does this on every install):

    tippr-run scripts/create_default_awards.py

Two are given out by the site itself, which only does so once they exist:

- verified_email: when a member verifies their email address (and taken
  back if they change it)
- tippr_gold: when a member gets gold

The rest are for the admins to give from /admin/awards (an award's "give"
button), with an optional note and link:

- staff, early_member, bug_hunter, translator, helpful, best_comment

The "N-Year Club" trophies are made as members reach them (r2.lib.year_club,
kept up to date daily by tippr-job-year_clubs); the first run here gives
everyone theirs.

Members who verified their email or got gold before those two awards existed
get them when the awards are made; TIPPR_AWARD_BACKFILL=1 does that again.

Safe to re-run: awards that already exist (by codename) are left as the
admins set them. Each one's icon is in r2/public/static/awards (or the gold
one), at 40 and 70 pixels; imgurl has %d where the size goes.
"""

import os

from pylons import app_globals as g

from r2.models import Award, NotFound

site = g.site_name or "tippr"

AWARDS = [
    # codename, title, type, image
    ("verified_email", "Verified Email", "regular", "/static/awards/verified_email-%d.png"),
    ("tippr_gold", "tippr gold", "regular", "/static/tippr_gold-%d.png"),
    ("staff", "%s Staff" % site, "manual", "/static/awards/staff-%d.png"),
    ("early_member", "Early Member", "manual", "/static/awards/early_member-%d.png"),
    ("bug_hunter", "Bug Hunter", "manual", "/static/awards/bug_hunter-%d.png"),
    ("translator", "Translator", "manual", "/static/awards/translator-%d.png"),
    ("helpful", "Helpful Member", "manual", "/static/awards/helpful-%d.png"),
    ("best_comment", "Best Comment", "manual", "/static/awards/best_comment-%d.png"),
]

made = []
for codename, title, awardtype, imgurl in AWARDS:
    try:
        Award._by_codename(codename)
        continue
    except NotFound:
        pass
    Award._new(codename, title, awardtype, imgurl, True)
    made.append(codename)
    print("created award %s (%s)" % (codename, title))

print("%d awards created, %d already there" % (len(made), len(AWARDS) - len(made)))

# The site gives these as things happen, so members who verified their email
# or got gold before the award existed don't have it: give it to them once,
# when the award is first made (or again with TIPPR_AWARD_BACKFILL=1; members
# who already have it are skipped).
if os.environ.get("TIPPR_AWARD_BACKFILL"):
    made = list(set(made) | {"verified_email", "tippr_gold"})
if "verified_email" in made or "tippr_gold" in made:
    from r2.lib.db.operators import desc
    from r2.lib.utils import fetch_things2
    from r2.models import Account

    given = {"verified_email": 0, "tippr_gold": 0}
    for account in fetch_things2(Account._query(Account.c._deleted == False,
                                                sort=desc("_date"),
                                                data=True)):
        if account._spam or getattr(account, "_banned", False):
            continue
        if ("verified_email" in made and account.email and
                getattr(account, "email_verified", False)):
            Award.give_if_needed("verified_email", account)
            given["verified_email"] += 1
        if "tippr_gold" in made and getattr(account, "gold", False):
            Award.give_if_needed("tippr_gold", account)
            given["tippr_gold"] += 1
    print("made sure %(verified_email)d members with a verified email and "
          "%(tippr_gold)d gold members have those awards" % given)

    # and the X-Year Club trophies, which tippr-job-year_clubs keeps up to
    # date from then on, on each member's cake day
    from r2.lib import year_club
    print("year clubs: looked at %d members" % year_club.update_all())
