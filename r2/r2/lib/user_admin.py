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
"""Finding and looking into accounts (/admin/users). Admins only.

Search takes a username (exact, then names starting with it), an email
address (any account that used it, matched the way the site matches
emails: case, dots and +tags in Gmail-style addresses) or an IP address
(accounts that logged in from it).

The account view adds what admins need and moderators shouldn't see: the
email and its verification, two-factor status, the IP addresses the account
logged in from in the last 100 days, other accounts seen on those addresses,
the vaults it moderates and its support tickets.
"""

import ipaddress
from collections import OrderedDict

import sqlalchemy as sa
from pylons import app_globals as g

MAX_RESULTS = 50
MAX_IPS = 20            # addresses shown on an account
MAX_PER_IP = 20         # other accounts listed for each address


def _account_data_table():
    """The accounts' data table (name, email, ...) and its engine."""
    from r2.lib.db import tdb_sql
    from r2.models import Account
    table = tdb_sql.get_thing_table(Account._type_id)[1]
    return table, tdb_sql.get_engine_from_table(table)


def _accounts(ids):
    from r2.models import Account
    ids = [i for i in ids if i]
    if not ids:
        return []
    found = Account._byID(ids, data=True, return_dict=True,
                          ignore_missing=True)
    return [found[i] for i in ids if i in found]


def kind_of(query):
    query = (query or "").strip()
    if "@" in query:
        return "email"
    try:
        ipaddress.ip_address(query)
        return "ip"
    except ValueError:
        return "name"


def search(query):
    """(kind, [Account]) for a search box query."""
    query = (query or "").strip()
    if not query:
        return None, []
    kind = kind_of(query)
    if kind == "email":
        return kind, _by_email(query)
    if kind == "ip":
        return kind, _by_ip(query)
    return kind, _by_name(query)


def _by_name(query):
    from r2.lib.db.thing import NotFound
    from r2.models import Account
    name = query.lstrip("/").removeprefix("u/").removeprefix("user/").strip("/")
    results = OrderedDict()
    try:
        exact = Account._by_name(name, allow_deleted=True)
        results[exact._id] = exact
    except NotFound:
        pass
    table, engine = _account_data_table()
    pattern = name.lower().replace("\\", "\\\\").replace("%", "\\%") \
        .replace("_", "\\_") + "%"
    query = (sa.select(table.c.thing_id)
             .where(table.c.key == "name",
                    sa.func.lower(table.c.value).like(pattern, escape="\\"))
             .order_by(sa.func.lower(table.c.value))
             .limit(MAX_RESULTS))
    with engine.connect() as conn:
        ids = [row[0] for row in conn.execute(query)]
    for account in _accounts(ids):
        results.setdefault(account._id, account)
    return list(results.values())[:MAX_RESULTS]


def _by_email(query):
    from r2.models.account import AccountsByCanonicalEmail
    results = OrderedDict()
    for account in AccountsByCanonicalEmail.get_accounts(query):
        results[account._id] = account
    # and exact matches the index might not have (older accounts)
    table, engine = _account_data_table()
    lookup = (sa.select(table.c.thing_id)
              .where(table.c.key == "email",
                     sa.func.lower(table.c.value) == query.lower())
              .limit(MAX_RESULTS))
    with engine.connect() as conn:
        ids = [row[0] for row in conn.execute(lookup)]
    for account in _accounts(ids):
        results.setdefault(account._id, account)
    return list(results.values())


def _by_ip(ip):
    from r2.models.ip import AccountsByIP
    ids = []
    for entry in AccountsByIP.get(ip, column_count=MAX_RESULTS):
        for account_id in entry.values():
            account_id = int(account_id)
            if account_id not in ids:
                ids.append(account_id)
    return _accounts(ids)


def ip_history(account):
    """[(ip, last seen)] for account, most recent first, one row per
    address."""
    from r2.models.ip import IPsByAccount
    seen = OrderedDict()
    for entry in IPsByAccount.get(account._id, column_count=200):
        for date, ip in entry.items():
            if ip not in seen:
                seen[ip] = date
        if len(seen) >= MAX_IPS:
            break
    return list(seen.items())


def related_accounts(account, ips):
    """{ip: [other Account]} for the given addresses."""
    from r2.models.ip import AccountsByIP
    related = {}
    for ip, _date in ips:
        ids = []
        for entry in AccountsByIP.get(ip, column_count=MAX_PER_IP * 3):
            for account_id in entry.values():
                account_id = int(account_id)
                if account_id != account._id and account_id not in ids:
                    ids.append(account_id)
        others = _accounts(ids[:MAX_PER_IP])
        if others:
            related[ip] = others
    return related


def moderated_vaults(account):
    from r2.models import Vault
    ids = Vault.reverse_moderator_ids(account)
    if not ids:
        return []
    vaults = Vault._byID(ids, data=True, return_dict=False)
    return sorted(vaults, key=lambda v: v.name.lower())


def support_tickets(account):
    from r2.lib import support
    if not support.enabled():
        return []
    with support.ENGINE.connect() as conn:
        return [dict(row) for row in conn.execute(
            sa.select(support.tickets)
            .where(support.tickets.c.account_id == account._id)
            .order_by(support.tickets.c.updated.desc())
            .limit(50)).mappings()]


def status(account):
    """Short labels for the account's state."""
    labels = []
    if account._deleted:
        labels.append("deleted")
    if account._banned:
        labels.append("suspended")
    if getattr(account, "in_timeout", False):
        labels.append("in timeout")
    if account._spam:
        labels.append("spammer")
    if getattr(account, "gold", False):
        labels.append("gold")
    if account.name in g.admins:
        labels.append("admin")
    return labels
