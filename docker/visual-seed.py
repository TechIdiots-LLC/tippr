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
VISUAL_TEST=1): the accounts the browser test acts as. Run with tippr-run.

For a throwaway test site only: it makes a site admin (visual_admin) whose
password and two-factor secret it prints.

Ordinary members, not admins or moderators, so the test covers what members
can do: they post, comment, vote and write to the admins in the browser like
anyone else. They're approved contributors of /v/visualtest (made here,
owned by the admin), so brand-new accounts aren't held back by the comment
and submit rate limits, and they have the post karma that skips the captcha
(for posting and for messages). carol and dave use night mode, so the pages
are seen in both themes. visual_mod is a moderator of /v/visualtest and
nothing else, for the moderator tools. visual_gold has (permanent) gold, for
gold's pages.

The support queue's staff: visual_admin, an admin (for admin mode), and
visual_support, an employee whose support categories the test grants on
/admin/support/staff. Both need two-factor sign-in, so each gets an
authenticator app whose secret is printed for the test to make codes with.

Prints one line, "VISUAL_SEED " and the accounts as JSON
({name: {password, nightmode, [totp]}}). Safe to re-run: existing accounts
get new passwords and secrets.
"""

import json
import os
import secrets

from pylons import app_globals as g

from r2.lib import support, totp, two_factor, user_admin
from r2.lib.db import queries
from r2.lib.db.thing import NotFound
from r2.models import Account, Vault, admintools
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
GOLD = "visual_gold"
# the support queue's staff: name -> place on the employees list
STAFF = {"visual_admin": "admin", "visual_support": "employee"}

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


def account_named(name, password):
    try:
        account = Account._by_name(name)
        account.password = bcrypt_password(password)
    except NotFound:
        account = register(name, password, "127.0.0.1")
    return account


accounts = {}
for name, nightmode in MEMBERS.items():
    password = secrets.token_urlsafe(18)
    account = account_named(name, password)
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
    # posting and messaging skip the captcha (captcha_exempt_link_karma)
    needed = g.live_config["captcha_exempt_link_karma"] - account.link_karma
    if needed > 0:
        account.incr_karma("link", vault, needed)
        account._commit()
    accounts[name] = {"password": password, "nightmode": nightmode}

# visual_gold: a member with (permanent) gold, for gold's pages: filtered
# /all (/me/f/all) and the account switcher in preferences
password = secrets.token_urlsafe(18)
account = account_named(GOLD, password)
# with the account switcher on (the browser test adds visual_admin to it)
account.pref_account_switcher = True
account._commit()
if not vault.is_contributor(account):
    vault.add_contributor(account)
vault.add_subscriber(account)
admintools.make_gold_permanent(account)
accounts[GOLD] = {"password": password, "nightmode": False}

for name, level in STAFF.items():
    password = secrets.token_urlsafe(18)
    account = account_named(name, password)
    account._commit()
    error = user_admin.set_staff_level(account, admin, level)
    if error:
        raise SystemExit("visual-seed: can't make %s %s: %s" % (name, level, error))
    two_factor.remove_all(account)
    secret = totp.generate_secret()
    two_factor.add_totp(account, secret, name="visual test")
    # the test grants the support categories itself (/admin/support/staff)
    support.set_permissions(account, {}, admin)
    accounts[name] = {"password": password, "nightmode": False, "totp": secret}

print("VISUAL_SEED " + json.dumps({"vault": VAULT, "accounts": accounts}))
