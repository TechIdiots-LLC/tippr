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

"""Take vaults without feeds off the front page defaults.

On a new site the posts come from feeds (/admin/feeds), so a default vault
with no feed only adds an empty entry to every newcomer's front page. This
takes every vault without an enabled feed off the site-wide defaults (the
vaults themselves stay, and anyone subscribed stays subscribed). Each
change is logged on the vault's /admin/vaults page; a vault can be made a
default again there.

    tippr-run scripts/prune_default_vaults.py

PRUNE_DRY_RUN=1 only lists what would change. PRUNE_KEEP=tippr,asktippr
keeps those (comma-separated names) even without feeds.
"""

import os

from pylons import app_globals as g

from r2.lib import feeds, vault_admin
from r2.models import Account, NotFound, Vault


def admin_account():
    names = [os.environ.get("TIPPR_ADMIN_USER")] + list(g.admins or [])
    for name in names:
        if not name:
            continue
        try:
            return Account._by_name(name)
        except NotFound:
            continue
    raise SystemExit("no admin account found")


dry_run = os.environ.get("PRUNE_DRY_RUN") == "1"
keep = {name.strip().lower()
        for name in os.environ.get("PRUNE_KEEP", "").split(",") if name.strip()}

with_feeds = {f["vault_id"] for f in feeds.all_feeds() if f["enabled"]}
defaults = Vault._byID(list(vault_admin.default_ids()), data=True,
                       return_dict=False)
admin = admin_account()

removed, kept = [], []
for vault in sorted(defaults, key=lambda v: v.name.lower()):
    if vault._id in with_feeds or vault.name.lower() in keep:
        kept.append(vault.name)
        continue
    removed.append(vault.name)
    if not dry_run:
        vault_admin.set_listed(vault, "default", False, admin)

verb = "would take off" if dry_run else "took off"
print("%s the front page defaults (no feeds): %s"
      % (verb, ", ".join(removed) or "none"))
print("defaults now: %s" % (", ".join(kept) or "none"))
if not kept:
    print("warning: no defaults left, so newcomers' front page is empty "
          "until they subscribe to something")
