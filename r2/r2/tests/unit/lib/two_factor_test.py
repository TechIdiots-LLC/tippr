#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import time
from unittest.mock import MagicMock, patch

from r2.lib import two_factor
from r2.tests import TipprTestCase


class FakeCache(dict):
    def set(self, key, value, time=None):
        self[key] = value

    def delete(self, key):
        self.pop(key, None)


class TestTwoFactor(TipprTestCase):
    def setUp(self):
        self.cache = FakeCache()
        self.g = MagicMock(gencache=self.cache, login_cookie="session",
                           secrets={"SECRET": "s3cret"}, live_config={},
                           disable_ratelimit=True, admins=["admin"])
        self.request = MagicMock(cookies={"session": "abc"},
                                 user_agent="test-browser")
        self.c = MagicMock(oauth_user=None, cookies={})
        for target, value in (("r2.lib.two_factor.g", self.g),
                              ("r2.lib.two_factor.request", self.request),
                              ("r2.lib.two_factor.c", self.c)):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.account = MagicMock(_id=7, _id36="7", otp_secret="SECRET",
                                 password="hash", otp_recovery_codes=[],
                                 pref_otp_login=False, pref_otp_settings=False,
                                 pref_otp_post=False, two_factor_methods=0,
                                 two_factor_stamp="")
        self.account.name = "member"

    def test_always_asked_actions(self):
        self.assertTrue(two_factor.needs_code(self.account, "password"))
        self.assertTrue(two_factor.needs_code(self.account, "linked_logins"))
        # the optional ones only when chosen
        self.assertFalse(two_factor.needs_code(self.account, "post"))
        self.account.pref_otp_post = True
        self.assertTrue(two_factor.needs_code(self.account, "post"))

    def test_without_two_factor_nothing_is_asked(self):
        self.account.otp_secret = ""
        self.assertFalse(two_factor.needs_code(self.account, "password"))

    def test_apps_are_not_asked(self):
        self.c.oauth_user = MagicMock()
        self.assertFalse(two_factor.needs_code(self.account, "password"))

    def test_a_code_counts_for_this_session_only(self):
        two_factor.mark_recent(self.account)
        self.assertFalse(two_factor.needs_code(self.account, "password"))
        self.request.cookies = {"session": "another-login"}
        self.assertTrue(two_factor.needs_code(self.account, "password"))

    def test_authenticator_secrets_are_sealed(self):
        sealed = two_factor._seal("JBSWY3DPEHPK3PXP", 7)
        self.assertTrue(sealed.startswith(two_factor._SEALED))
        self.assertNotIn("JBSWY3DPEHPK3PXP", sealed)
        self.assertEqual(two_factor._open(sealed, 7), "JBSWY3DPEHPK3PXP")
        # each sealing differs (a fresh nonce)
        self.assertNotEqual(sealed, two_factor._seal("JBSWY3DPEHPK3PXP", 7))
        # bound to the account, and to the site's SECRET
        with self.assertRaises(Exception):
            two_factor._open(sealed, 8)
        self.g.secrets = {"SECRET": "another"}
        with self.assertRaises(Exception):
            two_factor._open(sealed, 7)
        # secrets kept before sealing still read
        self.assertEqual(two_factor._open("JBSWY3DPEHPK3PXP", 7),
                         "JBSWY3DPEHPK3PXP")

    def test_minutes_left(self):
        self.assertEqual(two_factor.recent_minutes_left(self.account), 0)
        two_factor.mark_recent(self.account)
        self.assertEqual(two_factor.recent_minutes_left(self.account),
                         two_factor.RECENT_MINUTES)
        key = two_factor._session_key(self.account)
        self.cache[key] = int(time.time()) + 61
        self.assertEqual(two_factor.recent_minutes_left(self.account), 2)
        self.cache[key] = int(time.time()) - 5   # not yet expired from cache
        self.assertEqual(two_factor.recent_minutes_left(self.account), 1)

    def test_recovery_codes_work_once(self):
        codes = two_factor.new_recovery_codes(self.account)
        self.assertEqual(len(codes), two_factor.RECOVERY_CODES)
        self.assertNotIn(codes[0], self.account.otp_recovery_codes)
        self.assertTrue(two_factor.use_recovery_code(self.account,
                                                     codes[0].upper()))
        self.assertFalse(two_factor.use_recovery_code(self.account, codes[0]))
        self.assertEqual(two_factor.recovery_codes_left(self.account),
                         two_factor.RECOVERY_CODES - 1)
        # new codes replace the old ones
        two_factor.new_recovery_codes(self.account)
        self.assertFalse(two_factor.use_recovery_code(self.account, codes[1]))

    def test_remembered_device(self):
        self.account.pref_otp_login = True
        self.assertTrue(two_factor.login_needs_code(self.account))
        cookies = MagicMock(Cookie=lambda **kw: MagicMock(**kw))
        with patch.dict("sys.modules", {"r2.lib.cookies": cookies}):
            two_factor.remember_device(self.account)
        cookie = self.c.cookies[two_factor.device_cookie_name(self.account)]
        self.request.cookies = {two_factor.device_cookie_name(self.account):
                                cookie.value}
        self.assertFalse(two_factor.login_needs_code(self.account))
        # a new password (or secret) forgets the devices
        self.account.password = "new-hash"
        self.assertTrue(two_factor.login_needs_code(self.account))

    def test_remembered_device_expires(self):
        self.account.pref_otp_login = True
        old = str(int(time.time()) - (two_factor.DEVICE_DAYS + 1) * 86400)
        value = "%s.%s" % (old, two_factor._device_signature(self.account, old))
        self.request.cookies = {two_factor.device_cookie_name(self.account):
                                value}
        self.assertTrue(two_factor.login_needs_code(self.account))

    def test_staff_requirement(self):
        self.account.otp_secret = ""
        self.assertFalse(two_factor.staff_tools_closed(self.account))
        self.g.live_config = {"require_two_factor_staff": True}
        self.assertTrue(two_factor.staff_tools_closed(self.account))
        self.account.otp_secret = "SECRET"
        self.assertFalse(two_factor.staff_tools_closed(self.account))
