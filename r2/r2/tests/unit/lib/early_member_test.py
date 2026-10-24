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
"""Who has a place among the first members."""

import unittest
from unittest import mock

from r2.lib import early_member


def account(id, name=None, **kw):
    props = dict(_id=id, _deleted=False, _spam=False, _banned=False,
                 feed_bot=False, internal_account=False,
                 registration_ip="203.0.113.1")
    props.update(kw)
    a = mock.Mock(**props)
    a.name = name or "member%d" % id
    return a


class EarlyMemberTest(unittest.TestCase):
    def setUp(self):
        self.g = mock.Mock(live_config={"early_member_count": 3},
                           system_user="tippr",
                           automoderator_account="AutoModerator")
        patch = mock.patch.object(early_member, "g", self.g)
        patch.start()
        self.addCleanup(patch.stop)

    def test_site_accounts_take_no_place(self):
        accounts = [account(1, "tippr"), account(2, "AutoModerator"),
                    account(3), account(4, feed_bot=True),
                    account(5, registration_ip="0.0.0.0"),
                    account(6), account(7), account(8)]
        places = early_member.first_members(accounts, 3)
        self.assertEqual([a._id for a in places], [3, 6, 7])

    def test_internal_accounts_take_no_place(self):
        # marked on /admin/users (a test account, a bot)
        accounts = [account(1), account(2, internal_account=True),
                    account(3), account(4)]
        places = early_member.first_members(accounts, 3)
        self.assertEqual([a._id for a in places], [1, 3, 4])

    def test_deleted_keep_their_place(self):
        gone = account(2, _deleted=True)
        accounts = [account(1), gone, account(3), account(4)]
        places = early_member.first_members(accounts, 3)
        self.assertEqual([a._id for a in places], [1, 2, 3])
        self.assertFalse(early_member.can_have(gone))

    def test_count(self):
        self.assertEqual(early_member.count(), 3)
        self.g.live_config = {}
        self.assertEqual(early_member.count(), early_member.DEFAULT_COUNT)
        self.g.live_config = {"early_member_count": 0}
        self.assertEqual(early_member.count(), 0)
        self.assertEqual(early_member.first_members([account(1)], 0), [])
