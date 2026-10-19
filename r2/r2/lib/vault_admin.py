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
"""Vaults as admins see them (/admin/vaults). Admins only.

Admins can create a vault whatever their karma and account age (the
create_vault_* limits on /admin/config are for everyone else; see
Account.can_create_Vault), and here they can find any vault, make it a
front page default or featured, give it moderators or take them away, and
ban it: a banned vault shows a "banned" page to everyone but the admins
until it's unbanned. Vaults can't be deleted outright (posts, comments and
subscriptions point at them), so banning is how one is removed.

Each action is logged in vault_admin_actions, shown on the vault's page.
"""

from collections import OrderedDict
from datetime import datetime, timezone

import sqlalchemy as sa
from pylons import app_globals as g

from r2.lib.db.tdb_sql import create_table, index_str, make_metadata

MAX_RESULTS = 50

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

actions_table = sa.Table(
    "vault_admin_actions", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("vault_id", sa.BigInteger, nullable=False),
    sa.Column("admin_id", sa.BigInteger, nullable=True),
    sa.Column("time", sa.DateTime(timezone=True), nullable=False),
    # ban, unban, default, undefault, feature, unfeature, add_moderator,
    # remove_moderator
    sa.Column("action", sa.String, nullable=False),
    sa.Column("detail", sa.Text, nullable=True),
)
create_table(actions_table, [
    index_str(actions_table, "vault_id", "vault_id"),
])

ACTION_NAMES = {
    "ban": "banned",
    "unban": "unbanned",
    "default": "made a front page default",
    "undefault": "no longer a front page default",
    "feature": "featured",
    "unfeature": "no longer featured",
    "add_moderator": "moderator added",
    "remove_moderator": "moderator removed",
}


def _log(vault, admin, action, detail=None):
    with ENGINE.begin() as conn:
        conn.execute(actions_table.insert().values(
            vault_id=vault._id, admin_id=admin._id if admin else None,
            time=datetime.now(g.tz), action=action, detail=detail))
    g.log.info("vault_admin: %s %s /v/%s (%s)", admin.name if admin else
               "system", action, vault.name, detail or "")


def action_log(vault):
    with ENGINE.connect() as conn:
        rows = [dict(row) for row in conn.execute(
            sa.select(actions_table)
            .where(actions_table.c.vault_id == vault._id)
            .order_by(actions_table.c.time.desc()).limit(100)).mappings()]
    for row in rows:
        row["time"] = row["time"].astimezone(timezone.utc)
    return rows


###############################################################################
# Finding vaults
###############################################################################

def _vaults(ids):
    from r2.models import Vault
    ids = [i for i in ids if i]
    if not ids:
        return []
    found = Vault._byID(ids, data=True, return_dict=True, ignore_missing=True)
    return [found[i] for i in ids if i in found]


def _query(*rules):
    from r2.lib.db.operators import desc
    from r2.models import Vault
    return list(Vault._query(Vault.c._spam == (True, False), *rules,
                             sort=desc("_date"), limit=MAX_RESULTS,
                             data=True))


def newest():
    return _query()


def banned():
    from r2.models import Vault
    return _query(Vault.c._spam == True)


def search(query):
    """[Vault] whose name is query or starts with it (any case)."""
    from r2.lib.db import tdb_sql
    from r2.lib.db.thing import NotFound
    from r2.models import Vault
    name = (query or "").strip().lstrip("/").removeprefix("v/") \
        .removeprefix("r/").strip("/")
    if not name:
        return []
    results = OrderedDict()
    try:
        exact = Vault._by_name(name)
        if isinstance(exact, Vault):
            results[exact._id] = exact
    except NotFound:
        pass
    table = tdb_sql.get_thing_table(Vault._type_id)[1]
    engine = tdb_sql.get_engine_from_table(table)
    pattern = name.lower().replace("\\", "\\\\").replace("%", "\\%") \
        .replace("_", "\\_") + "%"
    lookup = (sa.select(table.c.thing_id)
              .where(table.c.key == "name",
                     sa.func.lower(table.c.value).like(pattern, escape="\\"))
              .order_by(sa.func.lower(table.c.value))
              .limit(MAX_RESULTS))
    with engine.connect() as conn:
        ids = [row[0] for row in conn.execute(lookup)]
    for vault in _vaults(ids):
        results.setdefault(vault._id, vault)
    return list(results.values())[:MAX_RESULTS]


###############################################################################
# Front page defaults and featured vaults (the site-wide lists)
###############################################################################

def _lists():
    from r2.models.vault import LocalizedDefaultVaults, LocalizedFeaturedVaults
    return {"default": LocalizedDefaultVaults,
            "feature": LocalizedFeaturedVaults}


def listed_ids(which):
    cls = _lists()[which]
    return cls.get_vaultids(cls.GLOBAL)


def default_ids():
    return set(listed_ids("default"))


def featured_ids():
    return set(listed_ids("feature"))


def set_listed(vault, which, on, admin):
    """Add vault to (or take it off) the front page defaults (which:
    "default") or the featured vaults ("feature")."""
    cls = _lists()[which]
    ids = [i for i in listed_ids(which) if i != vault._id]
    if on:
        ids.append(vault._id)
    cls.set_global_vaults(_vaults(ids))
    _log(vault, admin, which if on else "un" + which)


def status(vault, defaults=None, featured=None):
    """Short labels for the vault's state."""
    labels = []
    if vault._spam:
        labels.append("banned")
    if vault.type != "public":
        labels.append(vault.type.replace("_", " "))
    if getattr(vault, "quarantine", False):
        labels.append("quarantined")
    if vault.over_18:
        labels.append("18+")
    if vault._id in (default_ids() if defaults is None else defaults):
        labels.append("default")
    if vault._id in (featured_ids() if featured is None else featured):
        labels.append("featured")
    return labels


###############################################################################
# Actions
###############################################################################

def ban(vault, admin, message=None):
    """Hide vault from everyone but the admins, showing message (if any)
    on its "banned" page. It also comes off the front page defaults and
    the featured vaults."""
    from copy import copy
    for which in ("default", "feature"):
        if vault._id in listed_ids(which):
            set_listed(vault, which, False, admin)
    ban_info = copy(getattr(vault, "ban_info", {}) or {})
    ban_info.update(banner=admin.name, banned_at=datetime.now(g.tz),
                    auto=False, moderator_banned=False,
                    message=message or "")
    vault.ban_info = ban_info
    vault._spam = True
    vault._commit()
    vault.update_search_index()
    _log(vault, admin, "ban", message or None)


def unban(vault, admin, note=None):
    from copy import copy
    ban_info = copy(getattr(vault, "ban_info", {}) or {})
    ban_info.update(unbanner=admin.name, unbanned_at=datetime.now(g.tz))
    vault.ban_info = ban_info
    vault._spam = False
    vault._commit()
    vault.update_search_index()
    _log(vault, admin, "unban", note or None)


def add_moderator(vault, account, admin):
    """Make account a moderator with every permission, without an
    invitation (as when someone creates a vault)."""
    from r2.models import ModAction
    vault.remove_moderator_invite(account)
    vault.add_moderator(account)
    if not vault.hide_contributors:
        vault.add_contributor(account)
    ModAction.create(vault, admin, "addmoderator", target=account)
    _log(vault, admin, "add_moderator", account.name)


def remove_moderator(vault, account, admin):
    from r2.models import ModAction
    vault.remove_moderator(account)
    ModAction.create(vault, admin, "removemoderator", target=account)
    _log(vault, admin, "remove_moderator", account.name)
