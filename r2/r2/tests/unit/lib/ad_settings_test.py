#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""Which pages may show ads (r2.lib.ad_settings.ads_allowed_here)."""

from types import SimpleNamespace
from unittest.mock import patch

from r2.lib import ad_settings
from r2.tests import TipprTestCase


class TestAdsAllowedHere(TipprTestCase):
    def allowed(self, path="/v/pics/", admin_page=""):
        c = SimpleNamespace(admin_page=admin_page, user_is_loggedin=False,
                            site=SimpleNamespace(allow_ads=True, over_18=False))
        with patch.object(ad_settings, "c", c), \
                patch.object(ad_settings, "request", SimpleNamespace(path=path)), \
                patch.object(ad_settings, "g", SimpleNamespace(disable_ads=False)):
            return ad_settings.ads_allowed_here()

    def test_ordinary_pages(self):
        self.assertTrue(self.allowed())

    def test_never_on_admin_pages(self):
        self.assertFalse(self.allowed("/admin/feeds"))
        self.assertFalse(self.allowed("/admin"))
        # (an AdminPage wherever it's served)
        self.assertFalse(self.allowed("/elsewhere", admin_page=True))
