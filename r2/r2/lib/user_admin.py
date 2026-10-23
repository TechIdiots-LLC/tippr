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


PAGE_SIZE = 50


def listing(before=None, after=None, limit=PAGE_SIZE):
    """Every account, newest first, a page at a time (deleted and suspended
    ones too): ([Account], newer, older), where newer and older are the
    id36s to pass back as `after` and `before` for the next page each way
    (None at either end). `before`: accounts older than that one;
    `after`: newer than it."""
    from r2.lib.db.operators import asc, desc
    from r2.models import Account
    every = (Account.c._deleted == (True, False),
             Account.c._spam == (True, False))

    def page(anchor, newer):
        rules = list(every)
        if anchor is not None:
            rules.append(Account.c._id > anchor if newer else
                         Account.c._id < anchor)
        query = Account._query(*rules, sort=asc("_id") if newer else desc("_id"),
                               limit=limit + 1, data=True)
        return list(query)

    def id_of(id36):
        try:
            return int(id36, 36)
        except (TypeError, ValueError):
            return None

    if after:
        accounts = page(id_of(after), newer=True)
        more_newer = len(accounts) > limit
        accounts = list(reversed(accounts[:limit]))
        more_older = True
    else:
        accounts = page(id_of(before), newer=False)
        more_older = len(accounts) > limit
        accounts = accounts[:limit]
        more_newer = before is not None
    newer = accounts[0]._id36 if accounts and more_newer else None
    older = accounts[-1]._id36 if accounts and more_older else None
    return accounts, newer, older


def count_accounts():
    """How many accounts there are (deleted and suspended ones too)."""
    from r2.lib.db import tdb_sql
    from r2.models import Account
    table = tdb_sql.get_thing_table(Account._type_id)[0]
    with tdb_sql.get_engine_from_table(table).connect() as conn:
        return conn.execute(sa.select(sa.func.count()).select_from(table)).scalar()


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


# The internal status: a short label the admins give an account ("trusted",
# "watch", ...) and a note, for each other. Only admins see them; the member
# doesn't.
STATUS_MAX_LENGTH = 40
NOTE_MAX_LENGTH = 1000
MAX_BY_STATUS = 200     # accounts listed for one status


def internal_status(account):
    """(label, note) the admins gave the account ("" for none)."""
    return (getattr(account, "admin_status", "") or "",
            getattr(account, "admin_status_note", "") or "")


def statuses_in_use():
    """[(label, accounts with it)], the most used first."""
    table, engine = _account_data_table()
    count = sa.func.count()
    query = (sa.select(table.c.value, count)
             .where(table.c.key == "admin_status", table.c.value != "")
             .group_by(table.c.value)
             .order_by(count.desc(), table.c.value)
             .limit(MAX_RESULTS))
    with engine.connect() as conn:
        return [(row[0], row[1]) for row in conn.execute(query)]


def by_internal_status(label):
    """The accounts with that status, newest first."""
    table, engine = _account_data_table()
    query = (sa.select(table.c.thing_id)
             .where(table.c.key == "admin_status", table.c.value == label)
             .order_by(table.c.thing_id.desc())
             .limit(MAX_BY_STATUS))
    with engine.connect() as conn:
        ids = [row[0] for row in conn.execute(query)]
    return _accounts(ids)


###############################################################################
# Actions (each one logged in account_admin_actions)
###############################################################################

from datetime import datetime, timedelta, timezone

from r2.lib.db.tdb_sql import create_table, index_str, make_metadata
from r2.lib.hooks import HookRegistrar

user_admin_hooks = HookRegistrar()

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

actions_table = sa.Table(
    "account_admin_actions", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("account_id", sa.BigInteger, nullable=False),
    # who did it (None: the system, e.g. a timeout running out)
    sa.Column("admin_id", sa.BigInteger, nullable=True),
    sa.Column("time", sa.DateTime(timezone=True), nullable=False),
    # timeout, untimeout, suspend, unsuspend, remove_content, spam_content,
    # delete_content, reverify_email, remove_email, reset_2fa, delete_account,
    # set_status
    sa.Column("action", sa.String, nullable=False),
    sa.Column("detail", sa.Text, nullable=True),
)
create_table(actions_table, [
    index_str(actions_table, "account_id", "account_id"),
])

