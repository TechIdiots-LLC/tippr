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
"""VMultiByPath makes a member's own filter (f/all, f/mod) the first time
they change it, and nothing else."""

import unittest
from unittest.mock import MagicMock, patch

from pylons import tmpl_context as c

from r2.lib.db import tdb_cassandra
from r2.lib.errors import ErrorSet
from r2.lib.validator import VMultiByPath


class TestVMultiByPathCreatesFilters(unittest.TestCase):
    def setUp(self):
        c.user_is_loggedin = True
        c.user = MagicMock()
        c.user.name = "Member"
        c.errors = ErrorSet()
        by_id = patch("r2.lib.validator.validator.LabeledMulti._byID",
                      side_effect=tdb_cassandra.NotFound)
        create = patch("r2.lib.validator.validator.LabeledMulti.create")
        by_id.start()
        self.create = create.start()
        self.addCleanup(by_id.stop)
        self.addCleanup(create.stop)

    def run_validator(self, path, **kw):
        validator = VMultiByPath("multipath", require_edit=True, **kw)
        return validator.run(path)

    def test_own_filter_is_made(self):
        for name in ("all", "mod"):
            self.create.reset_mock()
            result = self.run_validator("/user/member/f/%s" % name)
            self.create.assert_called_once_with("/user/member/f/%s" % name, c.user)
            self.assertIs(result, self.create.return_value)

    def test_not_other_filters_or_others_or_multis(self):
        for path in ("/user/member/f/junk", "/user/someone/f/all", "/user/member/m/all"):
            self.run_validator(path)
        self.run_validator("/user/member/f/all", kinds="m")
        self.create.assert_not_called()

    def test_not_logged_out_or_just_viewing(self):
        VMultiByPath("multipath").run("/user/member/f/all")
        c.user_is_loggedin = False
        self.run_validator("/user/member/f/all")
        self.create.assert_not_called()
