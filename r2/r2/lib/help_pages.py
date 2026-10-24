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
"""The pages under /help (r2.controllers.policies), and what they're called:
here so the sitemaps (r2.lib.sitemaps.live) can list them too."""

from collections import OrderedDict

from pylons.i18n import N_

# The help pages (/help/<name>): wiki pages help/<name> in the site wiki,
# loaded from docs/help/<name>.md by scripts/init_policy_wiki_pages.py.
# Keep config/routing.py's /help/:page requirements in step.
HELP_PAGES = OrderedDict([
    ("faq", N_("frequently asked questions")),
    ("search", N_("searching")),
    ("formatting", N_("formatting posts and comments")),
    ("rss", N_("RSS feeds")),
    ("trophies", N_("trophies")),
    ("suspensions", N_("timeouts and suspensions")),
    ("quarantine", N_("quarantined vaults")),
    ("muting", N_("muting in moderator mail")),
    ("automoderator", N_("AutoModerator")),
    ("api", N_("using the API")),
    ("advertising", N_("advertising")),
    ("translate", N_("translating")),
])

# the policies, also at /help/<name>
POLICY_PAGES = OrderedDict([
    ("useragreement", N_("user agreement")),
    ("privacypolicy", N_("privacy policy")),
    ("contentpolicy", N_("content policy")),
    ("moderatorguidelines", N_("moderator guidelines")),
])
