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
"""A page's description reads as the markdown does, not as its syntax."""

import unittest

from r2.lib.filters import markdown_text


class MarkdownTextTest(unittest.TestCase):
    def test_syntax_goes(self):
        self.assertEqual(
            markdown_text("Some **bold**, a [link](https://example.com) and `code`."),
            "Some bold, a link and code.")

    def test_one_line(self):
        self.assertEqual(markdown_text("A list:\n\n* one\n* two\n\n> quoted"),
                         "A list: one two quoted")

    def test_empty(self):
        self.assertEqual(markdown_text(""), "")
        self.assertEqual(markdown_text(None), "")