ACTION_NAMES = {
    "timeout": "timeout",
    "untimeout": "timeout lifted",
    "suspend": "suspended",
    "unsuspend": "suspension lifted",
    "remove_content": "content removed",
    "spam_content": "content removed as spam",
    "delete_content": "content deleted",
    "reverify_email": "email re-verification required",
    "remove_email": "email address removed",
    "reset_2fa": "two-factor reset",
    "delete_account": "account deleted",
    "set_status": "internal status changed",
}
MAX_CONTENT = 1000      # posts, and comments, acted on by the content tools
MAX_TIMEOUT_DAYS = 365


def _log(account, admin, action, detail=None):
    with ENGINE.begin() as conn:
        conn.execute(actions_table.insert().values(
            account_id=account._id, admin_id=admin._id if admin else None,
            time=datetime.now(g.tz), action=action, detail=detail))
    g.log.info("user_admin: %s %s %s (%s)", admin.name if admin else "system",
               action, account.name, detail or "")


def action_log(account):
    with ENGINE.connect() as conn:
        rows = [dict(row) for row in conn.execute(
            sa.select(actions_table)
            .where(actions_table.c.account_id == account._id)
            .order_by(actions_table.c.time.desc()).limit(100)).mappings()]
    # PostgreSQL hands times back in the server's zone; pages say UTC
    for row in rows:
        row["time"] = row["time"].astimezone(timezone.utc)
    return rows


def timeout(account, admin, days, reason):
    """Put account in timeout: it can read but not post, comment, vote or
    message anyone except the admins. days: 1 to MAX_TIMEOUT_DAYS, or None
    for no end."""
    from r2.models.bans import TempTimeout
    account.in_timeout = True
    account._commit()
    TempTimeout.unschedule(account)
    if days:
        TempTimeout.schedule(account, timedelta(days=days))
    length = ("%d days" % days) if days else "no end date"
    _log(account, admin, "timeout", "%s; %s" % (length, reason or "no reason"))
    from r2.lib import site_info
    _send_notice(account, "Your account is in a timeout",
                 ("Your account can't post, comment, vote or send messages "
                  "%s. Reason: %s\n\nIf you think this is a mistake, you can "
                  "still reach the site's staff through the contact page: %s")
                 % ("for %d days" % days if days else "until the staff lift it",
                    reason or "not given", site_info.contact_url("appeals")))


def set_internal_status(account, admin, label, note):
    """Give the account an internal status (internal_status); a blank label
    and note clear it. Returns whether anything changed."""
    label = " ".join((label or "").split())[:STATUS_MAX_LENGTH]
    note = (note or "").strip()[:NOTE_MAX_LENGTH]
    old_label, old_note = internal_status(account)
    if (label, note) == (old_label, old_note):
        return False
    account.admin_status = label
    account.admin_status_note = note
    account._commit()
    if label != old_label:
        detail = "%s -> %s" % (old_label or "none", label or "none")
    else:
        detail = "%s (note changed)" % (label or "none")
    _log(account, admin, "set_status", detail)
    return True


def untimeout(account, admin=None, reason=None):
    from r2.models.bans import TempTimeout
    account.in_timeout = False
    account._commit()
    TempTimeout.unschedule(account)
    _log(account, admin, "untimeout", reason)


def suspend(account, admin, reason):
    """Suspend account: it can't log in, and its sessions and app tokens end
    (Account._banned)."""
    account._banned = True
    _log(account, admin, "suspend", reason or "no reason")


def unsuspend(account, admin, reason=None):
    account._banned = False
    _log(account, admin, "unsuspend", reason)


def _content(account, limit=MAX_CONTENT):
    """The account's newest `limit` posts and newest `limit` comments that
    aren't deleted (removed ones included)."""
    from r2.lib.db.operators import desc
    from r2.models import Comment, Link
    things = []
    for cls in (Link, Comment):
        query = cls._query(cls.c.author_id == account._id,
                           cls.c._spam == (True, False),
                           cls.c._deleted == (True, False),
                           sort=desc("_date"), limit=limit, data=True)
        things.extend(t for t in query if not t._deleted)
    return things


