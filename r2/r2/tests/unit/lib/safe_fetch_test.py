#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import socket
import unittest
from unittest.mock import patch

from r2.lib import safe_fetch


class TestPublicAddresses(unittest.TestCase):
    def test_internal_addresses_are_not_public(self):
        for address in ("127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1",
                        "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1",
                        "fe80::1%eth0", "fc00::1", "::ffff:127.0.0.1",
                        "224.0.0.1", "not an address"):
            self.assertFalse(safe_fetch.is_public(address), address)

    def test_public_addresses(self):
        for address in ("93.184.216.34", "1.1.1.1", "2606:4700:4700::1111"):
            self.assertTrue(safe_fetch.is_public(address), address)

    def test_a_name_resolving_inside_is_refused(self):
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]
        with patch("socket.getaddrinfo", return_value=infos):
            with self.assertRaises(safe_fetch.BlockedAddress):
                safe_fetch.public_address("intranet.example", 80)

    def test_the_public_one_of_several_is_used(self):
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
                 (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        with patch("socket.getaddrinfo", return_value=infos):
            self.assertEqual(safe_fetch.public_address("example.com", 80),
                             (socket.AF_INET, ("93.184.216.34", 80)))

    def test_only_http_and_https(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x"):
            with self.assertRaises(safe_fetch.BlockedAddress):
                safe_fetch.urlopen(url)
