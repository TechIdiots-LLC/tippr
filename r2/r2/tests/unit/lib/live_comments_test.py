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
"""Live comments need both the site's and the vault's switch."""

import unittest
from unittest import mock

from r2.lib import live_comments


class LiveCommentsTest(unittest.TestCase):
    def setUp(self):
        self.g = mock.Mock(live_config={"live_comments": True})
        patch = mock.patch.object(live_comments, "g", self.g)
        patch.start()
        self.addCleanup(patch.stop)

    def test_both_switches(self):
        vault = mock.Mock(live_comments=True)
        self.assertTrue(live_comments.enabled_for(vault))
        vault.live_comments = False
        self.assertFalse(live_comments.enabled_for(vault))
        vault.live_comments = True
        self.g.live_config = {"live_comments": False}
        self.assertFalse(live_comments.enabled_for(vault))
        self.assertFalse(live_comments.enabled_for(None))

    def test_viewer_choice(self):
        member = mock.Mock(pref_live_comments=False)
        self.assertFalse(live_comments.viewer_wants(member, True))
        member.pref_live_comments = True
        self.assertTrue(live_comments.viewer_wants(member, True))
        # logged out: what new accounts start with
        self.assertTrue(live_comments.viewer_wants(None, False))
        self.g.live_config["live_comments_new_user_default"] = False
        self.assertFalse(live_comments.viewer_wants(None, False))

    def test_no_page_config_for_closed_threads(self):
        vault = mock.Mock(live_comments=True)
        link = mock.Mock(_id36="ab", _fullname="t1_ab", locked=True)
        link.is_archived.return_value = False
        self.assertIsNone(live_comments.page_config(link, vault, "new"))
        link.locked = False
        link.is_archived.return_value = True
        self.assertIsNone(live_comments.page_config(link, vault, "new"))

    def test_page_config(self):
        vault = mock.Mock(live_comments=True)
        link = mock.Mock(_id36="ab", _fullname="t1_ab", locked=False)
        link.is_archived.return_value = False
        websockets = mock.Mock()
        websockets.make_url.return_value = "wss://site/websocket/comments/ab?m=x"
        with mock.patch.dict("sys.modules", {"r2.lib.websockets": websockets}):
            with mock.patch("r2.lib.websockets", websockets, create=True):
                config = live_comments.page_config(link, vault, "new")
        self.assertEqual(config["link"], "t1_ab")
        self.assertEqual(config["sort"], "new")
        websockets.make_url.assert_called_with(
            "/websocket/comments/ab", max_age=live_comments.URL_SECONDS)
