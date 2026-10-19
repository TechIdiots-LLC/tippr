#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import datetime

import pytz

from r2.lib import year_club
from r2.tests import TipprTestCase


def at(y, m, d, h=12):
    return datetime.datetime(y, m, d, h, tzinfo=pytz.utc)


class TestYearClub(TipprTestCase):
    def test_years_old(self):
        made = at(2020, 6, 15)
        self.assertEqual(year_club.years_old(made, at(2020, 12, 1)), 0)
        self.assertEqual(year_club.years_old(made, at(2021, 6, 14)), 0)
        self.assertEqual(year_club.years_old(made, at(2021, 6, 15)), 1)
        self.assertEqual(year_club.years_old(made, at(2026, 6, 16)), 6)

    def test_leap_day_accounts(self):
        made = at(2024, 2, 29)
        self.assertEqual(year_club.anniversary(made, 1), at(2025, 2, 28))
        self.assertEqual(year_club.anniversary(made, 4), at(2028, 2, 29))
        self.assertEqual(year_club.years_old(made, at(2025, 2, 27)), 0)
        self.assertEqual(year_club.years_old(made, at(2025, 2, 28)), 1)

    def test_icons(self):
        self.assertEqual(year_club.icon_url(3), "/static/awards/year_club_3-%d.png")
        self.assertEqual(year_club.icon_url(25), "/static/awards/year_club_20-%d.png")
        self.assertEqual(year_club.icon_url(3) % 40, "/static/awards/year_club_3-40.png")
