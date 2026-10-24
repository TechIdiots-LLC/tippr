# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################
"""Markdown: tippr's syntax, and output souptest accepts."""

import time
import unittest

from r2.lib.markdown import render
from r2.lib.souptest import souptest_fragment
from r2.lib.utils import extract_user_mentions


def md(text, **kw):
    html = render(text, **kw).strip()
    souptest_fragment(html)
    return html


class MarkdownTest(unittest.TestCase):
    def test_text(self):
        self.assertEqual(md("*a* **b** ~~c~~ `d`"),
                         "<p><em>a</em> <strong>b</strong> <del>c</del> "
                         "<code>d</code></p>")

    def test_superscript(self):
        self.assertEqual(md("2^10 and ^(two words)"),
                         "<p>2<sup>10</sup> and <sup>two words</sup></p>")
        self.assertEqual(md("*a^b*"), "<p><em>a<sup>b</sup></em></p>")
        self.assertEqual(md("a ^ b"), "<p>a ^ b</p>")

    def test_spoiler(self):
        spoiler = '<span class="md-spoiler-text">hidden</span>'
        self.assertEqual(md("a >!hidden!< b"), "<p>a %s b</p>" % spoiler)
        # at the start of a line, not a quote
        self.assertEqual(md(">!hidden!<"), "<p>%s</p>" % spoiler)
        self.assertIn("<blockquote>", md("> quoted"))

    def test_vault_and_user_links(self):
        html = md("/v/books, v/art+music, u/bob, /u/bob and /user/bob")
        for href in ('"/v/books"', '"/v/art+music"', '"/u/bob"'):
            self.assertIn("href=" + href, html)
        self.assertEqual(html.count('href="/u/bob"'), 3)
        # not in a path, a word or code
        self.assertNotIn("<a", md("and/v/books, `/v/books`"))

    def test_mentions(self):
        self.assertEqual(extract_user_mentions("hi u/Bob and /user/eve"),
                         {"bob", "eve"})

    def test_links(self):
        self.assertIn('href="https://example.com"', md("https://example.com"))
        self.assertIn('href="http://www.example.com"', md("www.example.com"))
        self.assertIn('href="https://example.com"',
                      md("[site](example.com)"))
        self.assertNotIn("<a", md("README.md"))
        self.assertNotIn("<a", md("[x](javascript:alert(1))"))
        self.assertNotIn("<a", md("[x](data:text/html,hi)"))

    def test_nofollow_and_target(self):
        html = md("https://example.com /v/books", nofollow=True,
                  target="_blank")
        self.assertIn('href="https://example.com" rel="nofollow" '
                      'target="_blank"', html)
        self.assertIn('<a href="/v/books" target="_blank">', html)

    def test_images(self):
        # a link to the picture, except in the wiki
        self.assertEqual(md("![a cat](https://example.com/cat.png)"),
                         '<p><a href="https://example.com/cat.png">a cat</a>'
                         '</p>')
        self.assertIn('<img src="%%cat%%" alt="a cat" />',
                      md("![a cat](%%cat%%)", wiki=True))

    def test_task_list(self):
        self.assertEqual(md("- [ ] to do\n- [x] done"),
                         '<ul>\n<li class="md-task">\u2610 to do</li>\n'
                         '<li class="md-task">\u2611 done</li>\n</ul>')

    def test_table(self):
        html = md("| a | b |\n|:-|-:|\n| 1 | 2 |")
        self.assertIn('<th align="left">a</th>', html)
        self.assertIn('<td align="right">2</td>', html)

    def test_code(self):
        self.assertEqual(md("```python\nif a < b:\n```"),
                         '<pre><code class="language-python">if a &lt; b:\n'
                         '</code></pre>')

    def test_no_html(self):
        self.assertEqual(md("<b onclick=x>hi</b> &copy;"),
                         "<p>&lt;b onclick=x&gt;hi&lt;/b&gt; \u00a9</p>")

    def test_control_characters(self):
        self.assertEqual(md("a\x01b\x0bc"), "<p>abc</p>")

    def test_unicode(self):
        self.assertEqual(md("caf\u00e9 \U0001f44d\U0001f3fd \u65e5\u672c"),
                         "<p>caf\u00e9 \U0001f44d\U0001f3fd \u65e5\u672c</p>")

    def test_pathological_text_is_quick(self):
        for text in ("^a" * 5000, "^(" * 5000, ">!a" * 3333 + "!<",
                     "[" * 10000, "*a" * 5000):
            start = time.time()
            md(text)
            self.assertLess(time.time() - start, 2, text[:10])
