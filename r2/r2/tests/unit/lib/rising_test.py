#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import datetime
from unittest.mock import MagicMock

import pytz

from r2.lib import rising
from r2.tests import TipprTestCase

NOW = datetime.datetime(2026, 10, 19, 12, 0, tzinfo=pytz.utc)


def link(ups=1, downs=0, comments=0, hours_old=1):
    return MagicMock(_ups=ups, _downs=downs, num_comments=comments,
                     _date=NOW - datetime.timedelta(hours=hours_old))


class TestRising(TipprTestCase):
    def test_a_new_post_alone_has_no_activity(self):
        # the submitter's own upvote doesn't count
        self.assertEqual(rising.activity(link()), 0)

    def test_votes_and_comments_count(self):
        self.assertEqual(rising.activity(link(ups=3)), 2)
        self.assertEqual(rising.activity(link(comments=4)), 4)
        self.assertEqual(rising.activity(link(ups=3, comments=2)), 4)
        # more downvotes than upvotes don't cancel the comments
        self.assertEqual(rising.activity(link(ups=1, downs=5, comments=2)), 2)

    def test_newer_activity_rises_higher(self):
        fresh = rising.rising_score(link(ups=4, hours_old=1), NOW)
        older = rising.rising_score(link(ups=4, hours_old=10), NOW)
        self.assertGreater(fresh, older)

    def test_more_activity_rises_higher(self):
        busy = rising.rising_score(link(ups=6, comments=5, hours_old=3), NOW)
        quiet = rising.rising_score(link(ups=2, hours_old=3), NOW)
        self.assertGreater(busy, quiet)
