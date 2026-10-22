#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from unittest.mock import MagicMock, patch

from r2.lib import releases
from r2.tests import TipprTestCase


def release(tag, prerelease=False, draft=False, installer=True):
    version = tag.lstrip("v")
    assets = [{"name": "SHA256SUMS"}]
    if installer:
        assets.append({"name": "tippr-%s-installer.tar.gz" % version})
    return {"tag_name": tag, "name": tag, "html_url": "https://x/" + tag,
            "published_at": "2026-10-01T00:00:00Z", "prerelease": prerelease,
            "draft": draft, "assets": assets}


class TestVersions(TipprTestCase):
    def test_order(self):
        self.assertTrue(releases.newer("0.15.0", "0.14.0"))
        self.assertTrue(releases.newer("0.14.10", "0.14.9"))
        self.assertTrue(releases.newer("1.0.0", "0.99.99"))
        self.assertFalse(releases.newer("0.14.0", "0.14.0"))
        self.assertTrue(releases.newer("v0.15.0", "0.14.0"))

    def test_prereleases_come_before_their_release(self):
        self.assertTrue(releases.newer("1.2.0", "1.2.0-rc1"))
        self.assertTrue(releases.newer("1.2.0-rc2", "1.2.0-rc1"))
        self.assertTrue(releases.newer("1.2.0-rc10", "1.2.0-rc9"))
        self.assertTrue(releases.newer("1.2.0-rc1", "1.1.9"))

    def test_not_versions(self):
        self.assertIsNone(releases.version_key("master"))
        self.assertIsNone(releases.version_key(""))
        self.assertFalse(releases.newer("1.0.0", None))
        self.assertFalse(releases.newer("1.0.0; rm -rf /", "0.1.0"))


class TestReleases(TipprTestCase):
    def setUp(self):
        cache = {}
        fake_g = MagicMock(config={})
        fake_g.gencache.get.side_effect = cache.get
        fake_g.gencache.set.side_effect = (
            lambda key, value, time=None: cache.__setitem__(key, value))
        p = patch("r2.lib.releases.g", fake_g)
        p.start()
        self.addCleanup(p.stop)

    @patch("r2.lib.releases.requests")
    def test_only_installable_releases_newest_first(self, requests_mock):
        requests_mock.RequestException = Exception
        requests_mock.get.return_value = MagicMock(json=lambda: [
            release("v0.14.0"),
            release("v0.16.0-rc1", prerelease=True),
            release("v0.15.0"),
            release("v0.17.0", draft=True),
            release("v0.18.0", installer=False),
            release("nightly"),
        ])
        found = [r["version"] for r in releases.releases()["releases"]]
        self.assertEqual(found, ["0.16.0-rc1", "0.15.0", "0.14.0"])
        self.assertEqual(releases.latest()["version"], "0.15.0")
        self.assertEqual(releases.latest(prerelease=True)["version"],
                         "0.16.0-rc1")
        # asked once: kept for an hour
        releases.releases()
        self.assertEqual(requests_mock.get.call_count, 1)

    @patch("r2.lib.releases.requests")
    def test_github_down(self, requests_mock):
        requests_mock.RequestException = Exception
        requests_mock.get.side_effect = Exception("timed out")
        info = releases.releases()
        self.assertEqual(info["releases"], [])
        self.assertIn("timed out", info["error"])
        self.assertIsNone(releases.latest())

    def test_repo_setting_must_look_like_one(self):
        with patch("r2.lib.releases.g", MagicMock(config={
                "release_repo": "someone/fork"})):
            self.assertEqual(releases.repo(), "someone/fork")
        with patch("r2.lib.releases.g", MagicMock(config={
                "release_repo": "../../evil"})):
            self.assertEqual(releases.repo(), releases.DEFAULT_REPO)
