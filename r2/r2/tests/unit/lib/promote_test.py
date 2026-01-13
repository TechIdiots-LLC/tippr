import datetime
import unittest
from unittest.mock import MagicMock, Mock, patch

from r2.lib.promote import (
    get_nsfw_collections_vaultnames,
    get_refund_amount,
    refund_campaign,
    vaultnames_from_site,
)
from r2.models import (
    Account,
    Collection,
    FakeAccount,
    Frontpage,
    MultiVault,
    PromoCampaign,
    Vault,
)
from r2.tests import NonCache, TipprTestCase

subscriptions_vaultnames = ["foo", "bar"]
subscriptions = [Vault(name=vaultname) for vaultname in subscriptions_vaultnames]
multi_vaultnames = ["bing", "bat"]
multi_Vaults = [Vault(name=vaultname) for vaultname in multi_vaultnames]
nice_vaultname = "mylittlepony"
nsfw_vaultname = "pr0n"
questionably_nsfw = "sexstories"
quarantined_vaultname = "croontown"
naughty_subscriptions = [
    Vault(name=nice_vaultname),
    Vault(name=nsfw_vaultname, over_18=True),
    Vault(name=quarantined_vaultname, quarantine=True),
]
nsfw_collection_vaultnames = [questionably_nsfw, nsfw_vaultname]
nsfw_collection = Collection(
    name="after dark",
    vault_names=nsfw_collection_vaultnames,
    over_18=True
)

class TestVaultNamesFromSite(TipprTestCase):
    def setUp(self):
        self.logged_in = Account(name="test")
        self.logged_out = FakeAccount()

        self.patch_g(memoizecache=NonCache())

    def test_frontpage_logged_out(self):
        vaultnames = vaultnames_from_site(self.logged_out, Frontpage)

        self.assertEqual(vaultnames, {Frontpage.name})

    @patch("r2.models.Vault.user_vaults")
    def test_frontpage_logged_in(self, user_vaults):
        user_vaults.return_value = subscriptions
        vaultnames = vaultnames_from_site(self.logged_in, Frontpage)

        self.assertEqual(vaultnames, set(subscriptions_vaultnames) | {Frontpage.name})

    def test_multi_logged_out(self):
        multi = MultiVault(path="/user/test/m/multi_test", vaults=multi_Vaults)
        vaultnames = vaultnames_from_site(self.logged_out, multi)

        self.assertEqual(vaultnames, set(multi_vaultnames))

    @patch("r2.models.Vault.user_vaults")
    def test_multi_logged_in(self, user_vaults):
        user_vaults.return_value = subscriptions
        multi = MultiVault(path="/user/test/m/multi_test", vaults=multi_Vaults)
        vaultnames = vaultnames_from_site(self.logged_in, multi)

        self.assertEqual(vaultnames, set(multi_vaultnames))

    def test_Vault_logged_out(self):
        vaultname = "test1"
        vault = Vault(name=vaultname)
        vaultnames = vaultnames_from_site(self.logged_out, vault)

        self.assertEqual(vaultnames, {vaultname})

    @patch("r2.models.Vault.user_vaults")
    def test_Vault_logged_in(self, user_vaults):
        user_vaults.return_value = subscriptions
        vaultname = "test1"
        vault = Vault(name=vaultname)
        vaultnames = vaultnames_from_site(self.logged_in, vault)

        self.assertEqual(vaultnames, {vaultname})

    @patch("r2.models.Vault.user_vaults")
    def test_quarantined_subscriptions_are_never_included(self, user_vaults):
        user_vaults.return_value = naughty_subscriptions
        vault = Frontpage
        vaultnames = vaultnames_from_site(self.logged_in, vault)

        self.assertEqual(vaultnames, {vault.name} | {nice_vaultname})
        self.assertTrue(len(vaultnames & {quarantined_vaultname}) == 0)

    @patch("r2.models.Vault.user_vaults")
    def test_nsfw_subscriptions_arent_included_when_viewing_frontpage(self, user_vaults):
        user_vaults.return_value = naughty_subscriptions
        vaultnames = vaultnames_from_site(self.logged_in, Frontpage)

        self.assertEqual(vaultnames, {Frontpage.name} | {nice_vaultname})
        self.assertTrue(len(vaultnames & {nsfw_vaultname}) == 0)

    @patch("r2.models.Collection.get_all")
    def test_get_nsfw_collections_vaultnames(self, get_all):
        get_all.return_value = [nsfw_collection]
        vaultnames = get_nsfw_collections_vaultnames()

        self.assertEqual(vaultnames, set(nsfw_collection_vaultnames))

    @patch("r2.lib.promote.get_nsfw_collections_vaultnames")
    def test_remove_nsfw_collection_vaultnames_on_frontpage(self, get_nsfw_collections_vaultnames):
        get_nsfw_collections_vaultnames.return_value = set(nsfw_collection.vault_names)
        vaultname = "test1"
        vault = Vault(name=vaultname)
        Vault.user_vaults = MagicMock(return_value=[
            Vault(name=nice_vaultname),
            Vault(name=questionably_nsfw),
        ])

        frontpage_vaultnames = vaultnames_from_site(self.logged_in, Frontpage)
        swf_vaultnames = vaultnames_from_site(self.logged_in, vault)

        self.assertEqual(frontpage_vaultnames, {Frontpage.name, nice_vaultname})
        self.assertTrue(len(frontpage_vaultnames & {questionably_nsfw}) == 0)