def remove_content(account, admin, as_spam=False, limit=MAX_CONTENT):
    """Remove the account's posts and comments, as moderators remove things
    (they stay in the vaults' spam queues; as_spam also trains the spam
    filter). Returns how many were removed."""
    from r2.models.admintools import admintools
    things = [t for t in _content(account, limit) if not t._spam]
    if things:
        admintools.spam(things, auto=False, moderator_banned=True,
                        banner=admin.name, train_spam=as_spam)
        if as_spam:
            # what CleanTalk checked and let through (r2.lib.antispam)
            from r2.lib import antispam
            for t in things:
                antispam.feedback(t, spam=True)
    _log(account, admin, "spam_content" if as_spam else "remove_content",
         "%d removed" % len(things))
    return len(things)


def remove_content_as_spam(account, admin, limit=MAX_CONTENT):
    return remove_content(account, admin, as_spam=True, limit=limit)


def _delete_thing(thing, admin):
    """Delete a post or comment the way its author would
    (ApiController.POST_del): it shows as [deleted]."""
    from r2.lib import amqp
    from r2.lib.db import queries
    from r2.models import Comment, Link
    thing._deleted = True
    thing._commit()
    try:
        thing.update_search_index()
    except Exception:
        g.log.exception("user_admin: couldn't reindex %s", thing._fullname)
    if isinstance(thing, Link):
        amqp.add_item("deleted_link", thing._fullname)
        queries.delete(thing)
        thing.vault_slow.remove_sticky(thing)
        if thing.preview_object:
            thing.set_preview_object(None)
            thing._commit()
    elif isinstance(thing, Comment):
        link = thing.link_slow
        link._incr("num_comments", -1)
        link.remove_sticky_comment(comment=thing, set_by=admin)
        queries.new_comment(thing, None)
        queries.unnotify(thing)
        amqp.add_item("deleted_comment", thing._fullname)
        queries.delete(thing)


def delete_content(account, admin, limit=MAX_CONTENT, log=True):
    """Delete the account's posts and comments (the newest `limit` of
    each). Returns how many were deleted."""
    things = _content(account, limit)
    for thing in things:
        _delete_thing(thing, admin)
    if log:
        _log(account, admin, "delete_content", "%d deleted" % len(things))
    return len(things)


def require_email_verification(account, admin):
    """Mark the email address unverified and send a new verification
    link."""
    from r2.lib import emailer
    emailer.verify_email(account)
    _log(account, admin, "reverify_email", account.email)


def remove_email(account, admin, reason=None):
    old = account.email
    account.set_email("")
    account.email_verified = False
    account._commit()
    _log(account, admin, "remove_email",
         "%s; %s" % (old, reason) if reason else old)


def delete_account(account, admin, delete_posts, reason):
    """Delete the account for good: its sessions and app tokens end, and
    its password, email address, moderator and other roles go now, rather
    than 90 days later as when people delete their own account. Its posts
    and comments stay (by [deleted]) unless delete_posts."""
    from r2.models.account import deleted_account_cleanup
    from r2.models.token import OAuth2AccessToken, OAuth2RefreshToken
    deleted = delete_content(account, admin, log=False) if delete_posts else 0
    OAuth2AccessToken.revoke_all_by_user(account)
    OAuth2RefreshToken.revoke_all_by_user(account)
    account.delete(delete_message="deleted by the site's admins")
    deleted_account_cleanup({"admin": account._id36})
    _log(account, admin, "delete_account", "%s; %s" % (
        reason or "no reason",
        "%d posts and comments deleted" % deleted if delete_posts
        else "posts and comments kept"))


def reset_two_factor(account, admin, reason=None):
    """Turn off two-factor sign-in, for someone locked out of it."""
    from r2.lib import two_factor
    two_factor.remove_all(account)
    _log(account, admin, "reset_2fa", reason)


def _send_notice(account, subject, body):
    from r2.lib.db import queries
    from r2.models import Account, Message
    try:
        system = Account.system_user()
        message, inbox_rel = Message._new(system, account, subject, body,
                                          "0.0.0.0")
        message.distinguished = "admin"
        message._commit()
        queries.new_message(message, inbox_rel)
    except Exception:
        g.log.exception("user_admin: couldn't message %s", account.name)


@user_admin_hooks.on("trylater.untimeout")
def on_timeouts_ending(data):
    """Timeouts whose time is up (scheduled by timeout())."""
    from r2.models import Account
    for fullname in data.values():
        if isinstance(fullname, bytes):
            fullname = fullname.decode("utf-8")
        try:
            account = Account._by_fullname(fullname, data=True)
        except Exception:
            continue
        if getattr(account, "in_timeout", False):
            untimeout(account, None, "the timeout ran out")
