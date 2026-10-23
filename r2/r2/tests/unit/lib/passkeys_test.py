#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from unittest.mock import MagicMock, patch

from r2.lib import passkeys, two_factor
from r2.tests import TipprTestCase


class TestPasskeyNames(TipprTestCase):
    def test_named_by_where_it_was_saved(self):
        self.assertEqual(passkeys.provider_name(
            "EA9B8D66-4D01-1D21-3CE4-B6B48CB575D4", ["internal", "hybrid"]),
            "Google Password Manager")
        self.assertEqual(passkeys.provider_name(
            "fbfc3007-154e-4ecc-8c0b-6e020557d7bd", []), "iCloud Keychain")

    def test_unknown_security_keys_and_others(self):
        self.assertEqual(passkeys.provider_name(
            "00000000-0000-0000-0000-000000000000", ["usb"]), "security key")
        self.assertIsNone(passkeys.provider_name(None, ["internal"]))

    def test_names_are_numbered(self):
        account = MagicMock()
        with patch.object(two_factor, "methods",
                          return_value=[{"name": "Windows Hello"}]):
            self.assertEqual(two_factor._name(None, "passkey", account,
                                              "Windows Hello"),
                             "Windows Hello 2")
            self.assertEqual(two_factor._name(None, "passkey", account),
                             "passkey")
            # a name typed in is kept as it is
            self.assertEqual(two_factor._name(" my  key ", "passkey",
                                              account, "Windows Hello"),
                             "my key")
