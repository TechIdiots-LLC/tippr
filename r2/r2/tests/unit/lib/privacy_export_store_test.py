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
"""Data exports kept in the database: saved, read back, cleared when old."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import sqlalchemy as sa

from r2.lib import privacy_export_store as store
from r2.tests import TipprTestCase


class TestPrivacyExportStore(TipprTestCase):
    def setUp(self):
        self.engine = sa.create_engine("sqlite://")
        self.table = store._exports_table(sa.MetaData())
        self.table.create(self.engine)
        for target, value in (("r2.lib.privacy_export_store._db",
                               {"engine": self.engine, "table": self.table}),
                              ("r2.lib.privacy_export_store.g",
                               MagicMock(tz=timezone.utc))):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def test_save_and_load(self):
        store.save("token-1", b"PK\x03\x04zip bytes")
        self.assertEqual(store.load("token-1"), b"PK\x03\x04zip bytes")
        self.assertIsNone(store.load("someone-else"))

    def test_old_exports_are_cleared(self):
        with self.engine.begin() as conn:
            conn.execute(self.table.insert().values(
                token="old", data=b"old",
                created=datetime.now(timezone.utc) - timedelta(days=9)))
        store.save("new", b"new")
        self.assertIsNone(store.load("old"))
        self.assertEqual(store.load("new"), b"new")
