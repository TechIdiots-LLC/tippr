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

from BeautifulSoup import BeautifulSoup, Tag
from pylons import app_globals as g
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.controllers.tippr_base import TipprController
from r2.lib.base import abort
from r2.lib.db import tdb_cassandra
from r2.lib.filters import generate_table_of_contents, unsafe, wikimarkdown
from r2.lib.pages import PolicyPage, PolicyView
from r2.lib.validator import nop, validate
from r2.models.vault import Frontpage
from r2.models.wiki import WikiBadRevision, WikiPage, WikiRevision


class PoliciesController(TipprController):
    @validate(requested_rev=nop('v'))
    def GET_policy_page(self, page, requested_rev):
        # runtime debug: log host, page and request info to aid diagnosis
        try:
            with open('/tmp/help_page_debug.log', 'a') as _dbg:
                _dbg.write(f"POLICIES REQUEST host={getattr(c, 'cur_domain', '')} page={page} requested_rev={requested_rev}\n")
        except Exception:
            pass

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
        else:
            abort(404)

        try:
            wp = WikiPage.get(Frontpage, wiki_name)
        except tdb_cassandra.NotFound:
            # Debugging 404s
            import sys
            try:
                debug_id = WikiPage.id_for(Frontpage, wiki_name)
                try:
                    with open('/tmp/help_page_debug.log', 'a') as _dbg:
                        _dbg.write(f"PoliciesController 404: WikiPage '{wiki_name}' not found. ID: '{debug_id}'. Frontpage: {Frontpage}\n")
                except Exception:
                    pass
                sys.stderr.write(f"PoliciesController 404: WikiPage '{wiki_name}' not found. ID: '{debug_id}'. Frontpage: {Frontpage}\n")
            except Exception as e:
                try:
                    with open('/tmp/help_page_debug.log', 'a') as _dbg:
                        _dbg.write(f"PoliciesController 404: Error generating debug ID: {e}\n")
                except Exception:
                    pass
                sys.stderr.write(f"PoliciesController 404: Error generating debug ID: {e}\n")
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

        # log revision lookup outcome
        try:
            with open('/tmp/help_page_debug.log', 'a') as _dbg:
                _dbg.write(f"PoliciesController: page={page} wiki_name={wiki_name} wp_id={getattr(wp, '_id', None)} revs_found={len(revs)}\n")
        except Exception:
            pass

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

        doc_html = wikimarkdown(display_rev.content, include_toc=True)
        if isinstance(doc_html, bytes):
            soup = BeautifulSoup(doc_html.decode('utf-8'))
        else:
            soup = BeautifulSoup(doc_html)
        # Prefer TOC produced by wikimarkdown when available; avoid calling
        # generate_table_of_contents directly to prevent builder mismatches.
        toc_el = soup.find('div', 'toc')
        toc = toc_el if toc_el is not None else ''
        self._number_sections(soup)
        self._linkify_headings(soup)

        content = PolicyView(
            body_html=unsafe(soup),
            toc_html=unsafe(toc),
            revs=rev_info,
            display_rev=str(display_rev._id),
        )
        return PolicyPage(
            pagename=pagename,
            content=content,
        ).render()

    def _number_sections(self, soup):
        count = 1
        for para in soup.find('div', 'md').findAll(['p'], recursive=False):
            try:
                a = soup.new_tag('a')
                a['class'] = 'p-anchor'
                a['id'] = 'p_%d' % count
                a['href'] = '#p_%d' % count
                a.string = str(count)
                para.insert(0, a)
                para.insert(1, ' ')
            except Exception:
                # Fallback for older BeautifulSoup versions
                a = Tag(soup, 'a', [
                    ('class', 'p-anchor'),
                    ('id', 'p_%d' % count),
                    ('href', '#p_%d' % count),
                ])
                a.append(str(count))
                para.insert(0, a)
                para.insert(1, ' ')
            count += 1

    def _linkify_headings(self, soup):
        md_el = soup.find('div', 'md')
        for heading in md_el.findAll(['h1', 'h2', 'h3'], recursive=False):
            heading_a = Tag(soup, "a", [('href', '#%s' % heading['id'])])
            heading_a.contents = heading.contents
            heading.contents = []
            heading.append(heading_a)
