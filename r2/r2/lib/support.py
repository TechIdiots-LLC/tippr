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
"""The support queue (/admin/support).

Members reach the site's staff through ordinary messages to a private
admin vault (admin_message_acct, e.g. /v/siteadmins): the contact page's
"message the admins" links, appeals, and so on. Replies reach them in their
inbox as messages from that vault, so they never see which staff member
wrote them.

Nobody works from that vault's moderator mail: only the system account
moderates it. Each conversation becomes a ticket here instead, with a
category (from the [tag] the contact page puts in the subject), a status
(new, open, waiting on the member, closed), an assignee and a history.
Staff see and answer tickets on /admin/support, which checks
can_view()/can_reply() for the ticket's category on every request.

Tickets and their history are PostgreSQL tables, so they move with backups.
"""

import re
from datetime import datetime

import sqlalchemy as sa
from pylons import app_globals as g
from pylons.i18n import N_

from r2.lib.db.tdb_sql import create_table, index_str, make_metadata
from r2.lib.hooks import HookRegistrar

support_hooks = HookRegistrar()

# category -> (name, the tag that marks it in a subject)
CATEGORIES = {
    "general": (N_("general"), "general"),
    "report": (N_("serious reports"), "report"),
    "appeal": (N_("appeals"), "appeal"),
    "privacy": (N_("privacy"), "privacy"),
    "legal": (N_("copyright and legal"), "legal"),
    "moderators": (N_("moderator help"), "moderators"),
    "ratelimit": (N_("rate limits"), "ratelimit"),
    "gold": (N_("gold"), "gold"),
}
CATEGORY_ORDER = ["general", "report", "appeal", "privacy", "legal",
                  "moderators", "ratelimit", "gold"]

STATUSES = {
    "new": N_("new"),
    "open": N_("open"),
    "waiting": N_("waiting on the member"),
    "closed": N_("closed"),
}

# the queue's views: name -> (label, statuses shown)
VIEWS = {
    "needs_reply": (N_("needs a reply"), ("new", "open")),
    "mine": (N_("assigned to me"), ("new", "open", "waiting")),
    "waiting": (N_("waiting on the member"), ("waiting",)),
    "closed": (N_("closed"), ("closed",)),
    "all": (N_("all"), ("new", "open", "waiting", "closed")),
}
VIEW_ORDER = ["needs_reply", "mine", "waiting", "closed", "all"]

_TAG_RE = re.compile(r"^\s*(?:re:\s*)*\[([a-z]+)\]", re.IGNORECASE)


###############################################################################
# Tables
###############################################################################

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

