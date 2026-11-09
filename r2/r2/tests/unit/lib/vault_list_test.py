#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""/admin/vaults' CSV import and export (r2.lib.vault_list)."""

from types import SimpleNamespace
from unittest.mock import patch

from r2.lib import vault_admin, vault_list
from r2.lib.db.thing import NotFound
from r2.models import Vault
from r2.tests import TipprTestCase


def vault(_id, name, **kw):
    settings = dict(_id=_id, name=name, title=name.title(),
                    public_description="", description="", type="public",
                    link_type="any", ai_policy="any", lang="en", over_18=False,
                    allow_top=True, show_media=False, _spam=False,
                    quarantine=False)
    settings.update(kw)
    return SimpleNamespace(**settings)


class VaultListTestCase(TipprTestCase):
    def setUp(self):
        self.vaults = {"news": vault(1, "news"), "tech": vault(2, "tech")}

        def by_name(name, _update=False):
            if name.lower() not in self.vaults:
                raise NotFound
            return self.vaults[name.lower()]

        for target, name, kw in (
                (Vault, "_by_name", dict(side_effect=by_name)),
                (vault_admin, "default_ids", dict(return_value={1})),
                (vault_admin, "featured_ids", dict(return_value=set()))):
            p = patch.object(target, name, **kw)
            p.start()
            self.addCleanup(p.stop)

    def row(self, text, **kw):
        return vault_list.plan(text, **kw)["rows"][0]


class TestExport(VaultListTestCase):
    def test_comes_back_unchanged(self):
        self.vaults["news"].public_description = "first\nsecond, with \"quotes\""
        self.vaults["tech"].title = "=SUM(A1)"
        text = vault_list.export(self.vaults.values())
        result = vault_list.plan(text)
        self.assertEqual(result["counts"], {"same": 2})

    def test_a_formula_cant_run_in_a_spreadsheet(self):
        self.vaults["news"].title = "=HYPERLINK(1)"
        self.assertIn("'=HYPERLINK(1)",
                      vault_list.export([self.vaults["news"]]))

    def test_the_lists(self):
        lines = vault_list.export(self.vaults.values()).splitlines()
        self.assertTrue(lines[1].endswith("yes,no"))
        self.assertTrue(lines[2].endswith("no,no"))


class TestPlan(VaultListTestCase):
    def test_only_the_columns_given(self):
        row = self.row("name,ai_policy\nnews,no_generated\n")
        self.assertEqual(row["action"], "change")
        self.assertEqual(row["wanted"], dict(ai_policy="no_generated"))

    def test_a_blank_cell_leaves_it_but_blanks_a_description(self):
        self.vaults["news"].description = "sidebar"
        row = self.row("name,title,description\nnews,,\n")
        self.assertEqual(row["wanted"], dict(description=""))

    def test_excel_flavours(self):
        row = self.row("\tName;over_18\n".replace("\t", "") + "/v/news;Yes\n")
        self.assertEqual((row["name"], row["wanted"]),
                         ("news", dict(over_18=True)))

    def test_the_site_wide_lists(self):
        row = self.row("name,default,featured\nnews,no,yes\n")
        self.assertEqual(row["wanted"], dict(default=False, featured=True))

    def test_problems(self):
        for text, code, column in (
                ("name,ai_policy\nnews,whatever\n", "bad_value", "ai_policy"),
                ("name,type\nnews,nonsense\n", "bad_value", "type"),
                ("name,type\nnews,gold_only\n", "bad_value", "type"),
                ("name,over_18\nnews,maybe\n", "bad_value", "over_18"),
                ("name,title\nnews,%s\n" % ("x" * 101), "too_long", "title"),
                ("name,title\nnope,Title\n", "no_such_vault", None)):
            row = self.row(text)
            self.assertEqual((row["action"], row["problem"], row["column"]),
                             ("problem", code, column), text)

    def test_a_name_twice(self):
        rows = vault_list.plan("name,title\nnews,A\nNEWS,B\n")["rows"]
        self.assertEqual(rows[1]["problem"], "repeated")

    def test_a_type_it_already_is(self):
        self.vaults["news"].type = "gold_only"
        self.assertEqual(self.row("name,type\nnews,gold_only\n")["action"],
                         "same")

    def test_banned_vaults_cant_be_defaults(self):
        self.vaults["tech"]._spam = True
        self.assertEqual(self.row("name,default\ntech,yes\n")["problem"],
                         "banned")

    def test_quarantined_settings_stay(self):
        self.vaults["news"].quarantine = True
        self.assertEqual(self.row("name,show_media\nnews,yes\n")["action"],
                         "same")

    def test_creating_is_asked_for_and_needs_a_title(self):
        text = "name,title\nbrand_new,Brand New\n"
        self.assertEqual(self.row(text)["problem"], "no_such_vault")
        self.assertEqual(self.row(text, create=True)["action"], "create")
        self.assertEqual(self.row("name,title\nbrand_new,\n", create=True)["problem"],
                         "no_title")
        self.assertEqual(self.row("name,title\nb!d,Title\n", create=True)["problem"],
                         "bad_name")

    def test_files_it_cant_read(self):
        self.assertEqual(vault_list.plan("title,lang\nA,en\n")["error"], "no_name")

    def test_columns_it_doesnt_know(self):
        result = vault_list.plan("name,titel\nnews,A\n")
        self.assertEqual(result["ignored"], ["titel"])
        self.assertEqual(result["counts"], {"same": 1})


class TestApply(VaultListTestCase):
    def test_saves_settings_and_lists(self):
        news = self.vaults["news"]
        news._commit = lambda: None
        news.update_search_index = lambda: None
        planned = vault_list.plan("name,over_18,default\nnews,yes,no\n")
        admin = SimpleNamespace(_id=9, _id36="9", name="admin")
        with patch("r2.models.ModAction.create") as logged, \
                patch.object(vault_admin, "set_listed") as listed:
            vault_list.apply(planned, admin)
        self.assertTrue(news.over_18)
        logged.assert_called_once()
        listed.assert_called_once_with(news, "default", False, admin)
