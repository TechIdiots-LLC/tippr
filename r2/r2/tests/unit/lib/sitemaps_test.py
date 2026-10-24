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
"""The complete sitemaps (r2.lib.sitemaps.complete)."""

import unittest
from unittest import mock

from r2.lib.sitemaps import complete, live


class FakeCache(dict):
    def set(self, key, value, time=None):
        self[key] = value

    def delete(self, key):
        self.pop(key, None)


class CompleteSitemapsTest(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        g = mock.Mock(permacache=self.cache,
                      https_endpoint="https://site.example")
        for target in ("r2.lib.sitemaps.complete.g",
                       "r2.lib.sitemaps.live.g"):
            patch = mock.patch(target, g)
            patch.start()
            self.addCleanup(patch.stop)
        self.posts = [("/v/a/comments/%d/x/" % i, None) for i in range(7)]
        for name, value in (
                ("listable_vaults", lambda: iter([("/v/a/", None)])),
                ("listable_posts", lambda: iter(self.posts)),
                ("URLS_PER_SITEMAP", 3)):
            target = complete if name == "URLS_PER_SITEMAP" else live
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_nothing_until_built(self):
        self.assertIsNone(complete.get("index"))
        self.assertIsNone(complete.built())

    def test_split_and_listed(self):
        complete.build()
        self.assertEqual(complete.part_names(),
                         ["vaults-1", "posts-1", "posts-2", "posts-3"])
        index = complete.get("index")
        self.assertIn("https://site.example/sitemaps/posts-3.xml", index)
        self.assertIn("/v/a/comments/6/x/", complete.get("posts-3"))
        self.assertEqual(complete.status()["urls"], 8)
        self.assertIsNone(complete.get("posts-4"))

    def test_parts_no_longer_needed_go(self):
        complete.build()
        self.posts = self.posts[:2]
        complete.build()
        self.assertEqual(complete.part_names(), ["vaults-1", "posts-1"])
        self.assertNotIn(complete._key("posts-3"), self.cache)


class ListableVaultsTest(unittest.TestCase):
    def test_front_page_first(self):
        books = mock.Mock(type="public", _spam=False, over_18=False,
                          quarantine=False)
        books.name = "books"
        nsfw = mock.Mock(type="public", _spam=False, over_18=True,
                         quarantine=False)
        nsfw.name = "nsfw"
        with mock.patch.object(live, "_vaults",
                               return_value=iter([books, nsfw])):
            paths = [path for path, _ in live.listable_vaults()]
        self.assertEqual(paths[:3], ["/", "/vaults/", "/help/"])
        for path in ("/help/faq/", "/help/formatting/",
                     "/help/privacypolicy/", "/help/useragreement/"):
            self.assertIn(path, paths)
        # then the vaults, without the NSFW one
        self.assertEqual(paths[-1], "/v/books/")
        self.assertNotIn("/v/nsfw/", paths)
