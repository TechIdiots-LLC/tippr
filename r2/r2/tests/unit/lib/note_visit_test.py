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
"""Account activity: where an account is used from, recorded hourly."""

from unittest.mock import MagicMock, patch

from r2.models import ip
from r2.tests import TipprTestCase


class FakeCache(dict):
    def add(self, key, value, time=0):
        if key in self:
            return False
        self[key] = value
        return True


class TestNoteVisit(TipprTestCase):
    def setUp(self):
        self.recorded = []
        for target, value in (
                ("r2.models.ip.g", MagicMock(gencache=FakeCache())),
                ("r2.models.ip.set_account_ip",
                 lambda *a: self.recorded.append(a[:2]))):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def test_once_an_hour_per_address(self):
        ip.note_visit(7, "8.8.8.8")
        ip.note_visit(7, "8.8.8.8")
        ip.note_visit(7, "1.1.1.1")
        ip.note_visit(8, "8.8.8.8")
        self.assertEqual(self.recorded, [(7, "8.8.8.8"),
                                         (7, "1.1.1.1"),
                                         (8, "8.8.8.8")])

    def test_private_and_bad_addresses_skipped(self):
        for address in ("192.168.1.4", "fd53:e171:17a4:100::1", "127.0.0.1",
                        "not an address"):
            ip.note_visit(7, address)
        self.assertEqual(self.recorded, [])
