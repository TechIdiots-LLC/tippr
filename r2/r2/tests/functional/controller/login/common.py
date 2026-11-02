# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2016 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################
import contextlib
from unittest.mock import MagicMock, patch

from r2.lib import antispam
from r2.lib.validator import VThrottledLogin, VUname
from r2.models import Account, NotFound


class LoginRegBase:
    """Mixin for login-centered controller tests.

    This class is (purposely) not a test case that'll be picked up by nose
    but rather should be added as a mixin on a TipprControllerTestCase
    subclass. The subclass needs to implement

     * assert_success - passed a result of do_post, and invoked in places
       where we expect the request to have succeeded
     * assert_failure - same, for failed and error cases from the server.

    Included are base test cases that should be common to all controllers
    which use r2.lib.controlers.login as part of the flow.
    """
    def do_login(self, user="test", passwd="test123", **kw):
        return self.do_post("login", {"user": user, "passwd": passwd}, **kw)

    def do_register(
        self, user="test", passwd="test123", passwd2="test123", **kw
    ):
        return self.do_post("register", {
            "user": user,
            "passwd": passwd,
            "passwd2": passwd2,
        }, **kw)

    @staticmethod
    def mock_account(name="test", cookie="cookievaluehere"):
        """A stand-in account, logged in with cookie."""
        account = MagicMock()
        account.name = name
        account.make_cookie.return_value = cookie
        account.modhash.return_value = "modhashvaluehere"
        # without two-factor (a MagicMock's attributes are all truthy, so it
        # would look like an account with it, sent to /logins/otp)
        account.otp_secret = ""
        account.two_factor_methods = 0
        return account

    def mock_login(self, name="test", cookie="cookievaluehere"):
        """Context manager for mocking login.

        Patches VThrottledLogin to always return a mock with the provided
        name and cookie value
        """
        return patch.object(VThrottledLogin, "run",
                            return_value=self.mock_account(name, cookie))

    def mock_register(self, check_name=False):
        """Context manager for mocking out registration.

        Within this context, new users can be registered but they will
        be mock objects.  Also all usernames can be registered as the account
        lookup is bypassed and Account._by_name always raises NotFound.
        check_name: the username goes through VUname's checks (length,
        characters, reserved names) instead of always passing. The
        context's value is the mocked register, to see whether an account
        was made.
        """
        from r2.controllers import login
        stack = contextlib.ExitStack()
        registered = stack.enter_context(patch.object(
            login, "register", return_value=self.mock_account()))
        if not check_name:
            stack.enter_context(patch.object(VUname, "run", return_value="test"))
        # ensure this user does not currently exist
        stack.enter_context(patch.object(Account, "_by_name", side_effect=NotFound))
        # no sign-up captcha (failed_captcha turns it back on)
        stack.enter_context(patch.object(antispam, "captcha_on_register",
                                         return_value=False))
        # nothing goes to CleanTalk
        stack.enter_context(patch.object(antispam, "check_signup",
                                         return_value=(True, None)))
        stack.registered = registered
        return stack

    def failed_captcha(self):
        """Context manager for mocking a failed captcha."""
        stack = contextlib.ExitStack()
        # ensure that a captcha is needed (r2.lib.antispam, VCaptcha)
        stack.enter_context(patch.object(
            antispam, "captcha_on_register", return_value=True))
        # ensure that the captcha is invalid
        stack.enter_context(patch.object(
            antispam, "verify_captcha", return_value=False))
        return stack

    def disabled_captcha(self):
        """Context manager for mocking a disabled captcha.

        Will raise an AssertionError if the captcha code is called.
        """
        stack = contextlib.ExitStack()
        # ensure that a captcha is not needed
        stack.enter_context(patch.object(
            antispam, "captcha_on_register", return_value=False))
        # ensure that the captcha is unused
        stack.enter_context(patch.object(
            antispam, "verify_captcha", side_effect=AssertionError))
        return stack

    def find_headers(self, res, name):
        """Find header in res"""
        for value in res.headers.getall(name):
            yield value

    def assert_headers(self, res, name, test):
        """Assert header value with test (lambda function or value)"""
        for value in self.find_headers(res, name):
            if callable(test) and test(value):
                return
            elif value == test:
                return
        raise AssertionError("No matching %s header found" % name)

    def assert_success(self, res):
        """Test that is run when we expect the post to succeed."""
        raise NotImplementedError

    def assert_failure(self, res, code=None):
        """Test that is run when we expect the post to fail."""
        raise NotImplementedError

    def test_login(self):
        with self.mock_login():
            res = self.do_login()
            self.assert_success(res)

    def test_login_wrong_password(self):
        with patch.object(Account, "_by_name", side_effect=NotFound):
            res = self.do_login()
            self.assert_failure(res, "WRONG_PASSWORD")

    def test_register(self):
        with self.mock_register():
            res = self.do_register()
            self.assert_success(res)

    def test_register_username_taken(self):
        with patch.object(
            Account, "_by_name", return_value=MagicMock(_deleted=False)
        ):
            res = self.do_register()
            self.assert_failure(res, "USERNAME_TAKEN")

    def assert_refused(self, code, user="test", passwd2="test123",
                       patches=()):
        """A sign-up refused with code, and no account made. patches:
        [(object, attribute, return value)] for the attempt."""
        with contextlib.ExitStack() as stack:
            mocked = stack.enter_context(self.mock_register(check_name=True))
            for target, attribute, value in patches:
                stack.enter_context(patch.object(target, attribute,
                                                 return_value=value))
            res = self.do_register(user=user, passwd2=passwd2)
            self.assert_failure(res, code)
            self.assertFalse(mocked.registered.called)

    def test_register_with_the_names_checked(self):
        with self.mock_register(check_name=True) as mocked:
            res = self.do_register(user="hannah_b")
            self.assert_success(res)
            self.assertTrue(mocked.registered.called)

    def test_register_reserved_name(self):
        # names that would pass for staff (r2.lib.reserved_names)
        for name in ("admin", "Tippr_Mod", "adm1n", "SupportTeam"):
            self.assert_refused("USERNAME_RESERVED", user=name)

    def test_register_invalid_characters(self):
        self.assert_refused("USERNAME_INVALID_CHARACTERS", user="bad!name")

    def test_register_passwords_differ(self):
        self.assert_refused("BAD_PASSWORD_MATCH", passwd2="something-else")

    def test_register_signups_closed(self):
        from r2.lib import site_info
        self.assert_refused("SIGNUPS_CLOSED",
                            patches=[(site_info, "signups_open", False)])

    def test_register_spam(self):
        # CleanTalk says no (r2.lib.antispam)
        self.assert_refused("SPAM_SIGNUP", patches=[
            (antispam, "check_signup", (False, "spam"))])

    def test_captcha_blocking(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(self.mock_register())
            stack.enter_context(self.failed_captcha())
            res = self.do_register()
            self.assert_failure(res, "BAD_CAPTCHA")

    def test_captcha_disabling(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(self.mock_register())
            stack.enter_context(self.disabled_captcha())
            res = self.do_register()
            self.assert_success(res)
