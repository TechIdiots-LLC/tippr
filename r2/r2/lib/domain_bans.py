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
"""Banned domains (/admin/domain/<domain>, /admin/domains).

A ban covers the domain and its subdomains (banning example.com bans
www.example.com and blog.example.com) and does one of two things to links
submitted to it:

- "block": the submit form refuses the link and says why (the reason is
  shown to the member);
- "spam": the link is accepted but removed as spam straight away, without
  telling the submitter (for spammers who would otherwise just try another
  address).

These back the hooks reddit's private plugin used to provide in
r2.models.admintools (is_banned_domain, is_shamed_domain and
bans_for_domain_parts). Bans are a PostgreSQL table, so they move with
backups.
"""

from collections import namedtuple
from datetime import datetime, timezone

import sqlalchemy as sa
from pylons import app_globals as g

from r2.lib.db.tdb_sql import create_table, make_metadata

ACTIONS = ("block", "spam")
_CACHE_KEY = "domain_bans"
_CACHE_SECONDS = 60

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

bans = sa.Table(
    "domain_bans", METADATA,
    sa.Column("domain", sa.String, primary_key=True),
    sa.Column("action", sa.String, nullable=False),
    # shown to members for "block"; for the admins only for "spam"
    sa.Column("reason", sa.Text, nullable=False, default=""),
    sa.Column("banned_by", sa.String, nullable=True),
    sa.Column("created", sa.DateTime(timezone=True), nullable=False),
)
create_table(bans)


# what the old hooks returned: .domain, and .banmsg for the spam note
Ban = namedtuple("Ban", "domain action reason banned_by created banmsg")


def normalize(domain):
    """example.com from "https://www.Example.com/x", "www.example.com." …"""
    domain = (domain or "").strip().lower()
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    domain = domain.split("/", 1)[0].split("?", 1)[0].split("@")[-1]
    domain = domain.split(":", 1)[0].rstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _host(url):
    from r2.lib.utils import UrlParser
    try:
        return normalize(UrlParser(url).hostname or "")
    except Exception:
        return ""


def all_bans():
    """{domain: Ban}"""
    found = g.gencache.get(_CACHE_KEY)
    if found is None:
        with ENGINE.connect() as conn:
            rows = list(conn.execute(sa.select(bans)).mappings())
        found = {}
        for row in rows:
            created = row["created"].astimezone(timezone.utc)
            found[row["domain"]] = Ban(
                row["domain"], row["action"], row["reason"] or "",
                row["banned_by"], created,
                "%s: %s" % (row["domain"], row["reason"] or row["action"]))
        g.gencache.set(_CACHE_KEY, found, time=_CACHE_SECONDS)
    return found


def ban_for(url_or_domain):
    """The ban covering a URL or domain (or one of its parent domains), or
    None."""
    host = (_host(url_or_domain) if "/" in (url_or_domain or "")
            else normalize(url_or_domain))
    if not host:
        return None
    current = all_bans()
    if not current:
        return None
    parts = host.split(".")
    for i in range(len(parts) - 1):
        ban = current.get(".".join(parts[i:]))
        if ban:
            return ban
    return None


def ban(domain, action, reason, admin):
    domain = normalize(domain)
    if not domain or "." not in domain or domain.startswith("self."):
        # (self.<vault> is how text posts show, not a real domain)
        raise ValueError("not a domain")
    if action not in ACTIONS:
        raise ValueError(action)
    with ENGINE.begin() as conn:
        conn.execute(bans.delete().where(bans.c.domain == domain))
        conn.execute(bans.insert().values(
            domain=domain, action=action, reason=(reason or "").strip()[:500],
            banned_by=admin.name, created=datetime.now(g.tz)))
    g.gencache.delete(_CACHE_KEY)
    g.log.info("domain_bans: %s banned %s (%s): %s", admin.name, domain,
               action, reason)


def unban(domain, admin):
    domain = normalize(domain)
    with ENGINE.begin() as conn:
        conn.execute(bans.delete().where(bans.c.domain == domain))
    g.gencache.delete(_CACHE_KEY)
    g.log.info("domain_bans: %s unbanned %s", admin.name, domain)


###############################################################################
# The hooks in r2.models.admintools
###############################################################################

def is_banned_domain(url):
    """A "spam" ban covering url (its submissions are removed as spam), or
    None."""
    found = ban_for(url)
    return found if found and found.action == "spam" else None


def is_shamed_domain(url):
    """(True, domain, reason) when a "block" ban covers url (the submit
    form refuses it), else (False, None, None)."""
    found = ban_for(url)
    if found and found.action == "block":
        return True, found.domain, found.reason or "banned by the admins"
    return False, None, None


def bans_for_domain_parts(urls):
    """The bans covering any of urls (to flag them for admins)."""
    seen = set()
    for url in urls or ():
        found = ban_for(url)
        if found and found.domain not in seen:
            seen.add(found.domain)
            yield found


###############################################################################
# The admin page
###############################################################################

def recent_links(domain, limit=100):
    """The newest links to domain or its subdomains, removed ones included."""
    from r2.lib.db import operators
    from r2.lib.db.operators import desc
    from r2.models import Link
    query = Link._query(operators.domain(Link.c.url) == domain,
                        Link.c._spam == (True, False),
                        sort=desc("_date"), limit=limit, data=True)
    return list(query)
