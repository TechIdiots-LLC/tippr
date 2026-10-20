#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import datetime

from r2.lib import site_info
from r2.tests import TipprTestCase

TODAY = datetime.date(2026, 10, 19)
POLICY = """# Privacy Policy

*Effective Date: January 22, 2026*

*Last Revised: January 22, 2026*

We collect very little.
"""


class TestStampRevised(TipprTestCase):
    def test_new_page_is_dated_today(self):
        text, changed = site_info.stamp_revised(POLICY, None, today=TODAY)
        self.assertTrue(changed)
        self.assertIn("*Last Revised: October 19, 2026*", text)
        # the effective date isn't touched
        self.assertIn("*Effective Date: January 22, 2026*", text)

    def test_changed_text_is_dated_today(self):
        current = POLICY.replace("January 22", "March 3")
        new = POLICY.replace("very little", "almost nothing")
        text, changed = site_info.stamp_revised(new, current, today=TODAY)
        self.assertTrue(changed)
        self.assertIn("*Last Revised: October 19, 2026*", text)

    def test_unchanged_text_keeps_the_sites_date(self):
        current = POLICY.replace("Last Revised: January 22", "Last Revised: March 3")
        text, changed = site_info.stamp_revised(POLICY, current, today=TODAY)
        self.assertFalse(changed)
        self.assertIn("*Last Revised: March 3, 2026*", text)

    def test_single_digit_day(self):
        text, _ = site_info.stamp_revised(
            POLICY, None, today=datetime.date(2026, 11, 5))
        self.assertIn("*Last Revised: November 5, 2026*", text)
