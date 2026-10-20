#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import base64
import json
import os

from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS, eddsa

from r2.lib import payments
from r2.lib.payments import bitpay, coinbase, paypal, stripe_checkout
from r2.tests import TipprTestCase


def _unb64url(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TestPrices(TipprTestCase):
    def test_dollars(self):
        self.assertEqual(payments.dollars(399), "3.99")
        self.assertEqual(payments.dollars(2999), "29.99")
        self.assertEqual(payments.dollars(5), "0.05")

    def test_months_then_whole_years(self):
        month = payments.g.gold_month_price.pennies
        year = payments.g.gold_year_price.pennies
        self.assertEqual(payments.gold_price(1), (1, month))
        self.assertEqual(payments.gold_price(11), (11, month * 11))
        self.assertEqual(payments.gold_price(12), (12, year))
        # a year and a bit is charged (and delivered) as the whole years
        self.assertEqual(payments.gold_price(25), (24, year * 2))
        with self.assertRaises(ValueError):
            payments.gold_price(0)


class TestCoinbaseJWT(TipprTestCase):
    def test_ed25519_token_verifies(self):
        seed = os.urandom(32)
        key = ECC.construct(curve="Ed25519", seed=seed)
        public = key.public_key().export_key(format="raw")
        secret = base64.b64encode(seed + public).decode()

        token = coinbase.make_jwt("key-1", secret, "POST",
                                  "/api/v1/checkouts", now=1000)
        header, claims, signature = token.split(".")
        eddsa.new(key.public_key(), "rfc8032").verify(
            ("%s.%s" % (header, claims)).encode(), _unb64url(signature))
        header = json.loads(_unb64url(header))
        claims = json.loads(_unb64url(claims))
        self.assertEqual(header["alg"], "EdDSA")
        self.assertEqual(header["kid"], "key-1")
        self.assertEqual(len(header["nonce"]), 32)
        self.assertEqual(claims["uri"],
                         "POST business.coinbase.com/api/v1/checkouts")
        self.assertEqual((claims["nbf"], claims["exp"]), (1000, 1120))
        self.assertEqual(claims["aud"], ["cdp_service"])

    def test_ecdsa_pem_token_verifies(self):
        key = ECC.generate(curve="P-256")
        pem = key.export_key(format="PEM")
        token = coinbase.make_jwt("key-2", pem, "GET", "/api/v1/checkouts")
        header, claims, signature = token.split(".")
        DSS.new(key.public_key(), "fips-186-3").verify(
            SHA256.new(("%s.%s" % (header, claims)).encode()),
            _unb64url(signature))
        self.assertEqual(json.loads(_unb64url(header))["alg"], "ES256")

    def test_bad_secret(self):
        with self.assertRaises(payments.PaymentError):
            coinbase.make_jwt("k", "not base64!", "GET", "/")

    def test_idempotency_key_is_a_stable_uuid4(self):
        key = coinbase.idempotency_key("checkout-abc")
        self.assertEqual(key, coinbase.idempotency_key("checkout-abc"))
        self.assertNotEqual(key, coinbase.idempotency_key("checkout-abd"))
        self.assertEqual(len(key), 36)
        self.assertEqual(key[14], "4")
        self.assertIn(key[19], "89ab")


class TestPayPal(TipprTestCase):
    def test_states(self):
        def order(capture_status=None, status="COMPLETED"):
            unit = {}
            if capture_status:
                unit["payments"] = {"captures": [
                    {"id": "CAP1", "status": capture_status}]}
            return {"status": status, "purchase_units": [unit]}
        self.assertEqual(paypal._state(order("COMPLETED")),
                         {"status": "paid", "capture_ref": "CAP1"})
        self.assertEqual(paypal._state(order("PENDING"))["status"], "pending")
        self.assertEqual(paypal._state(order("REFUNDED"))["status"],
                         "refunded")
        self.assertEqual(paypal._state(order("DECLINED"))["status"], "failed")
        approved = paypal._state(order(status="APPROVED"))
        self.assertIsNone(approved["status"])
        self.assertEqual(approved["order_status"], "APPROVED")

    def test_webhook_refs(self):
        self.assertEqual(paypal.webhook_refs({
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": "ORDER1",
                         "purchase_units": [{"custom_id": "pay1"}]}}),
            ("pay1", "ORDER1", None))
        self.assertEqual(paypal.webhook_refs({
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"id": "CAP1", "custom_id": "pay1",
                         "supplementary_data": {
                             "related_ids": {"order_id": "ORDER1"}}}}),
            ("pay1", "ORDER1", "CAP1"))
        # a refund: the resource is the refund, its "up" link the capture
        self.assertEqual(paypal.webhook_refs({
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "resource": {"id": "REF1", "links": [
                {"rel": "up", "href":
                 "https://api-m.paypal.com/v2/payments/captures/CAP1"}]}}),
            (None, None, "CAP1"))


class TestStripe(TipprTestCase):
    def test_webhook_refs(self):
        self.assertEqual(stripe_checkout.webhook_refs({
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_1", "client_reference_id": "pay1",
                                "payment_intent": "pi_1"}}}),
            ("pay1", "cs_1", "pi_1"))
        self.assertEqual(stripe_checkout.webhook_refs({
            "type": "charge.refunded",
            "data": {"object": {"id": "ch_1", "payment_intent": "pi_1"}}}),
            (None, None, "pi_1"))


class TestCrypto(TipprTestCase):
    def test_coinbase_webhook_refs(self):
        event = {"eventType": "checkout.payment.success",
                 "data": {"id": "68f7a946db0529ea9b6d3a12",
                          "metadata": {"tippr_payment": "pay1"}}}
        self.assertEqual(coinbase.webhook_refs(event),
                         ("pay1", "68f7a946db0529ea9b6d3a12", None))

    def test_coinbase_statuses(self):
        self.assertEqual(coinbase.STATUS["COMPLETED"], "paid")
        self.assertEqual(coinbase.STATUS["PROCESSING"], "pending")
        self.assertIsNone(coinbase.STATUS["ACTIVE"])

    def test_bitpay_webhook_refs(self):
        # the current format, and the old one with the invoice at the top
        self.assertEqual(bitpay.webhook_refs(
            {"event": {"name": "invoice_confirmed"},
             "data": {"id": "INV1", "orderId": "pay1"}}),
            ("pay1", "INV1", None))
        self.assertEqual(bitpay.webhook_refs(
            {"id": "INV1", "posData": "pay1", "status": "confirmed"}),
            ("pay1", "INV1", None))

    def test_bitpay_delivers_at_confirmed(self):
        self.assertEqual(bitpay.STATUS["paid"], "pending")
        self.assertEqual(bitpay.STATUS["confirmed"], "paid")
