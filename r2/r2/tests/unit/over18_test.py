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
"""Who sees 18+ content (r2.controllers.tippr_base.over18)."""

import types
import unittest
from unittest import mock

from r2.controllers import tippr_base


class Over18Test(unittest.TestCase):
    def over18(self, logged_in, pref=False, admin=False, cookies=None):
        fake_c = types.SimpleNamespace(
            user_is_loggedin=logged_in, user_is_admin=admin,
            user=types.SimpleNamespace(pref_over_18=pref),
            cookies={} if cookies is None else cookies)
        with mock.patch.object(tippr_base, "c", fake_c):
            return tippr_base.over18(), fake_c

    def test_member_who_said_so(self):
        self.assertIs(self.over18(True, pref=True)[0], True)

    def test_member_who_did_not(self):
        self.assertIs(self.over18(True, pref=False)[0], False)

    def test_admin(self):
        self.assertIs(self.over18(True, admin=True)[0], True)

    def test_logged_out(self):
        self.assertIs(self.over18(False)[0], False)

    def test_logged_out_old_cookie_no_longer_counts_and_is_cleared(self):
        old = types.SimpleNamespace(value="1")
        result, fake_c = self.over18(False, cookies={"over18": old})
        self.assertIs(result, False)
        self.assertIsNot(fake_c.cookies["over18"], old)
        self.assertEqual(fake_c.cookies["over18"].value, "")
