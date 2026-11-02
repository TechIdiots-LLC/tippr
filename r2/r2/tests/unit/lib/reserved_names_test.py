#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""Usernames that would pass for staff (r2.lib.reserved_names)."""

from types import SimpleNamespace
from unittest.mock import patch

from r2.lib import reserved_names
from r2.tests import TipprTestCase


class TestReserved(TipprTestCase):
    def setUp(self):
        self.extra = ()
        g = SimpleNamespace(site_name="tippr", domain="tippr.net",
                            live_config={})
        g.live_config = SimpleNamespace(
            get=lambda key: self.extra if key == "reserved_usernames" else None)
        p = patch.object(reserved_names, "g", g)
        p.start()
        self.addCleanup(p.stop)

    def assertReserved(self, *names):
        for name in names:
            self.assertTrue(reserved_names.is_reserved(name), name)

    def assertAllowed(self, *names):
        for name in names:
            self.assertFalse(reserved_names.is_reserved(name), name)

    def test_staff_words_anywhere(self):
        self.assertReserved("admin", "Administrator", "xXadminXx", "siteadmin",
                            "Moderator", "AutoModerator", "the_official_one",
                            "sysop")

    def test_lookalikes(self):
        self.assertReserved("adm1n", "ADM1N", "a_d_m_i_n", "a-d-m-i-n",
                            "аdmin",          # Cyrillic a
                            "mοderator",      # Greek omicron
                            "adrnin",              # rn for m
                            "àdmin")          # an accent

    def test_mod_and_staff_as_parts(self):
        self.assertReserved("mod", "Mods", "tippr_mod", "TipprMod", "mod-team",
                            "Staff", "site_staff", "mod2")
        self.assertAllowed("modern", "modular_synth", "commodore", "staffordshire")

    def test_joined_words(self):
        self.assertReserved("support", "Team", "tippr_team", "tipprsupport",
                            "ModSupport", "the_tippr_team", "SecurityTeam")
        self.assertAllowed("Team_Rocket", "steam", "teamrocket",
                           "system_of_a_down_fan", "helpful_hannah")

    def test_the_sites_name(self):
        self.assertReserved("tippr", "Tippr", "t1ppr", "tippr_help")
        self.assertAllowed("tippr_fan", "ilovetippr")

    def test_whole_names(self):
        self.assertReserved("root", "noreply", "postmaster", "null")
        self.assertAllowed("root_beer", "information_age", "groot")

    def test_ordinary_names(self):
        self.assertAllowed("acalcutt", "news_bot", "badminton_fan", "Hannah",
                           "darkmode_dan", "user123", "Ice-Cream")

    def test_the_admins_words(self):
        self.assertAllowed("ceo_bob")
        self.extra = ("ceo", "Founder")
        self.assertReserved("ceo_bob", "TheFounder", "f0under")
