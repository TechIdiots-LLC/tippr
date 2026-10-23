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
"""Thread "here now" counts (r2.lib.activity)."""

import contextlib
import unittest
from unittest import mock

from thrift.transport.TTransport import TTransportException

from r2.lib import activity


class HereNowTest(unittest.TestCase):
    def service(self, count=3, fuzzed=True):
        svc = mock.Mock()
        svc.count_activity.return_value = mock.Mock(count=count,
                                                    is_fuzzed=fuzzed)
        svc.retrying.return_value = contextlib.nullcontext(svc)
        return svc

    def test_records_then_counts(self):
        svc = self.service()
        with mock.patch.object(activity, "_activity_service", return_value=svc):
            self.assertEqual(activity.here_now("t1_ab", "t2_me"), (3, True))
        svc.record_activity.assert_called_once_with("t1_ab", "t2_me")
        svc.count_activity.assert_called_once_with("t1_ab")

    def test_no_visitor_only_counts(self):
        svc = self.service()
        with mock.patch.object(activity, "_activity_service", return_value=svc):
            activity.here_now("t1_ab", None)
        svc.record_activity.assert_not_called()

    def test_service_down(self):
        svc = self.service()
        svc.count_activity.side_effect = TTransportException()
        with mock.patch.object(activity, "_activity_service", return_value=svc):
            self.assertIsNone(activity.here_now("t1_ab", "t2_me"))
        with mock.patch.object(activity, "_activity_service", return_value=None):
            self.assertIsNone(activity.here_now("t1_ab", "t2_me"))

    def test_visitor_ids(self):
        user = mock.Mock(_fullname="t2_me")
        self.assertEqual(activity.visitor_id(user, True, None), "t2_me")
        self.assertEqual(
            activity.visitor_id(None, False, mock.Mock(loid="AbC123")), "AbC123")
        self.assertIsNone(activity.visitor_id(None, False, None))
