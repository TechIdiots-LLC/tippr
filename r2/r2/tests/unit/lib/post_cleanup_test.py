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
"""Which posts the post cleanup takes, and how it goes about it."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from r2.lib import post_cleanup
from r2.tests import TipprTestCase

BOT = 1
MEMBER = 2


def post(n=1, **kw):
    values = dict(_deleted=False, _spam=False, author_id=BOT, num_comments=0,
                  _ups=1, _downs=0, gildings=0, promoted=None, reported=0,
                  _fullname="t3_%d" % n, vault_id=10,
                  _date=datetime(2026, 1, 1, tzinfo=timezone.utc)
                  + timedelta(minutes=n))
    values.update(kw)
    return SimpleNamespace(**values)


VAULT = SimpleNamespace(sticky_fullnames=["t3_99"])


class TestQualifies(TipprTestCase):
    def fails(self, link, kind="feeds"):
        return post_cleanup._fails(link, VAULT, {BOT}, kind)

    def test_a_quiet_bot_post(self):
        self.assertIsNone(self.fails(post()))
        # (no votes at all, its author's taken back)
        self.assertIsNone(self.fails(post(_ups=0)))

    def test_any_interest_keeps_it(self):
        self.assertEqual(self.fails(post(num_comments=1)), "has comments")
        self.assertEqual(self.fails(post(_ups=2)), "has votes")
        self.assertEqual(self.fails(post(_downs=1)), "has votes")
        self.assertEqual(self.fails(post(gildings=1)), "gilded")
        self.assertEqual(self.fails(post(reported=1)), "reported")
        self.assertEqual(self.fails(post(n=99)), "stickied")
        self.assertEqual(self.fails(post(promoted=True)), "promoted")
        self.assertEqual(self.fails(post(_spam=True)), "deleted or removed")

    def test_each_rule_has_its_own_posts(self):
        self.assertEqual(self.fails(post(author_id=MEMBER)), "someone else's")
        self.assertIsNone(self.fails(post(author_id=MEMBER), "members"))
        self.assertEqual(self.fails(post(), "members"), "someone else's")


class TestFind(TipprTestCase):
    def find(self, batches, **kw):
        with patch.object(post_cleanup, "bot_ids", return_value={BOT}), \
                patch.object(post_cleanup, "_candidates",
                             side_effect=batches + [[]]) as candidates, \
                patch("r2.models.Vault._byID", return_value={10: VAULT}):
            found, checked, more = post_cleanup.find("feeds", 30, **kw)
        return [l._fullname for l in found], checked, more, candidates

    def test_oldest_first_skipping_the_rest(self):
        found, checked, more, _ = self.find(
            [[post(1), post(2, num_comments=3), post(3)]])
        self.assertEqual((found, checked, more), (["t3_1", "t3_3"], 3, False))

    def test_pages_on_from_the_last_post(self):
        with patch.object(post_cleanup, "BATCH", 2):
            found, checked, more, candidates = self.find(
                [[post(1), post(2)], [post(3)]])
        self.assertEqual(found, ["t3_1", "t3_2", "t3_3"])
        self.assertEqual(candidates.call_args_list[1].args[4], post(2)._date)

    def test_stops_at_the_limit(self):
        found, checked, more, _ = self.find([[post(1), post(2), post(3)]],
                                            limit=2)
        self.assertEqual((found, more), (["t3_1", "t3_2"], True))

    def test_a_bot_that_posts_no_feed(self):
        bot = SimpleNamespace(_id=MEMBER)
        self.assertEqual(self.find([], bot=bot)[:3], ([], 0, False))


class TestRuns(TipprTestCase):
    def setUp(self):
        for name in ("_start", "_finish"):
            p = patch.object(post_cleanup, name)
            p.start()
            self.addCleanup(p.stop)

    def test_a_run_stops_at_its_cap(self):
        batches = [([post(1), post(2)], 2, True), ([post(3)], 1, True)]
        with patch.object(post_cleanup, "find", side_effect=batches) as find, \
                patch.object(post_cleanup, "clean_up", return_value=1):
            self.assertEqual(post_cleanup.run("feeds", 30, 3), (3, 2))
        # (the second batch asks for only what's left)
        self.assertEqual(find.call_args_list[1].kwargs["limit"], 1)

    def test_the_daily_run_shares_the_cap(self):
        rules = dict(post_cleanup.DEFAULTS, feeds_enabled=True, feeds_days=30,
                     members_enabled=True, members_days=700, max_per_run=10)
        with patch.object(post_cleanup, "settings", return_value=rules), \
                patch.object(post_cleanup, "run",
                             side_effect=[(4, 0), (0, 0)]) as run:
            post_cleanup.run_scheduled()
        self.assertEqual([c.args for c in run.call_args_list],
                         [("feeds", 30, 10), ("members", 700, 6)])

    def test_off_rules_dont_run(self):
        with patch.object(post_cleanup, "settings",
                          return_value=dict(post_cleanup.DEFAULTS)), \
                patch.object(post_cleanup, "run") as run:
            post_cleanup.run_scheduled()
        run.assert_not_called()


class TestFiles(TipprTestCase):
    def link(self, thumbnail="https://media/t.jpg", uid="abc"):
        link = MagicMock(has_thumbnail=bool(thumbnail), thumbnail_url=thumbnail,
                         preview_object={"uid": uid, "url": "https://media/p.jpg"}
                         if uid else None, _fullname="t3_1")
        return link

    def clean_up(self, links, thumbnail_used=False, preview_used=False):
        fake_g = MagicMock()
        provider = fake_g.media_provider
        with patch("r2.lib.amqp.add_item"), \
                patch("r2.lib.db.queries.delete") as delete, \
                patch.object(post_cleanup, "_thumbnail_used",
                             return_value=thumbnail_used), \
                patch.object(post_cleanup, "_preview_used",
                             return_value=preview_used), \
                patch.object(post_cleanup, "g", fake_g):
            files = post_cleanup.clean_up(links)
        return files, provider.purge, delete

    def test_unshared_files_go(self):
        link = self.link()
        files, purge, delete = self.clean_up([link])
        self.assertEqual(files, 2)
        self.assertEqual(sorted(c.args[0] for c in purge.call_args_list),
                         ["https://media/p.jpg", "https://media/t.jpg"])
        self.assertTrue(link._deleted)
        link.set_preview_object.assert_called_with(None)
        delete.assert_called_once_with([link])

    def test_shared_files_stay(self):
        files, purge, _ = self.clean_up([self.link()], thumbnail_used=True,
                                        preview_used=True)
        self.assertEqual(files, 0)
        purge.assert_not_called()

    def test_a_post_without_images(self):
        files, purge, _ = self.clean_up([self.link(thumbnail=None, uid=None)])
        self.assertEqual(files, 0)
        purge.assert_not_called()


class TestRemoveFeed(TipprTestCase):
    FEED = dict(id=5, url="https://feed.example/rss", enabled=True,
                removing=None)

    def remove(self, which, links, batch=200):
        feeds = MagicMock()
        feeds.posted_link_ids.return_value = [l._fullname for l in links]
        admin = SimpleNamespace(name="admin")
        with patch("r2.lib.feeds", feeds), \
                patch("r2.models.Link._byID", return_value=links), \
                patch("r2.models.Vault._byID", return_value={10: VAULT}), \
                patch.object(post_cleanup, "REMOVE_BATCH", batch), \
                patch.object(post_cleanup, "_start"), \
                patch.object(post_cleanup, "_finish"), \
                patch.object(post_cleanup, "clean_up",
                             return_value=0) as clean_up:
            left = post_cleanup.remove_feed(dict(self.FEED), which, admin)
        cleaned = [l._fullname for c in clean_up.call_args_list
                   for l in c.args[0]]
        return left, cleaned, feeds

    def test_without_its_posts(self):
        left, cleaned, feeds = self.remove(None, [post(1)])
        self.assertEqual((left, cleaned), (0, []))
        feeds.remove.assert_called_once_with(5)
        feeds.update.assert_not_called()

    def test_the_quiet_ones_oldest_first(self):
        links = [post(3), post(1), post(2, num_comments=4), post(4, _deleted=True)]
        left, cleaned, feeds = self.remove("quiet", links)
        self.assertEqual((left, cleaned), (0, ["t3_1", "t3_3"]))
        feeds.update.assert_called_once_with(5, enabled=False, removing="quiet")
        feeds.remove.assert_called_once_with(5)

    def test_all_of_them_a_batch_at_a_time(self):
        links = [post(1), post(2, num_comments=4), post(3)]
        left, cleaned, feeds = self.remove("all", links, batch=2)
        # (the feed stays, marked, until the job has done the rest)
        self.assertEqual((left, cleaned), (1, ["t3_1", "t3_2"]))
        feeds.remove.assert_not_called()
