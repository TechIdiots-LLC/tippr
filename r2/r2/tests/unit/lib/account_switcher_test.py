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
"""Who gets the account switcher: gold members and admins."""

from types import SimpleNamespace

from r2.tests import TipprTestCase


def account(name="someone", gold=False, mod=False):
    return SimpleNamespace(name=name, gold=gold, is_moderator_somewhere=mod)


class TestAccountSwitcherAllowed(TipprTestCase):
    def setUp(self):
        super().setUp()
        # imported here: at collection it would load the models before the
        # test setup mocks the database
        from r2.lib import account_switcher
        self.switcher = account_switcher
        self.c = self.autopatch(account_switcher, "c")
        self.c.user_is_loggedin = True
        self.kept = self.autopatch(account_switcher, "_kept", return_value=[])
        self.patch_g(admins=["boss"])

    def test_who_qualifies(self):
        self.assertTrue(self.switcher.qualifies(account(gold=True)))
        self.assertTrue(self.switcher.qualifies(account(name="boss")))
        # moderating is per vault (anyone can start one), so it doesn't count
        self.assertFalse(self.switcher.qualifies(account(mod=True)))
        self.assertFalse(self.switcher.qualifies(account()))

    def test_the_account_in_use(self):
        self.c.user = account(gold=True)
        self.assertTrue(self.switcher.allowed())
        self.c.user = account()
        self.assertFalse(self.switcher.allowed())

    def test_a_kept_account_counts(self):
        # switched to an alt without gold: the gold account kept in the
        # switcher still lets them switch back
        self.c.user = account()
        self.kept.return_value = [(account("alt"), "s1"), (account("main", gold=True), "s2")]
        self.assertTrue(self.switcher.allowed())
        self.kept.return_value = [(account("alt"), "s1")]
        self.assertFalse(self.switcher.allowed())

    def test_not_logged_in(self):
        self.c.user_is_loggedin = False
        self.assertFalse(self.switcher.allowed())
