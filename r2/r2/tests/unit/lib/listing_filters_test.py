#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

from unittest.mock import MagicMock

from pylons import tmpl_context as c

from r2.lib import listing_filters
from r2.tests import TipprTestCase


def user(**prefs):
    u = MagicMock(_id=1)
    for kind in ("keywords", "domains", "vaults", "users"):
        setattr(u, "pref_filter_" + kind, prefs.get(kind, ()))
    return u


def link(title="a post", domain="example.org", vault="pics", author="someone",
         is_self=False):
    l = MagicMock(title=title, is_self=is_self)
    l.link_domain.return_value = domain
    w = MagicMock(domain=domain)
    w.vault.name = vault
    w.vault._id = 99
    w.author.name = author
    return l, w


class TestCleanList(TipprTestCase):
    def test_lines_and_commas(self):
        self.assertEqual(listing_filters.clean_list("Cats, dogs\n\n birds ", "keywords"),
                         ["cats", "dogs", "birds"])

    def test_prefixes_and_urls(self):
        self.assertEqual(listing_filters.clean_list("/v/Pics\nv/funny/", "vaults"),
                         ["pics", "funny"])
        self.assertEqual(listing_filters.clean_list("/u/Bob, user/alice", "users"),
                         ["bob", "alice"])
        self.assertEqual(
            listing_filters.clean_list("https://www.Example.com/a/b, .news.org", "domains"),
            ["example.com", "news.org"])

    def test_duplicates_and_limits(self):
        self.assertEqual(listing_filters.clean_list("a\nA\na", "keywords"), ["a"])
        many = "\n".join("w%d" % i for i in range(500))
        self.assertEqual(len(listing_filters.clean_list(many, "keywords")),
                         listing_filters.MAX_ENTRIES)


class TestHides(TipprTestCase):
    def setUp(self):
        c._listing_filters = None
        c.site = MagicMock(_id=1)

    def test_nothing_set(self):
        self.assertFalse(listing_filters.hides(user(), *link()))

    def test_keywords_are_whole_words(self):
        u = user(keywords=("cat", "new york"))
        self.assertTrue(listing_filters.hides(u, *link(title="My CAT sleeps")))
        self.assertTrue(listing_filters.hides(u, *link(title="Snow in New York today")))
        self.assertFalse(listing_filters.hides(u, *link(title="Concatenate strings")))

    def test_domains_cover_subdomains(self):
        u = user(domains=("example.com",))
        self.assertTrue(listing_filters.hides(u, *link(domain="news.example.com")))
        self.assertTrue(listing_filters.hides(u, *link(domain="www.example.com")))
        self.assertFalse(listing_filters.hides(u, *link(domain="notexample.com")))
        self.assertFalse(listing_filters.hides(
            u, *link(domain="example.com", is_self=True)))

    def test_vaults_except_on_their_own_page(self):
        u = user(vaults=("pics",))
        self.assertTrue(listing_filters.hides(u, *link(vault="pics")))
        c._listing_filters = None
        c.site = MagicMock(_id=99)
        self.assertFalse(listing_filters.hides(u, *link(vault="pics")))

    def test_users(self):
        u = user(users=("spammer",))
        self.assertTrue(listing_filters.hides(u, *link(author="Spammer")))
        self.assertFalse(listing_filters.hides(u, *link(author="friend")))
