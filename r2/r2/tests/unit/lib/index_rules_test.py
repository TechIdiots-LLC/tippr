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
"""Which posts search engines are asked to index (r2.lib.index_rules)."""

import types
import unittest

from r2.lib import index_rules


def account(feed_bot=None):
    a = types.SimpleNamespace(name="someone")
    if feed_bot is not None:
        a.feed_bot = feed_bot
    return a


def link(num_comments=0):
    return types.SimpleNamespace(num_comments=num_comments)


class WaitsForPeopleTest(unittest.TestCase):
    def test_feed_bot_post_without_comments_waits(self):
        self.assertTrue(index_rules.waits_for_people(link(0), account(True)))

    def test_feed_bot_post_with_a_comment_is_indexed(self):
        self.assertFalse(index_rules.waits_for_people(link(1), account(True)))

    def test_a_persons_post_is_indexed(self):
        self.assertFalse(index_rules.waits_for_people(link(0), account(False)))
        self.assertFalse(index_rules.waits_for_people(link(0), account()))

    def test_unknown_author_is_indexed(self):
        self.assertFalse(index_rules.waits_for_people(link(0), None))

    def test_missing_comment_count_counts_as_none(self):
        self.assertTrue(index_rules.waits_for_people(
            types.SimpleNamespace(), account(True)))
        self.assertTrue(index_rules.waits_for_people(link(None),
                                                     account(True)))
