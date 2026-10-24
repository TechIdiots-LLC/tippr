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
"""Counting ads: tracking names, and which /click addresses are let through."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

from r2.lib import ad_traffic
from r2.tests import TipprTestCase


class TestAdTraffic(TipprTestCase):
    def setUp(self):
        p = patch("r2.lib.ad_traffic.g", MagicMock(tracking_secret=b"s3cret"))
        p.start()
        self.addCleanup(p.stop)

    def signed(self, url, name):
        # as r2.lib.promote.add_trackers signs it
        return hmac.new(b"s3cret", (url + name).encode("utf-8"),
                        hashlib.sha1).hexdigest()

    def test_tracking_names(self):
        split = ad_traffic.split_tracking_name
        self.assertEqual(split("t1_ab-t8_cd-books"), ("t1_ab", "t8_cd", "books"))
        self.assertEqual(split("t1_ab-t8_cd"), ("t1_ab", "t8_cd", ""))
        self.assertEqual(split("t1_ab-NO_CAMPAIGN"), ("t1_ab", None, ""))

    def test_scopes(self):
        self.assertEqual(ad_traffic._scopes("click", "clicktarget",
                                            "t1_ab-t8_cd-books"),
                         [("click", "t1_ab"), ("clicktarget", "t8_cd\tbooks")])
        self.assertEqual(ad_traffic._scopes("ad", "adtarget", "t1_ab-NO_CAMPAIGN"),
                         [("ad", "t1_ab")])

    def test_a_signed_click_goes_through(self):
        url, name = "https://example.com/sale?x=1", "t1_ab-t8_cd-books"
        self.assertTrue(ad_traffic.valid_click(url, name, self.signed(url, name)))

    def test_anything_else_doesnt(self):
        url, name = "https://example.com/", "t1_ab-t8_cd"
        good = self.signed(url, name)
        self.assertFalse(ad_traffic.valid_click("https://evil.example/", name, good))
        self.assertFalse(ad_traffic.valid_click(url, "t1_zz-t8_cd", good))
        self.assertFalse(ad_traffic.valid_click(url, name, "0" * 40))
        self.assertFalse(ad_traffic.valid_click(url, name, ""))
        js = "javascript:alert(1)"
        self.assertFalse(ad_traffic.valid_click(js, name, self.signed(js, name)))

    def test_click_hash_matches_add_trackers(self):
        self.assertEqual(ad_traffic.click_hash("https://a.example/", "t1_ab-t8_cd"),
                         self.signed("https://a.example/", "t1_ab-t8_cd"))
