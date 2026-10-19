# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

from collections import OrderedDict

from bs4 import BeautifulSoup
from pylons import app_globals as g
from pylons import tmpl_context as c
from pylons.i18n import N_, _

from r2.controllers.tippr_base import TipprController
from r2.lib.base import abort
from r2.lib.db import tdb_cassandra
from r2.lib.filters import generate_table_of_contents, unsafe, wikimarkdown
from r2.lib.pages import HelpIndex, PolicyPage, PolicyView
from r2.lib.validator import nop, validate
from r2.models.vault import Frontpage
from r2.models.wiki import WikiBadRevision, WikiPage, WikiRevision


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
    ("api", N_("using the API")),
    ("advertising", N_("advertising")),
    ("translate", N_("translating")),
])


def help_wiki_name(page):
    return "help/" + page


class PoliciesController(TipprController):
    def GET_help_index(self):
        """/help: the help pages and the policies."""
        pages = [(name, _(title)) for name, title in HELP_PAGES.items()]
        policies = [
            ("useragreement", _("user agreement")),
            ("privacypolicy", _("privacy policy")),
            ("contentpolicy", _("content policy")),
            ("moderatorguidelines", _("moderator guidelines")),
        ]
        return PolicyPage(pagename=_("help"), help_page=True,
                          content=HelpIndex(pages=pages, policies=policies),
                          ).render()

    @validate(requested_rev=nop('v'))
    def GET_policy_page(self, page, requested_rev):
        if c.render_style == 'compact':
            self.redirect('/wiki/' + page)
        if page == 'privacypolicy':
            wiki_name = g.wiki_page_privacy_policy
            pagename = _('privacy policy')
        elif page == 'useragreement':
            wiki_name = g.wiki_page_user_agreement
            pagename = _('user agreement')
        elif page == 'contentpolicy':
            wiki_name = g.wiki_page_content_policy
            pagename = _('content policy')
        elif page == 'moderatorguidelines':
            wiki_name = g.wiki_page_moderator_guidelines
            pagename = _('moderator guidelines')
        elif page in HELP_PAGES:
            wiki_name = help_wiki_name(page)
            pagename = _(HELP_PAGES[page])
        else:
            abort(404)
        is_help = page in HELP_PAGES

        try:
            wp = WikiPage.get(Frontpage, wiki_name)
        except tdb_cassandra.NotFound:
            abort(404)

        revs = list(wp.get_revisions())

        if not revs:
            # No revisions found via the view; fallback to scanning the
            # `wikirevision` column family directly to find revisions for
            # this page (works around view indexing mismatches).
            try:
                revs = []
                for t_id, cols in WikiRevision._cf.get_range():
                    wr = WikiRevision._from_serialized_columns(t_id, cols)
                    if getattr(wr, 'pageid', None) == wp._id:
                        revs.append(wr)
                # sort by timeuuid (newest first) if possible
                revs.sort(key=lambda r: getattr(r._id, 'time', 0), reverse=True)
            except Exception:
                revs = []

        if not revs:
            # No revisions found for this wiki page — treat as not found
            abort(404)

        # collapse minor edits into revisions with reasons
        rev_info = []
        last_edit = None
        for rev in revs:
            if rev.is_hidden:
                continue

            if not last_edit:
                last_edit = rev

            if rev._get('reason'):
                rev_info.append({
                    'id': str(last_edit._id),
                    'title': rev._get('reason'),
                })
                last_edit = None

        if requested_rev:
            try:
                display_rev = WikiRevision.get(requested_rev, wp._id)
            except (tdb_cassandra.NotFound, WikiBadRevision):
                abort(404)
        else:
            display_rev = revs[0]

        doc_html = wikimarkdown(display_rev.content, include_toc=False)
        if isinstance(doc_html, bytes):
            soup = BeautifulSoup(doc_html.decode('utf-8'), 'html.parser')
        else:
            soup = BeautifulSoup(doc_html, 'html.parser')
        # The table of contents goes in the side column, not the body.
        toc = generate_table_of_contents(soup, prefix='section') or ''
        if not is_help:
            # numbered paragraphs, to refer to; help pages don't need them
            self._number_sections(soup)
        self._linkify_headings(soup)

        content = PolicyView(
            body_html=unsafe(soup),
            toc_html=unsafe(toc),
            revs=[] if is_help else rev_info,
            display_rev=str(display_rev._id),
        )
        return PolicyPage(
            pagename=pagename,
            content=content,
            help_page=is_help,
        ).render()

    def _number_sections(self, soup):
        count = 1
        for para in soup.find('div', 'md').find_all(['p'], recursive=False):
            a = soup.new_tag('a', href='#p_%d' % count,
                             attrs={'class': 'p-anchor', 'id': 'p_%d' % count})
            a.string = str(count)
            para.insert(0, a)
            para.insert(1, ' ')
            count += 1

    def _linkify_headings(self, soup):
        md_el = soup.find('div', 'md')
        for heading in md_el.find_all(['h1', 'h2', 'h3'], recursive=False):
            heading_a = soup.new_tag('a', href='#%s' % heading['id'])
            # Move the children with extract(): assigning .contents directly
            # (the BeautifulSoup 3 idiom) leaves bs4's tree links pointing at
            # the old parent, and serialization then stops at this heading.
            for child in list(heading.contents):
                heading_a.append(child.extract())
            heading.append(heading_a)
