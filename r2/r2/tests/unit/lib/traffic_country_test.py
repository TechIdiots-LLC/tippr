#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""Counting pageviews by country (r2.lib.traffic_counter.visitor_country)."""

from types import SimpleNamespace
from unittest.mock import patch

import babel.core

from r2.lib import geoip, traffic_counter
from r2.lib.pages.trafficpages import CountryTraffic
from r2.tests import TipprTestCase


class TestVisitorCountry(TipprTestCase):
    def setUp(self):
        self.g = SimpleNamespace(geoip_location="http://127.0.0.1:5000",
                                 log=SimpleNamespace(exception=lambda *a: None))
        for p in (patch.object(traffic_counter, "g", self.g),
                  patch.object(traffic_counter, "_geoip_paused_until", 0.0)):
            p.start()
            self.addCleanup(p.stop)
        self.request = SimpleNamespace(via_cdn=False, ip="81.2.69.142")

    def country(self, found):
        with patch.object(geoip, "get_request_location",
                          lambda request, c: found):
            return traffic_counter.visitor_country(self.request, None)

    def test_the_lookups_answer(self):
        self.assertEqual(self.country("gb"), "GB")

    def test_unknown(self):
        self.assertEqual(self.country(None), "")
        self.assertEqual(self.country("not a country"), "")

    def test_no_geoip_service(self):
        del self.g.geoip_location
        self.assertEqual(self.country("GB"), "")

    def test_a_slow_service_is_left_alone_for_a_while(self):
        # (the pause check, the start, the end, the pause; the next check)
        clock = iter([100.0, 100.0, 102.0, 103.0, 104.0])
        with patch.object(traffic_counter.time, "time", lambda: next(clock)):
            self.assertEqual(self.country("GB"), "GB")
            # (paused: asked again, it doesn't look)
            self.assertEqual(self.country("GB"), "")


class TestCountryName(TipprTestCase):
    def test_names(self):
        en = babel.core.Locale.parse("en")
        self.assertEqual(CountryTraffic.get_country_name("DE", en), "Germany")
        self.assertEqual(CountryTraffic.get_country_name("de", en), "Germany")
        self.assertEqual(CountryTraffic.get_country_name("XQ", en), "XQ")
