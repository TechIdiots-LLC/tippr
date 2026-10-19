#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from r2.models import Account
from r2.tests import TipprTestCase


class TestHasSubscribed(TipprTestCase):
    def test_defaults_to_false(self):
        self.assertFalse(Account(name="new_account").has_subscribed)

    def test_reads_the_stored_value(self):
        # loaded from the database with the flag set
        account = Account(name="subscriber")
        account._t["has_subscribed"] = True
        self.assertTrue(account.has_subscribed)

    def test_setting_it_sticks(self):
        account = Account(name="subscriber")
        account.has_subscribed = True
        self.assertTrue(account.has_subscribed)
        self.assertTrue(account._t["has_subscribed"])
