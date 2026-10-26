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
"""Media addresses back to their bucket and key, for deleting media."""

from types import SimpleNamespace
from unittest.mock import patch

from r2.lib import object_storage
from r2.tests import TipprTestCase


class TestBucketAndKey(TipprTestCase):
    def use(self, **config):
        fake_g = SimpleNamespace(config=config, **config)
        p = patch("r2.lib.object_storage.g", fake_g)
        p.start()
        self.addCleanup(p.stop)

    def test_the_bucket_list_comes_parsed(self):
        # the ini's s3_media_buckets is a tuple by the time the app reads it
        self.use(s3_media_buckets=("tippr-media",),
                 s3_public_url="https://example.com/media/")
        self.assertEqual(object_storage.configured_buckets(), ["tippr-media"])
        self.assertEqual(
            object_storage.bucket_and_key("https://example.com/media/a.png"),
            ("tippr-media", "a.png"))

    def test_or_as_text(self):
        self.use(s3_media_buckets="one, two",
                 s3_client_uploads_bucket="two")
        self.assertEqual(object_storage.configured_buckets(), ["one", "two"])

    def test_other_addresses_are_not_ours(self):
        self.use(s3_media_buckets=("tippr-media",),
                 s3_public_url="https://example.com/media/")
        self.assertEqual(
            object_storage.bucket_and_key("https://elsewhere.org/media/a.png"),
            (None, None))
