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
"""/admin/feeds: searching, filtering and sorting the feeds (FeedView)."""

from datetime import datetime, timezone

from r2.lib.feed_view import FeedView
from r2.tests import TipprTestCase


def feed(_id, title, vault_name, bot_name, enabled=True, error=None,
         checked=True, posted=0, interval=60):
    return dict(id=_id, feed_title=title, url="https://%s.example/feed" % _id,
                vault_name=vault_name, bot_name=bot_name, enabled=enabled,
                last_error=error, posted=posted, interval_minutes=interval,
                title_prefix=None, over_18=False, ai_content=None,
                created=None,
                last_checked=(datetime(2026, 1, _id, tzinfo=timezone.utc)
                              if checked else None))


FEEDS = [
    feed(1, "Sports Daily", "sports", "news_bot", posted=5),
    feed(2, "Tech News", "technology", "news_bot", enabled=False, posted=9),
    feed(3, "World Report", "worldnews", "feed_bot", error="timed out", posted=1),
    feed(4, "Science Weekly", "technology", "feed_bot", checked=False, posted=0),
]


class TestFeedView(TipprTestCase):
    def ids(self, **kw):
        return [f["id"] for f in FeedView([dict(f) for f in FEEDS], **kw).feeds]

    def found(self, **kw):
        """Which feeds a search or filter shows, whatever their order."""
        return sorted(self.ids(**kw))

    def test_newest_first_until_sorted_otherwise(self):
        self.assertEqual(self.ids(), [4, 3, 2, 1])
        self.assertEqual(self.ids(sort="added", order="asc"), [1, 2, 3, 4])

    def test_search(self):
        # in titles (Tech News), vaults (worldnews) and bots (news_bot)
        self.assertEqual(self.found(q="news"), [1, 2, 3])
        self.assertEqual(self.found(q="WORLDNEWS"), [3])
        self.assertEqual(self.found(q="4.example"), [4])

    def test_filters(self):
        self.assertEqual(self.found(vault="technology"), [2, 4])
        self.assertEqual(self.found(bot="feed_bot"), [3, 4])
        self.assertEqual(self.found(status="paused"), [2])
        self.assertEqual(self.found(status="errors"), [3])
        self.assertEqual(self.found(status="never"), [4])
        self.assertEqual(self.found(status="active", vault="technology"), [4])
        page = FeedView(FEEDS)
        self.assertEqual(page.counts, dict(all=4, active=3, paused=1,
                                           errors=1, never=1))
        self.assertEqual(page.vault_names, ["sports", "technology", "worldnews"])

    def test_sorts(self):
        self.assertEqual(self.ids(sort="posts", order="desc"), [2, 1, 3, 4])
        self.assertEqual(self.ids(sort="title"), [4, 1, 2, 3])
        self.assertEqual(self.ids(sort="checked"), [4, 1, 2, 3])
        # anything else is newest first
        self.assertEqual(self.ids(sort="nonsense", status="bogus"), [4, 3, 2, 1])

    def test_most_reported_first(self):
        reported = [dict(f, reports=n) for f, n in zip(FEEDS, (0, 3, 7, 0))]
        shown = FeedView(reported, sort="reports").feeds
        self.assertEqual([f["id"] for f in shown][:2], [3, 2])
        # (rows without counts count as none)
        self.assertEqual(self.ids(sort="reports", order="asc")[0], 1)

    def test_links_keep_the_view(self):
        page = FeedView(FEEDS, vault="sports", sort="posts")
        self.assertEqual(page.link(), "/admin/feeds?vault=sports&sort=posts")
        # the sorted column the other way round, another one ascending
        self.assertEqual(page.sort_link("posts"),
                         "/admin/feeds?vault=sports&sort=posts&order=desc")
        self.assertEqual(page.sort_link("title"),
                         "/admin/feeds?vault=sports&sort=title")
        self.assertEqual(FeedView(FEEDS).link(), "/admin/feeds")
        # "added" turned round, and back to the default (no query)
        self.assertEqual(FeedView(FEEDS).sort_link("added"),
                         "/admin/feeds?order=asc")
        self.assertEqual(FeedView(FEEDS, order="asc").sort_link("added"),
                         "/admin/feeds")
