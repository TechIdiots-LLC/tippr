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
                         ["b", "d"])  # comparator order, as pycassa
        self.assertEqual(list(_slice_columns(row(), column_reversed=True,
                                             column_count=2)), ["d", "c"])


class GetTest(unittest.TestCase):
    def test_empty_slice_is_not_found(self):
        from unittest import mock
        from r2.lib.db import cassandra_compat

        cf = cassandra_compat.ColumnFamily.__new__(cassandra_compat.ColumnFamily)
        cf.keyspace, cf.table = "ks", "t"
        cf.comparator_kind = "text"
        stored = {name: cassandra_compat.pickle.dumps((value, 1))
                  for name, value in row().items()}
        cf.session = mock.Mock()
        cf.session.execute.return_value.one.return_value = mock.Mock(
            columns=stored)
        self.assertEqual(list(cf.get("k", column_start="c",
                                     column_reversed=True)), ["c", "b", "a"])
        with self.assertRaises(NotFoundException):
            cf.get("k", column_start="0", column_reversed=True)


class ComparatorOrderTest(unittest.TestCase):
    """Names are stored as text; the comparator puts them back in order."""

    def test_time_uuids_in_time_order(self):
        import uuid
        from r2.lib.db.cassandra_compat import (
            TIME_UUID_TYPE, comparator_kind, decode_name)
        kind = comparator_kind(TIME_UUID_TYPE)
        # uuid1s a few minutes apart: their text starts with the low bits
        # of the time, so text order isn't time order
        base = uuid.uuid1()
        names = [uuid.UUID(fields=((base.time_low + step) & 0xffffffff,) +
                           base.fields[1:]) for step in (0, 1 << 30, 2 << 30)]
        stored = OrderedDict(
            (decode_name(kind, str(n)), i) for i, n in
            sorted(enumerate(names), key=lambda t: str(t[1])))
        newest_first = _slice_columns(stored, column_reversed=True,
                                      kind=kind)
        self.assertEqual(
            [n.time for n in newest_first],
            sorted((n.time for n in names), reverse=True))
        self.assertTrue(all(isinstance(n, uuid.UUID) for n in newest_first))

    def test_numbers_in_number_order(self):
        from r2.lib.db.cassandra_compat import LongType, comparator_kind
        kind = comparator_kind(LongType())
        stored = OrderedDict((name, "") for name in (10, 9, 100))
        self.assertEqual(list(_slice_columns(stored, column_reversed=True,
                                             column_count=2, kind=kind)),
                         [100, 10])

    def test_dates_and_bounds(self):
        import datetime
        from r2.lib.db.cassandra_compat import (
            DATE_TYPE, comparator_kind, decode_name)
        kind = comparator_kind(DATE_TYPE)
        utc = datetime.timezone.utc
        days = [datetime.datetime(2026, 1, d, tzinfo=utc) for d in (3, 1, 2)]
        stored = OrderedDict((decode_name(kind, str(d)), "") for d in days)
        self.assertEqual(
            [d.day for d in _slice_columns(
                stored, column_start=datetime.datetime(2026, 1, 2, tzinfo=utc),
                column_reversed=True, kind=kind)],
            [2, 1])

    def test_composite_names(self):
        from r2.lib.db.cassandra_compat import (
            CompositeType, AsciiType, comparator_kind, decode_name)
        kind = comparator_kind(CompositeType(AsciiType(), AsciiType()))
        self.assertEqual(decode_name(kind, "('a', 'b')"), ("a", "b"))
