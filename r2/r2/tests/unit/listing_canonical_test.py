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


class AllMinusTest(TipprControllerTestCase):
    """/v/all-a-b-c: one address for each set of vaults, and only members
    are offered it."""

    def vaults(self, *names):
        return [types.SimpleNamespace(name=name, _id=i)
                for i, name in enumerate(names)]

    def test_path_is_in_name_order(self):
        from r2.models.vault import AllMinus
        self.assertEqual(AllMinus(self.vaults("space", "Art", "cats")).path,
                         "/v/all-Art-cats-space")
        self.assertEqual(AllMinus(self.vaults("cats", "space", "Art")).path,
                         "/v/all-Art-cats-space")

    def infobar(self, logged_in):
        from r2.lib.pages import pages
        fake_c = types.SimpleNamespace(
            user_is_loggedin=logged_in,
            user=types.SimpleNamespace(gold=False))
        with mock.patch.object(pages, "c", fake_c), \
                mock.patch.object(pages, "request",
                                  types.SimpleNamespace(path="/v/all/")), \
                mock.patch.object(pages.Vault, "user_vaults",
                                  return_value=[1, 2]), \
                mock.patch.object(pages.Vault, "_byID",
                                  return_value=self.vaults("cats", "art")):
            return pages.AllInfoBar(pages.AllSR(), fake_c.user)

    def test_members_get_the_link(self):
        self.assertEqual(self.infobar(True).allminus_url, "/v/all-art-cats")

    def test_logged_out_visitors_do_not(self):
        self.assertIsNone(self.infobar(False).allminus_url)


class DefaultRobotsTest(TipprControllerTestCase):
    """Which listings ask search engines not to index them."""

    def robots(self, site):
        from r2.lib.pages import pages
        return pages.default_robots(site)

    def test_domain_listing(self):
        from r2.models.vault import DomainVault
        self.assertEqual(self.robots(DomainVault("xkcd.com")), "noindex")

    def test_filtered_all(self):
        from r2.models.vault import AllMinus
        self.assertEqual(self.robots(AllMinus([])), "noindex")

    def test_vaults_and_all_are_indexed(self):
        from r2.models.vault import AllSR, DefaultVault
        self.assertIsNone(self.robots(AllSR()))
        self.assertIsNone(self.robots(DefaultVault()))
