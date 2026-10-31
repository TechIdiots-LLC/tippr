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

"""Members' listing filters, like the Reddit Enhancement Suite's filteReddit.

Under "filters" on /prefs a member lists title keywords and users whose
posts they don't want in listings, and under "gold options" domains and
vaults (gold_allowed). Link.keep_item drops those posts (never the
member's own). A vault filter doesn't apply on that vault's
own page: visiting it is a choice to see it.

Keywords match whole words or phrases in titles, ignoring case. Domains
match subdomains too (example.com hides news.example.com). Each list is
kept to MAX_ENTRIES of up to MAX_LENGTH characters.
"""

import re

from pylons import app_globals as g
from pylons import tmpl_context as c

MAX_ENTRIES = 200
MAX_LENGTH = 100

FILTER_PREFS = (
    "pref_filter_keywords",
    "pref_filter_domains",
    "pref_filter_vaults",
    "pref_filter_users",
)
# the ones for gold members (gold_allowed)
GOLD_FILTERS = (
    "pref_filter_domains",
    "pref_filter_vaults",
)


def clean_list(text, kind):
    """The entries a member typed (one per line, or separated by commas),
    tidied: lower case, no duplicates, /v/ and /u/ prefixes and URL parts
    dropped."""
    if not text:
        return []
    if isinstance(text, (list, tuple)):
        text = "\n".join(text)
    entries = []
    for entry in re.split(r"[\n,]+", text):
        entry = entry.strip().lower()
        if kind == "vaults":
            entry = re.sub(r"^/?v/", "", entry).strip("/")
        elif kind == "users":
            entry = re.sub(r"^/?u(ser)?/", "", entry).strip("/")
        elif kind == "domains":
            entry = re.sub(r"^[a-z]+://", "", entry).split("/")[0]
            entry = entry.lstrip(".")
            if entry.startswith("www."):
                entry = entry[4:]
        entry = entry[:MAX_LENGTH]
        if entry and entry not in entries:
            entries.append(entry)
        if len(entries) >= MAX_ENTRIES:
            break
    return entries


def gold_allowed(user):
    """Gold members and admins filter by domain and vault (GOLD_FILTERS):
    gold's "filter /v/all", for every listing. Without gold, a list saved
    before is kept but not applied."""
    return bool(user and (user.gold or user.name in g.admins))


class _Filters:
    def __init__(self, user):
        self.keywords = list(getattr(user, "pref_filter_keywords", None) or [])
        self.domains, self.vaults = set(), set()
        if gold_allowed(user):
            self.domains = set(getattr(user, "pref_filter_domains", None) or [])
            self.vaults = set(getattr(user, "pref_filter_vaults", None) or [])
        self.users = set(getattr(user, "pref_filter_users", None) or [])
        self.keyword_re = None
        if self.keywords:
            self.keyword_re = re.compile(
                r"(?<!\w)(?:%s)(?!\w)" % "|".join(
                    re.escape(k) for k in self.keywords),
                re.IGNORECASE)

    def any(self):
        return bool(self.keyword_re or self.domains or self.vaults or
                    self.users)

    def domain_hidden(self, domain):
        domain = (domain or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        while domain:
            if domain in self.domains:
                return True
            if "." not in domain:
                return False
            domain = domain.split(".", 1)[1]
        return False

    def hides(self, link, wrapped):
        if self.users:
            author = getattr(wrapped, "author", None)
            if author and author.name.lower() in self.users:
                return True
        if self.vaults:
            vault = getattr(wrapped, "vault", None)
            if (vault and vault.name.lower() in self.vaults and
                    getattr(c.site, "_id", None) != vault._id):
                return True
        if self.domains and not link.is_self:
            domain = getattr(wrapped, "domain", None) or link.link_domain()
            if self.domain_hidden(domain):
                return True
        if self.keyword_re and self.keyword_re.search(link.title or ""):
            return True
        return False


def for_user(user):
    """The user's filters, worked out once a request."""
    # (c gives "" for attributes that were never set)
    cache = getattr(c, "_listing_filters", None)
    if not isinstance(cache, tuple) or cache[0] != user._id:
        cache = (user._id, _Filters(user))
        c._listing_filters = cache
    return cache[1]


def hides(user, link, wrapped):
    """Whether the user's filters hide this link."""
    if not user:
        return False
    filters = for_user(user)
    return filters.any() and filters.hides(link, wrapped)
