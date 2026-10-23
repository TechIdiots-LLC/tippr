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
"""Column slicing in cassandra_compat matches pycassa's get/multiget."""

import unittest
from collections import OrderedDict

from r2.lib.db.cassandra_compat import NotFoundException, _slice_columns


def row():
    return OrderedDict((name, name.upper()) for name in ("a", "b", "c", "d"))


class SliceColumnsTest(unittest.TestCase):
    def test_forward_range(self):
        self.assertEqual(list(_slice_columns(row(), column_start="b",
                                             column_finish="c")), ["b", "c"])

    def test_reversed_start_is_the_high_end(self):
        # the newest column at or before "c", as GoldRevenueGoalByDate.get asks
        self.assertEqual(list(_slice_columns(row(), column_start="c",
                                             column_reversed=True,
                                             column_count=1)), ["c"])
        self.assertEqual(list(_slice_columns(row(), column_start="c",
                                             column_finish="b",
                                             column_reversed=True)),
                         ["c", "b"])

    def test_empty_bounds_are_no_bound(self):
        self.assertEqual(list(_slice_columns(row(), column_start="",
                                             column_finish="")),
                         ["a", "b", "c", "d"])

    def test_columns_and_count(self):
        self.assertEqual(list(_slice_columns(row(), columns=["d", "b", "x"])),
                         ["d", "b"])
        self.assertEqual(list(_slice_columns(row(), column_reversed=True,
                                             column_count=2)), ["d", "c"])


class GetTest(unittest.TestCase):
    def test_empty_slice_is_not_found(self):
        from unittest import mock
        from r2.lib.db import cassandra_compat

        cf = cassandra_compat.ColumnFamily.__new__(cassandra_compat.ColumnFamily)
        cf.keyspace, cf.table = "ks", "t"
        stored = {name: cassandra_compat.pickle.dumps((value, 1))
                  for name, value in row().items()}
        cf.session = mock.Mock()
        cf.session.execute.return_value.one.return_value = mock.Mock(
            columns=stored)
        self.assertEqual(list(cf.get("k", column_start="c",
                                     column_reversed=True)), ["c", "b", "a"])
        with self.assertRaises(NotFoundException):
            cf.get("k", column_start="0", column_reversed=True)
