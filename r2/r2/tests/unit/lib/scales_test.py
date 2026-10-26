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
"""Scales: tipping, taking tips back, and who sees the tallies."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import sqlalchemy as sa

from r2.lib import scales
from r2.tests import TipprTestCase


def link(_id=1, author_id=100, **kw):
    attrs = dict(_id=_id, author_id=author_id, _deleted=False, _spam=False,
                 promoted=None, archived_slow=False)
    attrs.update(kw)
    return SimpleNamespace(**attrs)


def account(_id, **kw):
    return SimpleNamespace(_id=_id, in_timeout=kw.get("in_timeout", False))


class TestScales(TipprTestCase):
    def setUp(self):
        engine = sa.create_engine("sqlite://")
        table = scales._tips_table(sa.MetaData())
        table.create(engine)
        for target, value in (("r2.lib.scales._db",
                               {"engine": engine, "table": table}),
                              ("r2.lib.scales.g", MagicMock(tz=timezone.utc))):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.post = link()
        self.poster = account(100)
        self.alice = account(1)
        self.bob = account(2)

    def scale(self, summary, name):
        return next(s for s in summary["scales"] if s["name"] == name)

    def test_tip_change_and_take_back(self):
        scales.tip(self.post, self.alice, "depth", scales.LEFT)
        scales.tip(self.post, self.bob, "depth", scales.LEFT)
        self.assertEqual(scales.tallies(self.post)["depth"],
                         {scales.LEFT: 2, scales.RIGHT: 0})
        # one tip each: changing sides moves it
        scales.tip(self.post, self.alice, "depth", scales.RIGHT)
        self.assertEqual(scales.tallies(self.post)["depth"],
                         {scales.LEFT: 1, scales.RIGHT: 1})
        scales.tip(self.post, self.alice, "depth", 0)
        self.assertEqual(scales.tallies(self.post)["depth"],
                         {scales.LEFT: 1, scales.RIGHT: 0})
        self.assertEqual(scales.tips_by(self.post, self.alice), {})

    def test_scales_are_separate(self):
        scales.tip(self.post, self.alice, "made", scales.RIGHT)
        tallies = scales.tallies(self.post)
        self.assertEqual(tallies["made"][scales.RIGHT], 1)
        self.assertEqual(tallies["depth"], {scales.LEFT: 0, scales.RIGHT: 0})

    def test_tally_shown_only_once_tipped(self):
        scales.tip(self.post, self.bob, "depth", scales.LEFT)
        before = scales.summary(self.post, self.alice)
        self.assertIsNone(self.scale(before, "depth")["tally"])
        scales.tip(self.post, self.alice, "depth", scales.RIGHT)
        after = scales.summary(self.post, self.alice)
        self.assertEqual(self.scale(after, "depth")["tally"],
                         {"left": 1, "right": 1})
        self.assertEqual(self.scale(after, "depth")["mine"], scales.RIGHT)
        # only that scale's
        self.assertIsNone(self.scale(after, "tone")["tally"])

    def test_six_scales_all_shown(self):
        summary = scales.summary(self.post, self.alice)
        self.assertEqual([s["name"] for s in summary["scales"]],
                         ["made", "depth", "nature", "evidence", "tone",
                          "scope"])
        self.assertNotIn("more", summary["scales"][0])
        self.assertEqual(summary["bar_min"], scales.BAR_MIN)

    def test_retired_scales_arent_shown(self):
        # tips kept under a retired name (helpful) don't count anywhere
        with scales._engine().begin() as conn:
            conn.execute(scales._table().insert().values(
                link_id=self.post._id, account_id=self.bob._id,
                scale="helpful", side=scales.LEFT,
                created=datetime.now(timezone.utc)))
        self.assertNotIn("helpful", scales.tallies(self.post))
        summary = scales.summary(self.post, self.bob)
        names = [s["name"] for s in summary["scales"]]
        self.assertNotIn("helpful", names)
        # but are in the member's data export, with their side's name
        exported = scales.export(self.bob)
        self.assertEqual(exported[0]["scale"], "helpful")
        self.assertEqual(exported[0]["tipped_toward"], "helpful")

    def test_moderators_see_every_tally(self):
        scales.tip(self.post, self.bob, "tone", scales.RIGHT)
        mod = account(3)
        summary = scales.summary(self.post, mod, sees_all=True)
        self.assertTrue(summary["sees_all"])
        self.assertEqual(self.scale(summary, "tone")["tally"],
                         {"left": 0, "right": 1})
        self.assertEqual(self.scale(summary, "scope")["tally"],
                         {"left": 0, "right": 0})
        # and can still tip someone else's post
        self.assertTrue(summary["can_tip"])
        self.assertFalse(scales.summary(self.post, self.alice)["sees_all"])

    def test_poster_sees_tallies_but_cant_tip(self):
        scales.tip(self.post, self.alice, "tone", scales.LEFT)
        summary = scales.summary(self.post, self.poster)
        self.assertTrue(summary["is_poster"])
        self.assertFalse(summary["can_tip"])
        self.assertEqual(self.scale(summary, "tone")["tally"],
                         {"left": 1, "right": 0})

    def test_who_can_tip(self):
        self.assertTrue(scales.can_tip(self.post, self.alice))
        self.assertFalse(scales.can_tip(self.post, None))
        self.assertFalse(scales.can_tip(self.post, self.poster))
        self.assertFalse(scales.can_tip(self.post, account(3, in_timeout=True)))
        for closed in (dict(_deleted=True), dict(_spam=True),
                       dict(archived_slow=True), dict(promoted=True)):
            self.assertFalse(scales.can_tip(link(**closed), self.alice),
                             closed)

    def test_bad_scale_or_side(self):
        with self.assertRaises(ValueError):
            scales.tip(self.post, self.alice, "spam", scales.LEFT)
        with self.assertRaises(ValueError):
            scales.tip(self.post, self.alice, "depth", 5)

    def test_export(self):
        scales.tip(self.post, self.alice, "made", scales.RIGHT)
        scales.tip(link(_id=36), self.alice, "depth", scales.LEFT)
        exported = {t["post_id"]: t for t in scales.export(self.alice)}
        self.assertEqual(exported["1"]["tipped_toward"], "AI-generated")
        self.assertEqual(exported["10"]["tipped_toward"], "quick overview")
        self.assertEqual(scales.export(self.bob), [])
