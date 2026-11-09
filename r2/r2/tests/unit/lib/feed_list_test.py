#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""/admin/feeds' import and export (r2.lib.feed_list)."""

from types import SimpleNamespace
from unittest.mock import patch

from r2.lib import feed_list, feeds
from r2.lib.db.thing import NotFound
from r2.models import Account, Vault
from r2.tests import TipprTestCase

VAULTS = {"news": 1, "technology": 2}


def vault_by_name(name):
    if name not in VAULTS:
        raise NotFound
    return SimpleNamespace(_id=VAULTS[name], name=name, ai_policy="any")


def feed(_id, url, vault="news", bot="news_bot", **kw):
    row = dict(id=_id, url=url, vault_id=VAULTS[vault], vault_name=vault,
               bot_name=bot, title_prefix=None, over_18=False, ai_content=None,
               enabled=True, interval_minutes=60)
    row.update(kw)
    return row


class TestReadAndExport(TipprTestCase):
    def read(self, *lines):
        return feed_list.read_lines(lines)

    def test_the_starter_list_format(self):
        e, = self.read("/v/news\t[BBC]\thttps://bbc.example/rss.xml\n")
        self.assertEqual((e["vault"], e["prefix"], e["url"]),
                         ("news", "[BBC]", "https://bbc.example/rss.xml"))
        self.assertFalse(e["over_18"] or e["paused"] or e["bot"] or e["every"])

    def test_vault_carries_down_and_comments_skip(self):
        entries = self.read("/v/news", "# https://no.example/",
                            "https://a.example/", "https://b.example/")
        self.assertEqual([e["vault"] for e in entries], ["news", "news"])
        self.assertIsNone(self.read("https://a.example/")[0]["vault"])

    def test_the_settings_on_a_line(self):
        e, = self.read("/v/news https://a.example/ nsfw ai:generated "
                       "bot:feed_bot every:30 paused")
        self.assertTrue(e["over_18"] and e["paused"])
        self.assertEqual((e["ai_label"], e["bot"], e["every"]),
                         ("generated", "feed_bot", 30))

    def test_a_prefix_isnt_read_as_settings(self):
        e, = self.read("/v/news\tprefix:nsfw /v/other paused\thttps://a.example/")
        self.assertEqual((e["prefix"], e["vault"]),
                         ("nsfw /v/other paused", "news"))
        self.assertFalse(e["over_18"] or e["paused"])

    def test_export_comes_back_the_same(self):
        original = feed(1, "https://a.example/x,y", title_prefix="Blog: new",
                        over_18=True, ai_content="assisted", enabled=False,
                        bot="feed_bot", interval_minutes=90)
        e, = self.read(feed_list.export_line(original))
        self.assertEqual(
            (e["vault"], e["url"], e["prefix"], e["over_18"], e["ai_label"],
             e["paused"], e["bot"], e["every"]),
            ("news", "https://a.example/x,y", "Blog: new", True, "assisted",
             True, "feed_bot", 90))

    def test_export_leaves_out_feeds_going_and_vaults_gone(self):
        text = feed_list.export([
            feed(1, "https://a.example/"),
            feed(2, "https://b.example/", removing="all"),
            dict(feed(3, "https://c.example/"), vault_name=""),
        ])
        self.assertEqual([e["url"] for e in self.read(*text.splitlines())],
                         ["https://a.example/"])


