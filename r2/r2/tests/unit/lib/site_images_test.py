#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""Replacing the site's images (r2.lib.site_images)."""

import io
import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from r2.lib import site_images
from r2.tests import TipprTestCase


def png(size=(10, 10)):
    data = io.BytesIO()
    Image.new("RGBA", size).save(data, "PNG")
    return data.getvalue()


# as nymph and the build leave them: sprite rules name the sheet and a
# position, others the image relative to static/
STYLESHEET = (
    ".arrow.up{background-image:url(sprite-tippr.abc.png);"
    "background-position:-0px -20px;background-repeat:no-repeat}"
    ".arrow.up:hover{background-image:url(sprite-tippr.abc.png);"
    "background-position:-16px -20px;background-repeat:no-repeat}"
    "@media (min-resolution:2dppx){.alert{background-image:url(sprite-tippr.abc.png);"
    "background-position:-0px -0px;background-repeat:no-repeat;"
    "background-size:20px 30px}}"
    ".coin{background:url(gold/gold-coin.png) no-repeat right}"
    ".big{background:url(\"../logo.png\") 0 0/50px 20px!important}"
    "ul.x{list-style-image:url(bullet.png)}"
    ".svg{background-image:url('data:image/svg+xml;base64,e30=')}"
    "@font-face{font-family:x;src:url(font.woff)}"
)
MANIFEST = {
    "sprite": "sprite-tippr.abc.png",
    "size": [40, 60],
    "images": [
        {"files": ["../alert_2x.png"], "x": 0, "y": 0, "width": 40,
         "height": 20, "stretch": False},
        {"files": ["../aupgray.png"], "x": 0, "y": 20, "width": 15,
         "height": 14, "stretch": False},
        {"files": ["../aupmod.png", "../aupmod-copy.png"], "x": 16, "y": 20,
         "width": 15, "height": 14, "stretch": False},
    ],
}