tickets = sa.Table(
    "support_tickets", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    # the conversation's first message (Message._id)
    sa.Column("root_message_id", sa.BigInteger, nullable=False, unique=True),
    # the member the conversation is with
    sa.Column("account_id", sa.BigInteger, nullable=True),
    sa.Column("category", sa.String, nullable=False),
    sa.Column("subject", sa.String, nullable=False, default=""),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("assignee_id", sa.BigInteger, nullable=True),
    sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_member_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_staff_id", sa.BigInteger, nullable=True),
    sa.Column("last_staff_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("messages", sa.Integer, nullable=False, default=1),
)

events = sa.Table(
    "support_ticket_events", METADATA,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ticket_id", sa.Integer, nullable=False),
    sa.Column("time", sa.DateTime(timezone=True), nullable=False),
    # who did it (None: the system)
    sa.Column("actor_id", sa.BigInteger, nullable=True),
    # created, member_message, reply, status, assign
    sa.Column("action", sa.String, nullable=False),
    sa.Column("detail", sa.Text, nullable=True),
)

create_table(tickets, [
    index_str(tickets, "status", "status"),
    index_str(tickets, "category", "category"),
    index_str(tickets, "assignee_id", "assignee_id"),
    index_str(tickets, "updated", "updated"),
])
create_table(events, [index_str(events, "ticket_id", "ticket_id")])


def _now():
    return datetime.now(g.tz)


###############################################################################
# The admin vault
###############################################################################

def vault_name():
    """The admin vault's name, or None when admin_message_acct isn't a
    vault (older configs sent "message the admins" to one account)."""
    acct = g.admin_message_acct or ""
    if acct.startswith("/v/"):
        return acct[len("/v/"):].strip("/") or None
    return None


def enabled():
    return vault_name() is not None


def get_vault():
    """The admin vault, or None if it isn't set up."""
    from r2.lib.db.thing import NotFound
    from r2.models import Vault
    name = vault_name()
    if not name:
        return None
    try:
        return Vault._by_name(name, stale=True)
    except NotFound:
        return None


def ensure_vault():
    """Create the admin vault if it's missing: private, moderated only by
    the system account. Returns it (or None when support isn't enabled)."""
    from r2.models import Account, Vault
    from r2.models.vault import VaultExists
    name = vault_name()
    if not name:
        return None
    vault = get_vault()
    if vault:
        return vault
    system = Account.system_user()
    try:
        vault = Vault._new(
            name=name,
            title=(g.site_name or g.domain) + " staff",
            author_id=system._id,
            ip="0.0.0.0",
            type="private",
            link_type="self",
            allow_top=False,
            hide_ads=True,
            public_description="Messages to the site's staff. Members "
                               "write here from the contact page.",
        )
    except VaultExists:
        return get_vault()
    vault.add_moderator(system)
    g.log.info("support: created the admin vault /v/%s", name)
    return vault


###############################################################################
# Permissions
###############################################################################

def can_view(user, category=None):
    """Whether user may see tickets (in category, if given)."""
    from pylons import tmpl_context as c
    return bool(user and getattr(c, "user_is_admin", False))


def can_reply(user, category=None):
    return can_view(user, category)


def visible_categories(user):
    return [cat for cat in CATEGORY_ORDER if can_view(user, cat)]


###############################################################################
# Tickets from messages
###############################################################################

def category_of(subject):
    """The category tagged in a subject ("[privacy] ..."), or general."""
    match = _TAG_RE.match(subject or "")
    tag = match.group(1).lower() if match else None
    for category, (_name, category_tag) in CATEGORIES.items():
        if tag == category_tag:
            return category
    return "general"


def _add_event(conn, ticket_id, actor_id, action, detail=None):
    conn.execute(events.insert().values(
        ticket_id=ticket_id, time=_now(), actor_id=actor_id, action=action,
        detail=detail))


@support_hooks.on("message.new")
def on_new_message(message):
    """Make or update the ticket for a message in the admin vault."""
    try:
        _on_new_message(message)
    except Exception:
        # never get in the way of sending the message itself
        g.log.exception("support: couldn't record message %s", message._id)


def _on_new_message(message):
    if not getattr(message, "vault_id", None):
        return
    vault = get_vault()
    if not vault or message.vault_id != vault._id:
        return

    from r2.models import Account
    author = Account._byID(message.author_id, data=True)
    from_staff = bool(getattr(message, "from_vault", False) or
                      vault.is_moderator(author))
    root_id = getattr(message, "first_message", None) or message._id
    now = _now()

    with ENGINE.begin() as conn:
        ticket = conn.execute(sa.select(tickets).where(
            tickets.c.root_message_id == root_id)).mappings().first()
        if ticket is None:
            member_id = (getattr(message, "to_id", None) if from_staff
                         else author._id)
            result = conn.execute(tickets.insert().values(
                root_message_id=root_id,
                account_id=member_id,
                category=category_of(message.subject),
                subject=(message.subject or "")[:300],
                status="waiting" if from_staff else "new",
                created=now,
                updated=now,
                last_member_at=None if from_staff else now,
                last_staff_id=author._id if from_staff else None,
                last_staff_at=now if from_staff else None,
                messages=1,
            ))
            ticket_id = result.inserted_primary_key[0]
            _add_event(conn, ticket_id, author._id, "created")
            return

        values = {"updated": now, "messages": ticket["messages"] + 1}
        if from_staff:
            values.update(status="waiting", last_staff_id=author._id,
                          last_staff_at=now)
            action = "reply"
        else:
            values["last_member_at"] = now
            if ticket["status"] in ("waiting", "closed"):
                values["status"] = "open"
            action = "member_message"
        conn.execute(tickets.update().where(
            tickets.c.id == ticket["id"]).values(**values))
        _add_event(conn, ticket["id"], author._id, action)


###############################################################################
# The queue
###############################################################################

def list_tickets(user, view="needs_reply", category=None, limit=100):
    """Tickets user may see, newest activity first."""
    categories = visible_categories(user)
    if category:
        categories = [cat for cat in categories if cat == category]
    if not categories:
        return []
    statuses = VIEWS.get(view, VIEWS["needs_reply"])[1]
    query = sa.select(tickets).where(
        tickets.c.status.in_(statuses),
        tickets.c.category.in_(categories),
    )
    if view == "mine":
        query = query.where(tickets.c.assignee_id == user._id)
    query = query.order_by(tickets.c.updated.desc()).limit(limit)
    with ENGINE.connect() as conn:
        return [dict(row) for row in conn.execute(query).mappings()]


def counts(user):
    """{view: number of tickets} for the queue's tabs."""
    categories = visible_categories(user)
    result = {view: 0 for view in VIEW_ORDER}
    if not categories:
        return result
    query = sa.select(tickets.c.status, tickets.c.assignee_id,
                      sa.func.count()).where(
        tickets.c.category.in_(categories)).group_by(
        tickets.c.status, tickets.c.assignee_id)
    with ENGINE.connect() as conn:
        for status, assignee_id, n in conn.execute(query):
            for view, (_label, statuses) in VIEWS.items():
                if status not in statuses:
                    continue
                if view == "mine" and assignee_id != user._id:
                    continue
                result[view] += n
    return result


def get_ticket(ticket_id):
    with ENGINE.connect() as conn:
        row = conn.execute(sa.select(tickets).where(
            tickets.c.id == ticket_id)).mappings().first()
    return dict(row) if row else None


def ticket_events(ticket_id):
    with ENGINE.connect() as conn:
        return [dict(row) for row in conn.execute(
            sa.select(events).where(events.c.ticket_id == ticket_id)
            .order_by(events.c.time)).mappings()]


def thread(ticket):
    """The conversation's messages, oldest first."""
    from r2.lib.db.operators import asc
    from r2.models import Message
    root = Message._byID(ticket["root_message_id"], data=True)
    replies = list(Message._query(
        Message.c.first_message == root._id, sort=asc("_date"), data=True))
    return [root] + replies


def set_status(ticket_id, status, actor):
    if status not in STATUSES:
        raise ValueError(status)
    with ENGINE.begin() as conn:
        conn.execute(tickets.update().where(tickets.c.id == ticket_id)
                     .values(status=status, updated=_now()))
        _add_event(conn, ticket_id, actor._id, "status", status)


def assign(ticket_id, assignee, actor):
    """Assign the ticket to assignee (an Account), or unassign (None)."""
    with ENGINE.begin() as conn:
        conn.execute(tickets.update().where(tickets.c.id == ticket_id)
                     .values(assignee_id=assignee._id if assignee else None))
        _add_event(conn, ticket_id, actor._id, "assign",
                   assignee.name if assignee else None)


def reply(ticket, staff, body, ip):
    """Answer the member as the admin team: a message from the admin vault
    in the ticket's conversation. The message.new hook records it."""
    from r2.lib.db import queries
    from r2.models import Account
    from r2.models import Message
    vault = get_vault()
    messages = thread(ticket)
    parent = messages[-1]
    member = Account._byID(ticket["account_id"], data=True)
    subject = parent.subject or ""
    if not subject.lower().startswith("re: "):
        subject = "re: " + subject
    message, inbox_rel = Message._new(staff, member, subject, body, ip,
                                      parent=parent, vault=vault,
                                      from_vault=True)
    queries.new_message(message, inbox_rel)
    return message