class TestPromoteRefunds(unittest.TestCase):
    def setUp(self):
        self.link = Mock()
        self.campaign = MagicMock(spec=PromoCampaign)
        self.campaign._id = 1
        self.campaign.owner_id = 1
        self.campaign.trans_id = 1
        self.campaign.bid_pennies = 1
        self.campaign.start_date = datetime.datetime.now()
        self.campaign.end_date = (datetime.datetime.now() +
            datetime.timedelta(days=1))
        self.campaign.total_budget_dollars = 200.
        self.refund_amount = 100.
        self.billable_amount = 100.
        self.billable_impressions = 1000

    @patch('r2.lib.promote.authorize.refund_transaction')
    @patch('r2.lib.promote.PromotionLog.add')
    @patch('r2.lib.promote.queries.unset_underdelivered_campaigns')
    @patch('r2.lib.promote.emailer.refunded_promo')
    def test_refund_campaign_success(self, emailer_refunded_promo,
            queries_unset, promotion_log_add, refund_transaction):
        """Assert return value and that correct calls are made on success."""
        refund_transaction.return_value = (True, None)

        # the refund process attemtps a db lookup. We don't need it for the
        # purpose of the test.
        with patch.object(Account, "_byID"):
            success = refund_campaign(
                link=self.link,
                camp=self.campaign,
                refund_amount=self.refund_amount,
                billable_amount=self.billable_amount,
                billable_impressions=self.billable_impressions,
            )

        self.assertTrue(refund_transaction.called)
        self.assertTrue(promotion_log_add.called)
        queries_unset.assert_called_once_with(self.campaign)
        emailer_refunded_promo.assert_called_once_with(self.link)
        self.assertTrue(success)

    @patch('r2.lib.promote.authorize.refund_transaction')
    @patch('r2.lib.promote.PromotionLog.add')
    def test_refund_campaign_failed(self, promotion_log_add,
            refund_transaction):
        """Assert return value and that correct calls are made on failure."""
        refund_transaction.return_value = (False, None)

        # the refund process attemtps a db lookup. We don't need it for the
        # purpose of the test.
        with patch.object(Account, "_byID"):
            success = refund_campaign(
                link=self.link,
                camp=self.campaign,
                refund_amount=self.refund_amount,
                billable_amount=self.billable_amount,
                billable_impressions=self.billable_impressions,
            )

        self.assertTrue(refund_transaction.called)
        self.assertTrue(promotion_log_add.called)
        self.assertFalse(success)

    def test_get_refund_amount_when_zero(self):
        """
        Assert that correct value is returned when existing refund_amount is
        zero.
        """
        campaign = MagicMock(spec=('total_budget_dollars',))
        campaign.total_budget_dollars = 200.
        refund_amount = get_refund_amount(campaign, self.billable_amount)
        self.assertEqual(refund_amount,
            campaign.total_budget_dollars - self.billable_amount)

    def test_get_refund_amount_rounding(self):
        """Assert that inputs are correctly rounded up to the nearest penny."""
        # If campaign.refund_amount is less than a fraction of a penny,
        # the refund_amount should be campaign.total_budget_dollars.
        self.campaign.refund_amount = 0.00000001
        refund_amount = get_refund_amount(self.campaign, self.billable_amount)
        self.assertEqual(refund_amount, self.billable_amount)

        self.campaign.refund_amount = 0.00999999
        refund_amount = get_refund_amount(self.campaign, self.billable_amount)
        self.assertEqual(refund_amount, self.billable_amount)

        # If campaign.refund_amount is just slightly more than a penny,
        # the refund amount should be campaign.total_budget_dollars - 0.01.
        self.campaign.refund_amount = 0.01000001
        refund_amount = get_refund_amount(self.campaign, self.billable_amount)
        self.assertEqual(refund_amount, self.billable_amount - 0.01)

        # Even if campaign.refund_amount is just barely short of two pennies,
        # the refund amount should be campaign.total_budget_dollars - 0.01.
        self.campaign.refund_amount = 0.01999999
        refund_amount = get_refund_amount(self.campaign, self.billable_amount)
        self.assertEqual(refund_amount, self.billable_amount - 0.01)
