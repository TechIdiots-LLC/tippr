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
"""VFreshTwoFactor: deleting an account or turning two-factor off needs
two-factor confirmed a few minutes ago, or a code with the request."""

import unittest
from unittest.mock import MagicMock, patch

from pylons import tmpl_context as c

from r2.lib.errors import ErrorSet, errors
from r2.lib.validator import VFreshTwoFactor


class TestVFreshTwoFactor(unittest.TestCase):
    def setUp(self):
        c.user_is_loggedin = True
        c.user = MagicMock()
        c.errors = ErrorSet()
        self.confirmed = patch("r2.lib.two_factor.confirmed", return_value=False)
        self.check_code = patch("r2.lib.two_factor.check_code", return_value=False)
        self.confirmed_mock = self.confirmed.start()
        self.check_code_mock = self.check_code.start()
        self.addCleanup(self.confirmed.stop)
        self.addCleanup(self.check_code.stop)

    def run_validator(self, code):
        validator = VFreshTwoFactor("otp")
        validator.run(code)
        return bool(c.errors.get((errors.CONFIRM_AGAIN, "otp")))

    def test_confirmed_lately_passes(self):
        self.confirmed_mock.return_value = True
        self.assertFalse(self.run_validator(None))
        self.confirmed_mock.assert_called_with(c.user, fresh_only=True)

    def test_otherwise_it_asks_to_confirm_again(self):
        self.assertTrue(self.run_validator(None))

    def test_a_code_with_the_request_counts(self):
        self.check_code_mock.return_value = True
        self.assertFalse(self.run_validator("123456"))

    def test_a_wrong_code_doesnt(self):
        self.assertTrue(self.run_validator("000000"))

    def test_logged_out_isnt_its_business(self):
        c.user_is_loggedin = False
        self.assertFalse(self.run_validator(None))
