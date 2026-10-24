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
"""Part of docker/visual-test.mjs's run (docker/smoke-test.sh with
VISUAL_TEST=1): the accounts the browser test acts as. Run with paster run.

Ordinary members, not admins or moderators, so the test covers what members
can do: they post, comment and vote in the browser like anyone else. They're
approved contributors of /v/visualtest (made here, owned by the admin), so
brand-new accounts aren't held back by the comment and submit rate limits,
and the one who posts has the post karma that skips the captcha. carol and
dave use night mode, so the pages are seen in both themes. visual_mod is a
moderator of /v/visualtest and nothing else, for the moderator tools.

Prints one line, "VISUAL_SEED " and the accounts as JSON
({name: {password, nightmode}}). Safe to re-run: existing accounts get new
passwords.
"""

import json
import os
import secrets

from pylons import app_globals as g

from r2.lib.db import queries
from r2.lib.db.thing import NotFound
from r2.models import Account, Vault
from r2.models.account import bcrypt_password, register

VAULT = "visualtest"
MEMBERS = {
    # name: night mode
    "visual_alice": False,
    "visual_bob": False,
    "visual_carol": True,
    "visual_dave": True,
    "visual_mod": False,
}
# a moderator of /v/visualtest only: an ordinary account otherwise, not staff
MODERATOR = "visual_mod"

admin = Account._by_name(os.environ.get("TIPPR_ADMIN_USER") or "tippr")

try:
    vault = Vault._by_name(VAULT)
except NotFound:
    vault = Vault._new(name=VAULT, title="visual test", author_id=admin._id,
                       ip="127.0.0.1", lang=g.lang, type="public",
                       link_type="any",
                       public_description="Made by the release's browser test.")
    vault._commit()
    vault.add_subscriber(admin)
    vault.add_moderator(admin)
    queries.new_Vault(vault)

accounts = {}
for name, nightmode in MEMBERS.items():
    password = secrets.token_urlsafe(18)
    try:
        account = Account._by_name(name)
        account.password = bcrypt_password(password)
    except NotFound:
        account = register(name, password, "127.0.0.1")
    account.pref_nightmode = nightmode
    account._commit()
    if not vault.is_contributor(account):
        vault.add_contributor(account)
    if name == MODERATOR and not vault.is_moderator(account):
        vault.add_moderator(account)
    # (an earlier run's ban, if the test stopped before lifting it)
    if vault.is_banned(account):
        vault.remove_banned(account)
    vault.add_subscriber(account)
    accounts[name] = {"password": password, "nightmode": nightmode}

# the one who posts skips the captcha (captcha_exempt_link_karma)
poster = Account._by_name("visual_alice")
needed = g.live_config["captcha_exempt_link_karma"] - poster.link_karma
if needed > 0:
    poster.incr_karma("link", vault, needed)
    poster._commit()

print("VISUAL_SEED " + json.dumps({"vault": VAULT, "accounts": accounts}))
