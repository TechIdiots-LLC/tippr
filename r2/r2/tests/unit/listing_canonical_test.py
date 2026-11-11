"""The canonical links and robots rules of listing pages
(r2.controllers.listingcontroller), as search engines see them."""

import types
from unittest import mock

from r2.tests import TipprControllerTestCase


class UserCanonicalLinkTest(TipprControllerTestCase):
    """A profile's canonical link leaves out its sort and time."""

    def canonical(self, where):
        # (imported here: the controllers need the test case's setUp first)
        from r2.controllers import listingcontroller
        controller = listingcontroller.UserController.__new__(
            listingcontroller.UserController)
        controller.vuser = types.SimpleNamespace(name="feed_bot")
        controller.where = where
        with mock.patch.object(listingcontroller, "add_vault",
                               lambda path, **kw: path):
            return controller.canonical_link()

    def test_overview(self):
        self.assertEqual(self.canonical("overview"), "/user/feed_bot/")

    def test_submitted(self):
        self.assertEqual(self.canonical("submitted"),
                         "/user/feed_bot/submitted/")

    def test_comments(self):
        self.assertEqual(self.canonical("comments"),
                         "/user/feed_bot/comments/")
