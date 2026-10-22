#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from unittest.mock import MagicMock, patch

from r2.lib import activity_counter as ac
from r2.tests import TipprTestCase


class TestCountEvent(TipprTestCase):
    def setUp(self):
        self.counted = []
        for target, value in (
                ("r2.lib.activity_counter.count",
                 lambda name, vault=None: self.counted.append((name, vault))),
                ("r2.lib.activity_counter._vault_name",
                 lambda vault_id: "v%s" % vault_id if vault_id else None)):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def event(self, name, *args, **kwargs):
        self.counted.clear()
        ac.count_event(name, args, kwargs)
        return list(self.counted)

    def test_logins_and_signups(self):
        self.assertEqual(self.event("login_event", "login_attempt", error_msg=None),
                         [("logins", None)])
        self.assertEqual(self.event("login_event", "login_attempt", "WRONG_PASSWORD"),
                         [("failed_logins", None)])
        self.assertEqual(self.event("login_event", "register_attempt", error_msg=None),
                         [("signups", None)])
        self.assertEqual(self.event("login_event", "register_attempt", error_msg="BAD_CAPTCHA"),
                         [("failed_signups", None)])

    def test_new_visitor(self):
        self.assertEqual(self.event("loid_event", MagicMock(), "create_loid"),
                         [("new_visitors", None)])

    def test_votes_count_for_the_vault(self):
        vote = MagicMock(is_upvote=True, is_downvote=False)
        vote.thing.vault_id = 7
        self.assertEqual(self.event("vote_event", vote), [("upvotes", "v7")])
        vote = MagicMock(is_upvote=False, is_downvote=False)  # taken back
        self.assertEqual(self.event("vote_event", vote), [])

    def test_posts_comments_and_moderation(self):
        self.assertEqual(self.event("submit_event", MagicMock(vault_id=3)),
                         [("posts", "v3")])
        self.assertEqual(self.event("comment_event", MagicMock(vault_id=3)),
                         [("comments", "v3")])
        vault = MagicMock()
        vault.name = "books"
        self.assertEqual(self.event("report_event", reason="spam", vault=vault),
                         [("reports", "books")])
        self.assertEqual(
            self.event("mod_event", MagicMock(action="removelink"), vault, MagicMock()),
            [("mod_actions", "books"), ("mod:removelink", "books")])

    def test_other_events_are_ignored(self):
        self.assertEqual(self.event("bucketing_event", 1, "x", "a", None, None), [])

    def test_queue_counts_and_forwards(self):
        forward = MagicMock()
        queue = ac.CountingEventQueue(forward)
        with patch("r2.lib.activity_counter.count_event") as counted:
            queue.submit_event("a link", request=None)
        counted.assert_called_once_with("submit_event", ("a link",), {"request": None})
        forward.submit_event.assert_called_once_with("a link", request=None)
