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
"""The site-wide report reasons: kept in English, shown in the reader's
language, with the site's own name."""

from unittest.mock import patch

from r2.models import rules
from r2.tests import TipprTestCase


def translated(text):
    return "<%s>" % text


class TestSitewideRules(TipprTestCase):
    def setUp(self):
        for target, value in (
                ("r2.lib.site_info.policy_values",
                 lambda: {"SITE_NAME": "Example"}),
                ("r2.models.rules._", translated)):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def test_values_stay_english_labels_are_translated(self):
        pairs = rules.sitewide_rules()
        self.assertEqual(len(pairs), len(rules.SITEWIDE_RULES))
        self.assertEqual(pairs[0], ("Spam or vote manipulation",
                                    "<Spam or vote manipulation>"))

    def test_the_site_is_named(self):
        value, label = rules.sitewide_rules()[-1]
        self.assertEqual(value, "Breaking Example")
        self.assertEqual(label, "<Breaking Example>")
        self.assertNotIn("tippr", " ".join(v for v, l in
                                           rules.sitewide_rules()).lower())

    def test_reports_show_in_the_readers_language(self):
        self.assertEqual(rules.reason_label("Harassment or threats"),
                         "<Harassment or threats>")
        # a vault's rule, "other" text and old reasons as they are
        self.assertEqual(rules.reason_label("no memes"), "no memes")
        self.assertEqual(rules.reason_label("vote manipulation"),
                         "vote manipulation")