class SiteImagesTestCase(TipprTestCase):
    def setUp(self):
        site_images._cache.clear()
        self.addCleanup(site_images._cache.clear)
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        static = os.path.join(self.root, "static")
        os.makedirs(os.path.join(static, "gold"))
        os.makedirs(os.path.join(static, "awards"))
        for name, size in (("aupgray.png", (15, 14)), ("aupmod.png", (15, 14)),
                           ("aupmod-copy.png", (15, 14)),
                           ("alert.png", (20, 10)), ("alert_2x.png", (40, 20)),
                           ("gold/gold-coin.png", (16, 16)),
                           ("logo.png", (100, 40)), ("bullet.png", (4, 4)),
                           ("awards/trophy.png", (40, 40)),
                           ("sprite-tippr.png", (40, 60))):
            with open(os.path.join(static, name), "wb") as f:
                f.write(png(size))
        with open(os.path.join(static, "tippr.css"), "w") as f:
            f.write(STYLESHEET)
        with open(os.path.join(static, "sprite-tippr.json"), "w") as f:
            json.dump(MANIFEST, f)
        self.saved = {}
        g = SimpleNamespace(paths={"static_files": self.root},
                            static_names={}, log=SimpleNamespace(
                                exception=lambda *a, **kw: None))
        patches = [
            patch.object(site_images, "g", g),
            patch.object(site_images, "replacements", lambda: self.saved),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def replace(self, path, url):
        self.saved[path] = {"url": url, "size": [10, 10]}


class TestCatalogue(SiteImagesTestCase):
    def test_lists_the_images_but_not_sprites_or_awards(self):
        paths = set(site_images.catalogue())
        self.assertIn("aupgray.png", paths)
        self.assertIn("gold/gold-coin.png", paths)
        self.assertNotIn("sprite-tippr.png", paths)
        self.assertNotIn("awards/trophy.png", paths)
        self.assertEqual(site_images.catalogue()["logo.png"].size, (100, 40))

    def test_images_the_stylesheets_use(self):
        self.assertEqual(site_images.in_stylesheets(), {
            "aupgray.png", "aupmod.png", "aupmod-copy.png", "alert_2x.png",
            "gold/gold-coin.png", "logo.png", "bullet.png"})


class TestStylesheet(SiteImagesTestCase):
    def test_nothing_replaced(self):
        self.assertEqual(site_images.stylesheet_css("tippr.css"), "")

    def test_a_sprited_image(self):
        self.replace("aupgray.png", "https://media.example/up.png")
        self.assertEqual(
            site_images.stylesheet_css("tippr.css"),
            '.arrow.up{background-image:url("https://media.example/up.png");'
            "background-position:0 0;background-size:15px 14px}")

    def test_identical_images_share_a_place_in_the_sprite(self):
        self.replace("aupmod-copy.png", "https://media.example/m.png")
        self.assertIn(".arrow.up:hover{", site_images.stylesheet_css("tippr.css"))

    def test_double_size_version_in_its_media_block(self):
        # the 1x replacement stands in for alert_2x.png, at its size on the
        # page (the sheet's background-size halves it)
        self.replace("alert.png", "https://media.example/alert.png")
        self.assertEqual(
            site_images.stylesheet_css("tippr.css"),
            '@media (min-resolution:2dppx){.alert{background-image:'
            'url("https://media.example/alert.png");background-position:0 0;'
            "background-size:20px 10px}}")

    def test_not_sprited(self):
        self.replace("gold/gold-coin.png", "https://media.example/coin.png")
        self.replace("logo.png", "https://media.example/logo.png")
        self.replace("bullet.png", "https://media.example/b.png")
        css = site_images.stylesheet_css("tippr.css").split("\n")
        self.assertEqual(css, [
            # shown at the original's size
            '.coin{background-image:url("https://media.example/coin.png");'
            "background-size:16px 16px}",
            # the rule sets its size, and wins with !important
            '.big{background-image:url("https://media.example/logo.png")'
            "!important}",
            'ul.x{list-style-image:url("https://media.example/b.png")}',
        ])

    def test_unsafe_addresses_are_left_out(self):
        self.replace("aupgray.png", "https://media.example/x.png)</style>")
        self.assertEqual(site_images.stylesheet_css("tippr.css"), "")

    def test_follows_changes(self):
        self.assertEqual(site_images.stylesheet_css("tippr.css"), "")
        self.replace("aupgray.png", "https://media.example/up.png")
        self.assertIn(".arrow.up{", site_images.stylesheet_css("tippr.css"))


class TestReplacementUrl(SiteImagesTestCase):
    def test_paths(self):
        self.replace("gold/gold-coin.png", "http://media.example/coin.png")
        for path in ("gold/gold-coin.png", "/static/gold/gold-coin.png",
                     "../gold/gold-coin.png"):
            self.assertEqual(site_images.replacement_url(path),
                             "https://media.example/coin.png")
        self.assertIsNone(site_images.replacement_url("aupgray.png"))

    def test_js_overrides(self):
        self.replace("alert.png", "https://media.example/a.png")
        self.assertEqual(site_images.js_overrides(),
                         {"alert.png": "https://media.example/a.png"})


class TestStore(SiteImagesTestCase):
    def setUp(self):
        super().setUp()
        self.put = []
        site_images.g.media_provider = SimpleNamespace(
            put=lambda category, name, data: self.put.append(name) or
            "http://media.example/" + name)

    def test_stores_an_image(self):
        entry, error = site_images.store("gold/gold-coin.png", png((32, 32)))
        self.assertIsNone(error)
        self.assertEqual(entry["size"], [32, 32])
        self.assertTrue(self.put[0].startswith("site-gold-gold-coin-"))
        self.assertTrue(entry["url"].endswith(".png"))

    def test_refuses_what_isnt_an_image(self):
        entry, error = site_images.store("aupgray.png", b"<svg></svg>")
        self.assertIsNone(entry)
        self.assertTrue(error)
        self.assertEqual(self.put, [])

    def test_refuses_unknown_images(self):
        entry, error = site_images.store("../../etc/passwd", png())
        self.assertIsNone(entry)
        self.assertTrue(error)

    def test_refuses_huge_images(self):
        entry, error = site_images.store("aupgray.png", png((4001, 10)))
        self.assertIsNone(entry)
        self.assertTrue(error)
