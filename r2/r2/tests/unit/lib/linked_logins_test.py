#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import base64
import hashlib
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from r2.lib import linked_logins
from r2.tests import TipprTestCase

SETTINGS = dict(linked_logins.SETTINGS, google_enabled=True,
                google_client_id="gid", google_client_secret="gsecret",
                facebook_enabled=True, facebook_client_id="fid",
                facebook_client_secret="fsecret")


class FakeCache(dict):
    def set(self, key, value, time=None):
        self[key] = value

    def delete(self, key):
        self.pop(key, None)


def response(json, ok=True):
    r = MagicMock(ok=ok, status_code=200 if ok else 400, text="")
    r.json.return_value = json
    return r


class TestLinkedLogins(TipprTestCase):
    def setUp(self):
        self.cache = FakeCache()
        fake_g = MagicMock(gencache=self.cache,
                           https_endpoint="https://example.org")
        for target, value in (
                ("r2.lib.linked_logins.g", fake_g),
                ("r2.lib.linked_logins.login_settings", lambda: dict(SETTINGS))):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def test_start_sends_pkce_and_state(self):
        url, token = linked_logins.start("google", "login", dest="/v/books")
        q = parse_qs(urlparse(url).query)
        self.assertTrue(url.startswith("https://accounts.google.com/"))
        self.assertEqual(q["state"], [token])
        self.assertEqual(q["client_id"], ["gid"])
        self.assertEqual(q["redirect_uri"],
                         ["https://example.org/logins/callback/google"])
        record = self.cache["linked_login_state:" + token]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(
            record["verifier"].encode()).digest()).decode().rstrip("=")
        self.assertEqual(q["code_challenge"], [challenge])
        self.assertEqual(record["dest"], "/v/books")

    def test_disabled_provider(self):
        with patch("r2.lib.linked_logins.login_settings",
                   lambda: dict(SETTINGS, facebook_enabled=False)):
            with self.assertRaises(linked_logins.LoginError):
                linked_logins.start("facebook", "login")

    def test_state_must_match_the_browser_cookie(self):
        _, token = linked_logins.start("google", "login")
        with self.assertRaises(linked_logins.LoginError):
            linked_logins.finish("google", "code", token, "other-browser")
        with self.assertRaises(linked_logins.LoginError):
            linked_logins.finish("google", "code", token, None)

    @patch("r2.lib.linked_logins.requests")
    def test_finish_returns_who_signed_in_once(self, requests_mock):
        requests_mock.RequestException = Exception
        requests_mock.post.return_value = response({"access_token": "tok"})
        requests_mock.get.return_value = response(
            {"sub": "12345", "email": "a@example.com", "name": "A"})
        _, token = linked_logins.start("google", "link", dest="/prefs/security")
        record, identity = linked_logins.finish("google", "code", token, token)
        self.assertEqual(identity, {"subject": "12345", "email": "a@example.com",
                                    "name": "A"})
        self.assertEqual(record["purpose"], "link")
        sent = requests_mock.post.call_args[1]["data"]
        self.assertEqual(sent["code_verifier"], record["verifier"])
        self.assertEqual(sent["client_secret"], "gsecret")
        # the state can't be used twice
        with self.assertRaises(linked_logins.LoginError):
            linked_logins.finish("google", "code", token, token)

    @patch("r2.lib.linked_logins.requests")
    def test_refused_code(self, requests_mock):
        requests_mock.RequestException = Exception
        requests_mock.post.return_value = response({"error": "bad"}, ok=False)
        _, token = linked_logins.start("facebook", "login")
        with self.assertRaises(linked_logins.LoginError):
            linked_logins.finish("facebook", "code", token, token)

    def test_cancelled_at_the_provider(self):
        _, token = linked_logins.start("google", "login")
        with self.assertRaises(linked_logins.LoginError):
            linked_logins.finish("google", None, token, token)

    def test_only_local_destinations(self):
        self.assertEqual(linked_logins.safe_dest("/v/books"), "/v/books")
        for bad in ("https://evil.example/", "//evil.example/", "/\\evil", "", None,
                    # urlsplit drops these first: "//evil.example"
                    "/\t/evil.example", "/\n/evil.example", "/\r/evil.example",
                    "/ /evil.example", "/\x00/evil.example"):
            self.assertEqual(linked_logins.safe_dest(bad), "/")
        self.assertEqual(linked_logins.safe_dest("/v/books?sort=new#top"),
                         "/v/books?sort=new#top")

    def test_link_refuses_someone_elses_account(self):
        account = MagicMock(_id=1)
        with patch("r2.lib.linked_logins.account_id_for", lambda p, s: 2):
            with self.assertRaises(linked_logins.LoginError):
                linked_logins.link(account, "google", {"subject": "x"})

    @patch("r2.lib.linked_logins.requests")
    def test_github_and_discord_names(self, requests_mock):
        requests_mock.RequestException = Exception
        requests_mock.post.return_value = response({"access_token": "tok"})
        for provider, person, name in (
                ("github", {"id": 583231, "login": "octocat",
                            "name": "The Octocat", "email": None}, "octocat"),
                ("discord", {"id": "80351110224678912", "username": "nelly",
                             "global_name": "Nelly"}, "nelly")):
            requests_mock.get.return_value = response(person)
            with patch("r2.lib.linked_logins.login_settings",
                       lambda: dict(SETTINGS, **{
                           provider + "_enabled": True,
                           provider + "_client_id": "id",
                           provider + "_client_secret": "secret"})):
                _, token = linked_logins.start(provider, "login")
                _, identity = linked_logins.finish(provider, "code", token,
                                                   token)
            self.assertEqual(identity, {"subject": str(person["id"]),
                                        "email": None, "name": name})

    def test_the_api_lists_every_provider(self):
        # r2.controllers.api.LOGIN_PROVIDERS (read from the source: the
        # controllers aren't imported in the unit tests)
        import ast
        import os
        import r2
        path = os.path.join(os.path.dirname(r2.__file__), "controllers",
                            "api.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        listed = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and
                  getattr(node.targets[0], "id", None) == "LOGIN_PROVIDERS"]
        self.assertEqual(listed, [tuple(linked_logins.PROVIDER_ORDER)])
        extras = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and
                  getattr(node.targets[0], "id", None) == "LOGIN_EXTRA_SETTINGS"]
        self.assertEqual(extras, [{p: info["extra_settings"]
                                   for p, info in linked_logins.PROVIDERS.items()
                                   if info.get("extra_settings")}])


