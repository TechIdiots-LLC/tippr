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
"""The optional queues (comment tree fast lane, sharded queues) are used
only while a consumer is taking items from them."""

import unittest
from unittest import mock

from r2.lib import amqp


class FakeCache:
    def __init__(self):
        self.data = {}

    def set(self, key, value, time=0):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)


class HeartbeatTest(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        cfg = mock.Mock(cache=self.cache)
        patches = [
            mock.patch.object(amqp, "cfg", cfg),
            mock.patch.object(amqp, "_heartbeats", {}),
            mock.patch.object(amqp, "_consumer_seen", {}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_no_consumer_until_a_heartbeat(self):
        self.assertFalse(amqp.has_consumer("commentstree_fastlane_q"))
        amqp._consumer_seen.clear()
        amqp._heartbeat("commentstree_fastlane_q")
        self.assertTrue(amqp.has_consumer("commentstree_fastlane_q"))
        self.assertFalse(amqp.has_consumer("commentstree_3_q"))

    def test_heartbeats_are_throttled(self):
        amqp._heartbeat("author_query_2_q")
        self.cache.data.clear()
        amqp._heartbeat("author_query_2_q")
        self.assertEqual(self.cache.data, {})

    def test_answer_is_remembered(self):
        self.assertFalse(amqp.has_consumer("vault_query_1_q"))
        amqp._heartbeat("vault_query_1_q")
        # memcache is asked again only after HEARTBEAT_SECONDS
        self.assertFalse(amqp.has_consumer("vault_query_1_q"))

    def test_cache_errors_mean_no_consumer(self):
        self.cache.get = mock.Mock(side_effect=OSError)
        self.assertFalse(amqp.has_consumer("domain_query_5_q"))


class ShardQueueNameTest(unittest.TestCase):
    def test_instances_map_to_shards(self):
        try:
            from r2.lib.voting import query_shard_queue
        except Exception as e:  # models can't load without a database
            self.skipTest("r2.lib.voting doesn't import here: %r" % e)
        self.assertEqual(query_shard_queue("author", 1), "author_query_0_q")
        self.assertEqual(query_shard_queue("domain", "10"),
                         "domain_query_9_q")
