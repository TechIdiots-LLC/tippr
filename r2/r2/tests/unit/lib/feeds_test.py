#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from types import SimpleNamespace
from unittest.mock import patch

from r2.lib import feeds
from r2.tests import TipprTestCase

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example</title>
<item><title>Elon Musk&#8217;s plan for &amp;#8216;Trump Accounts&amp;#8217;</title>
  <link>https://example.com/a</link><guid>a</guid></item>
<item><title><![CDATA[Ben &amp; Jerry's <b>new</b> flavour]]></title>
  <link>https://example.com/b</link><guid>b</guid></item>
<item><title>Why 2 &lt; 3 &gt; 1</title>
  <link>https://example.com/c</link><guid>c</guid></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry><id>x</id><link href="https://example.com/x"/>
  <title type="html">Caf&amp;eacute; &amp;lt;i&amp;gt;news&amp;lt;/i&amp;gt;</title></entry>
</feed>"""


class TestFeedTitles(TipprTestCase):
    def test_double_escaped_and_html_titles(self):
        _, items = feeds.parse(RSS)
        self.assertEqual([i["title"] for i in items], [
            "Elon Musk’s plan for ‘Trump Accounts’",
            "Ben & Jerry's new flavour",
            "Why 2 < 3 > 1",
        ])

    def test_atom_html_title(self):
        _, items = feeds.parse(ATOM)
        self.assertEqual(items[0]["title"], "Café news")


class TestInterleave(TipprTestCase):
    def test_spreads_vaults_and_feeds(self):
        sports1, sports2, anime = {"id": 1}, {"id": 2}, {"id": 3}
        order = feeds._interleave([
            ("sports", sports1, ["s1a", "s1b", "s1c"]),
            ("sports", sports2, ["s2a", "s2b"]),
            ("anime", anime, ["a1", "a2"]),
        ])
        self.assertEqual([item for _, item in order],
                         ["s1a", "a1", "s2a", "a2", "s1b", "s2b", "s1c"])

    def test_empty(self):
        self.assertEqual(feeds._interleave([]), [])
        self.assertEqual(feeds._interleave([("v", {"id": 1}, [])]), [])


class TestReportReasons(TipprTestCase):
    def test_reasons_are_trimmed_and_named(self):
        self.assertEqual(feeds._reason("  spam "), "spam")
        self.assertEqual(feeds._reason(None), "no reason given")
        self.assertEqual(feeds._reason(""), "no reason given")
        self.assertEqual(len(feeds._reason("x" * 500)), feeds.REPORT_REASON_LENGTH)


class TestHideFeedBots(TipprTestCase):
    def hides(self, pref, author_id):
        user = SimpleNamespace(pref_hide_feed_bots=pref)
        fake_c = SimpleNamespace()
        with patch.object(feeds, "c", fake_c), \
                patch.object(feeds, "_bot_ids", return_value=[7]) as bots:
            first = feeds.hides(user, SimpleNamespace(author_id=author_id))
            # (looked up once a request)
            feeds.hides(user, SimpleNamespace(author_id=author_id))
        return first, bots.call_count

    def test_only_the_bots_and_only_when_chosen(self):
        self.assertEqual(self.hides(True, 7), (True, 1))
        self.assertEqual(self.hides(True, 8)[0], False)
        self.assertEqual(self.hides(False, 7), (False, 0))
        self.assertFalse(feeds.hides(None, SimpleNamespace(author_id=7)))


class TestFeedStats(TipprTestCase):
    def test_adding_up(self):
        totals = dict(posts=0, ups=0, downs=0, comments=0, interested=0)
        feeds._add_up(totals, SimpleNamespace(_ups=1, _downs=0, num_comments=0))
        feeds._add_up(totals, SimpleNamespace(_ups=4, _downs=1, num_comments=2))
        # (the bot's own upvote isn't counted; taken back, it's not negative)
        feeds._add_up(totals, SimpleNamespace(_ups=0, _downs=0, num_comments=0))
        self.assertEqual(totals, dict(posts=3, ups=3, downs=1, comments=2,
                                      interested=1))
