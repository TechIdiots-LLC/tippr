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

"""/admin/feeds' list (r2.lib.pages.AdminFeeds): the feeds searched,
filtered and sorted by the page's query (q, vault, bot, status, sort,
order), so a view keeps its address and stays after a save. The feeds are
r2.lib.feeds rows with vault_name and bot_name added."""

from urllib.parse import urlencode

STATUSES = ("all", "active", "paused", "errors", "never")

# sort name: the value it sorts by
SORTS = {
    "added": lambda f: f["id"],
    "title": lambda f: (f["feed_title"] or f["url"]).lower(),
    "vault": lambda f: f["vault_name"].lower(),
    "bot": lambda f: f["bot_name"].lower(),
    "every": lambda f: f["interval_minutes"],
    "checked": lambda f: (f["last_checked"].timestamp()
                          if f["last_checked"] else 0),
    "posts": lambda f: f["posted"],
    "reports": lambda f: f.get("reports", 0),
}

# with no sort given: the newest feeds first (the order added, backwards)
DEFAULT_SORT = "added"


def default_order(sort):
    """The way a sort goes until it's turned round: newest first for the
    order added, the most reported first for reports, A to Z (or smallest
    first) for the rest."""
    return "desc" if sort in ("added", "reports") else "asc"


# what the search looks in
SEARCHED = ("feed_title", "url", "vault_name", "bot_name", "title_prefix")


def status_is(f, status):
    if status == "active":
        return f["enabled"]
    if status == "paused":
        return not f["enabled"]
    if status == "errors":
        return bool(f["last_error"])
    if status == "never":
        return not f["last_checked"]
    return True


class FeedView:
    STATUSES = STATUSES

    def __init__(self, everything, q="", vault="", bot="", status="all",
                 sort=DEFAULT_SORT, order=None):
        self.q = (q or "").strip()
        self.vault = (vault or "").strip()
        self.bot = (bot or "").strip()
        self.status = status if status in STATUSES else "all"
        self.sort = sort if sort in SORTS else DEFAULT_SORT
        self.order = (order if order in ("asc", "desc")
                      else default_order(self.sort))
        # the menus: every vault and bot a feed has
        self.vault_names = sorted({f["vault_name"] for f in everything
                                   if f["vault_name"]}, key=str.lower)
        self.bot_names = sorted({f["bot_name"] for f in everything
                                 if f["bot_name"]}, key=str.lower)
        self.counts = {s: len([f for f in everything if status_is(f, s)])
                       for s in STATUSES}
        self.total = len(everything)

        needle = self.q.lower()
        shown = [
            f for f in everything
            if status_is(f, self.status)
            and (not self.vault or f["vault_name"].lower() == self.vault.lower())
            and (not self.bot or f["bot_name"].lower() == self.bot.lower())
            and (not needle or any(needle in (f[k] or "").lower()
                                   for k in SEARCHED))]
        shown.sort(key=SORTS[self.sort], reverse=self.order == "desc")
        self.feeds = shown

    def link(self, **changes):
        """/admin/feeds with this view's query, some of it changed."""
        query = dict(q=self.q, vault=self.vault, bot=self.bot,
                     status=self.status, sort=self.sort, order=self.order)
        query.update(changes)
        defaults = dict(status="all", sort=DEFAULT_SORT,
                        order=default_order(query["sort"] or DEFAULT_SORT))
        query = {k: v for k, v in query.items()
                 if v and v != defaults.get(k)}
        return "/admin/feeds" + ("?" + urlencode(query) if query else "")

    def sort_link(self, sort):
        """A column heading's link: by it (its usual way, default_order),
        or the other way round when it's already the sort."""
        if self.sort == sort:
            order = "asc" if self.order == "desc" else "desc"
        else:
            order = default_order(sort)
        return self.link(sort=sort, order=order)
