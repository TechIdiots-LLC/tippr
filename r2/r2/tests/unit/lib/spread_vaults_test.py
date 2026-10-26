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
"""/v/all's hot list with runs of one vault spread out."""

from r2.lib.normalized_hot import spread_vaults
from r2.tests import TipprTestCase


class TestSpreadVaults(TipprTestCase):
    def test_a_run_of_one_vault_is_broken_up(self):
        links = [("s%d" % i, "sports") for i in range(6)] + [
            ("n1", "news"), ("t1", "tech"), ("n2", "news")]
        self.assertEqual(spread_vaults(links),
                         ["s0", "n1", "s1", "t1", "s2", "n2",
                          "s3", "s4", "s5"])

    def test_order_kept_when_already_mixed(self):
        links = [("a", 1), ("b", 2), ("c", 1), ("d", 3)]
        self.assertEqual(spread_vaults(links), ["a", "b", "c", "d"])

    def test_nothing_pulled_from_beyond_the_window(self):
        links = [("s%d" % i, "sports") for i in range(5)] + [("n", "news")]
        self.assertEqual(spread_vaults(links, window=3),
                         ["s0", "s1", "s2", "n", "s3", "s4"])

    def test_every_post_kept(self):
        links = [(str(i), i % 3 == 0) for i in range(50)]
        self.assertEqual(sorted(spread_vaults(links)),
                         sorted(name for name, _ in links))
