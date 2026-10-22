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
        for bad in ("https://evil.example/", "//evil.example/", "/\\evil", "", None):
            self.assertEqual(linked_logins.safe_dest(bad), "/")

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