class TestPlan(TipprTestCase):
    def setUp(self):
        for target, name, kw in ((Vault, "_by_name", dict(side_effect=vault_by_name)),
                                 (Account, "_by_name", dict(side_effect=NotFound))):
            p = patch.object(target, name, **kw)
            p.start()
            self.addCleanup(p.stop)

    def actions(self, result):
        return [(r["action"], r["url"]) for r in result["rows"]]

    def test_adds_what_isnt_there(self):
        result = feed_list.plan(
            "/v/news https://a.example/\n/v/news https://b.example/ bot:other",
            "news_bot", [feed(1, "https://a.example")])
        self.assertEqual(self.actions(result), [("same", "https://a.example/"),
                                                ("add", "https://b.example/")])
        self.assertEqual(result["rows"][1]["bot"], "other")

    def test_a_feed_on_another_vault_is_another_feed(self):
        result = feed_list.plan("/v/technology https://a.example/", "b",
                                [feed(1, "https://a.example/")])
        self.assertEqual(result["counts"], {"add": 1})

    def test_a_repeated_line_adds_once(self):
        result = feed_list.plan("/v/news https://a.example/\n"
                                "/v/news https://a.example/", "b", [])
        self.assertEqual(result["counts"], {"add": 1, "same": 1})

    def test_problems(self):
        cases = (("https://a.example/", "no_vault"),
                 ("/v/nope https://a.example/", "no_such_vault"),
                 ("/v/news https://a.example/", "no_bot"),
                 ("/v/news https://a.example/ bot:b!d", "bad_bot"))
        for line, code in cases:
            row = feed_list.plan(line, "", [])["rows"][0]
            self.assertEqual((row["action"], row["problem"]), ("problem", code))

    def test_only_changes_when_asked(self):
        existing = [feed(1, "https://a.example/")]
        line = "/v/news [New] https://a.example/ nsfw paused every:120 bot:other"
        self.assertEqual(feed_list.plan(line, "b", existing)["counts"], {"same": 1})
        row = feed_list.plan(line, "b", existing, update=True)["rows"][0]
        self.assertEqual(row["action"], "change")
        self.assertEqual(row["values"], dict(
            title_prefix="[New]", over_18=True, enabled=False,
            interval_minutes=120))
        self.assertEqual(row["new_bot"], "other")

    def test_a_line_not_naming_the_bot_or_interval_keeps_them(self):
        existing = [feed(1, "https://a.example/", bot="old_bot", interval_minutes=30)]
        result = feed_list.plan("/v/news https://a.example/", "b", existing,
                                update=True)
        self.assertEqual(result["counts"], {"same": 1})

    def test_removes_only_from_the_view(self):
        everything = [feed(1, "https://a.example/"), feed(2, "https://b.example/"),
                      feed(3, "https://c.example/", vault="technology")]
        result = feed_list.plan("/v/news https://a.example/", "b", everything,
                                remove_from=everything[:2])
        self.assertEqual(self.actions(result),
                         [("same", "https://a.example/"),
                          ("remove", "https://b.example/")])

    def test_nothing_removed_from_a_list_with_problems_or_nothing_in_it(self):
        everything = [feed(1, "https://a.example/")]
        for text in ("/v/typo https://a.example/", "just some words"):
            result = feed_list.plan(text, "b", everything, remove_from=everything)
            self.assertTrue(result["remove_blocked"], text)
            self.assertNotIn("remove", result["counts"])

    def test_a_feed_being_deleted_is_left_to_it(self):
        going = [feed(1, "https://a.example/", removing="all")]
        result = feed_list.plan("/v/news https://b.example/", "b", going,
                                remove_from=going)
        self.assertEqual(result["counts"], {"add": 1})

    def test_apply(self):
        existing = [feed(1, "https://a.example/"), feed(2, "https://b.example/")]
        planned = feed_list.plan(
            "/v/news [X] https://a.example/\n"
            "/v/technology https://c.example/ paused every:5",
            "bot_one", existing, update=True, remove_from=existing)
        with patch.object(feeds, "add") as add, \
                patch.object(feeds, "update") as update, \
                patch.object(feeds, "remove") as remove, \
                patch.object(feeds, "bot_account") as bot_account:
            feed_list.apply(planned)
        update.assert_called_once_with(1, title_prefix="[X]")
        remove.assert_called_once_with(2)
        bot_account.assert_called_once_with("bot_one")
        args, kw = add.call_args
        self.assertEqual(args[0], "https://c.example/")
        # (the interval is raised to the least allowed)
        self.assertEqual(args[3], feeds.MIN_INTERVAL_MINUTES)
        self.assertFalse(kw["enabled"])