class TestSignInWithApple(TipprTestCase):
    """Apple's client secret (a token signed with the site's key) and its
    id_token (checked with Apple's published keys), with keys made here."""

    def setUp(self):
        import json
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        self.json = json
        self.ec_key = ec.generate_private_key(ec.SECP256R1())
        pem = self.ec_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        self.settings = {"apple_client_id": "net.example.signin", "apple_team_id": "TEAM123",
                         "apple_key_id": "KEY456", "apple_client_secret": pem}
        self.rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = self.rsa_key.public_key().public_numbers()
        as_b64 = lambda n: linked_logins._b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))
        keys = [{"kid": "apple1", "kty": "RSA", "alg": "RS256",
                 "n": as_b64(numbers.n), "e": as_b64(numbers.e)}]
        p = patch.object(linked_logins, "_apple_keys", return_value=keys)
        p.start()
        self.addCleanup(p.stop)

    def decode(self, part):
        return self.json.loads(linked_logins._b64url_decode(part))

    def test_client_secret_is_signed_with_the_key(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        token = linked_logins.apple_client_secret(self.settings, now=1000)
        header, claims, signature = token.split(".")
        self.assertEqual(self.decode(header), {"alg": "ES256", "kid": "KEY456"})
        self.assertEqual(self.decode(claims), {
            "iss": "TEAM123", "iat": 1000, "exp": 4600,
            "aud": "https://appleid.apple.com", "sub": "net.example.signin"})
        raw = linked_logins._b64url_decode(signature)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        # raises if it isn't the key's signature
        self.ec_key.public_key().verify(der, ("%s.%s" % (header, claims)).encode(),
                                        ec.ECDSA(hashes.SHA256()))

    def test_a_key_pasted_without_its_line_breaks_still_works(self):
        self.settings["apple_client_secret"] = " ".join(self.settings["apple_client_secret"].split())
        self.assertEqual(len(linked_logins.apple_client_secret(self.settings).split(".")), 3)

    def id_token(self, claims, kid="apple1", key=None):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        header = linked_logins._b64url(self.json.dumps({"alg": "RS256", "kid": kid}).encode())
        body = linked_logins._b64url(self.json.dumps(claims).encode())
        signature = (key or self.rsa_key).sign(("%s.%s" % (header, body)).encode(),
                                               padding.PKCS1v15(), hashes.SHA256())
        return "%s.%s.%s" % (header, body, linked_logins._b64url(signature))

    def claims(self, **kw):
        return dict({"iss": "https://appleid.apple.com", "aud": "net.example.signin",
                     "sub": "001234.abcdef", "exp": 2000}, **kw)

    def test_a_good_id_token(self):
        claims = linked_logins.verify_apple_id_token(
            self.id_token(self.claims()), "net.example.signin", now=1000)
        self.assertEqual(claims["sub"], "001234.abcdef")

    def test_bad_id_tokens_are_refused(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for token in (self.id_token(self.claims(aud="someone.else")),
                      self.id_token(self.claims(exp=999)),
                      self.id_token(self.claims(iss="https://evil.example")),
                      self.id_token(self.claims(), key=other_key),
                      self.id_token(self.claims(), kid="unknown"),
                      "not-a-token"):
            with self.assertRaises(linked_logins.LoginError):
                linked_logins.verify_apple_id_token(token, "net.example.signin", now=1000)

    def test_apple_needs_its_team_and_key_ids(self):
        settings = dict({"apple_enabled": True}, **self.settings)
        self.assertTrue(linked_logins.configured("apple", settings))
        settings["apple_key_id"] = ""
        self.assertFalse(linked_logins.configured("apple", settings))
