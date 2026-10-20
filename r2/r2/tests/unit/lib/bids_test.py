#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from unittest.mock import MagicMock, patch

from r2.lib import bids
from r2.lib.db.thing import NotFound
from r2.lib.payments import ads
from r2.tests import TipprTestCase


def bid(pay_id=bids.FREEBIE_PAYMENT_METHOD_ID, charged=False):
    b = MagicMock(pay_id=pay_id)
    b.is_charged.return_value = charged
    return b


class TestBids(TipprTestCase):
    @patch("r2.lib.bids.Bid")
    def test_new_freebie(self, Bid):
        Bid.one.side_effect = NotFound
        link = MagicMock(_id=42)
        trans_id, error = bids.auth_freebie_transaction(10.0, "user", link, 7)
        self.assertEqual((trans_id, error), (-42, ""))
        Bid._new.assert_called_once_with(
            -42, "user", bids.FREEBIE_PAYMENT_METHOD_ID, 42, 10.0, 7)

    @patch("r2.lib.bids.Bid")
    def test_freebie_given_again_is_updated(self, Bid):
        existing = bid()
        Bid.one.return_value = existing
        bids.auth_freebie_transaction(25.0, "user", MagicMock(_id=42), 7)
        self.assertEqual(existing.bid, 25.0)
        existing.auth.assert_called_once_with()
        Bid._new.assert_not_called()

    @patch("r2.lib.bids.Bid")
    def test_charge_marks_charged_once(self, Bid):
        Bid.one.return_value = b = bid()
        self.assertEqual(bids.charge_transaction("u", -42, 7), (True, None))
        b.charged.assert_called_once_with()
        Bid.one.return_value = b = bid(charged=True)
        bids.charge_transaction("u", -42, 7)
        b.charged.assert_not_called()

    @patch("r2.lib.bids.Bid")
    def test_void_and_refund_a_freebie(self, Bid):
        Bid.one.return_value = b = bid()
        self.assertEqual(bids.void_transaction("u", -42, 7), (True, None))
        b.void.assert_called_once_with()
        self.assertEqual(bids.refund_transaction("u", -42, 7, 2.5),
                         (True, None))
        b.refund.assert_called_once_with(2.5)

    @patch("r2.lib.payments.ads.refund_bid")
    @patch("r2.lib.bids.Bid")
    def test_provider_payments_are_refunded_through_the_provider(
            self, Bid, refund_bid):
        Bid.one.return_value = b = bid(ads.PROVIDER_PAYMENT_METHOD_ID, True)
        refund_bid.return_value = (True, None)
        self.assertEqual(bids.void_transaction("u", 10 ** 15 + 1, 7),
                         (True, None))
        refund_bid.assert_called_with(b)
        b.void.assert_called_once_with()

        self.assertEqual(bids.refund_transaction("u", 10 ** 15 + 1, 7, 12.5),
                         (True, None))
        refund_bid.assert_called_with(b, pennies=1250)
        b.refund.assert_called_once_with(12.5)

    @patch("r2.lib.payments.ads.refund_bid")
    @patch("r2.lib.bids.Bid")
    def test_a_failed_refund_leaves_the_bid(self, Bid, refund_bid):
        Bid.one.return_value = b = bid(ads.PROVIDER_PAYMENT_METHOD_ID, True)
        refund_bid.return_value = (False, "declined")
        self.assertEqual(bids.void_transaction("u", 10 ** 15 + 1, 7),
                         (False, "declined"))
        b.void.assert_not_called()

    @patch("r2.lib.bids.Bid")
    def test_is_charged(self, Bid):
        self.assertFalse(bids.is_charged_transaction(0, 7))
        Bid.one.side_effect = NotFound
        self.assertFalse(bids.is_charged_transaction(-42, 7))
        Bid.one.side_effect = None
        Bid.one.return_value = b = bid(charged=True)
        self.assertTrue(bids.is_charged_transaction(-42, 7))
