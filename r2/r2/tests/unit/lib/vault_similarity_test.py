#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from r2.lib import vault_similarity
from r2.tests import TipprTestCase

DEFAULT, LINUX, SELFHOSTED, GIS, FOOD = 1, 2, 3, 4, 5


class TestVaultSimilarity(TipprTestCase):
    def test_shared_subscribers_make_vaults_similar(self):
        members = [
            {DEFAULT, LINUX, SELFHOSTED},
            {DEFAULT, LINUX, SELFHOSTED},
            {DEFAULT, LINUX, GIS},
            {DEFAULT, FOOD},
        ]
        similar = vault_similarity.similarities(members)
        # apart from the default everyone is in (which the recommender
        # leaves out), linux's best match is selfhosted: 2 of linux's 3
        # members are in it
        self.assertEqual([b for b, _ in similar[LINUX] if b != DEFAULT][0],
                         SELFHOSTED)
        # food has nothing in common with linux
        self.assertNotIn(FOOD, [b for b, _ in similar[LINUX]])
        # scores are 0..1 and best first
        scores = [s for _, s in similar[LINUX]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0 < s <= 1 for s in scores))

    def test_a_vault_everyone_is_in_isnt_like_everything(self):
        members = [{DEFAULT, LINUX, SELFHOSTED}] * 3 + [{DEFAULT, FOOD}] * 20
        similar = vault_similarity.similarities(members)
        # selfhosted is far more like linux than like the default, which
        # everyone is in
        scores = dict(similar[SELFHOSTED])
        self.assertGreater(scores[LINUX], scores[DEFAULT])

    def test_symmetric_and_skips_empty_and_huge_lists(self):
        too_many = set(range(100, 100 + vault_similarity.MAX_SUBSCRIPTIONS + 1))
        similar = vault_similarity.similarities([set(), too_many, {LINUX, GIS}])
        self.assertEqual(dict(similar[LINUX]), {GIS: 1.0})
        self.assertEqual(dict(similar[GIS]), {LINUX: 1.0})
        self.assertNotIn(100, similar)
