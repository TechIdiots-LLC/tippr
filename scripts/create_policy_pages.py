"""
Create site policy wiki pages if they're missing.

Run this from the application's Python environment where the `r2` package
is importable. Example (from project root):

    # if you use a virtualenv, activate it first
    python scripts/create_policy_pages.py

Or run interactively in a paster/interactive shell if you prefer.

The script will attempt to read local files (docs/useragreement.md,
docs/privacypolicy.md) for content; if those files don't exist it will
create simple placeholders which you should edit via the wiki UI later.
"""

import os
import sys

from pylons import app_globals as g
from pylons import tmpl_context as c
from r2.models.vault import Frontpage
from r2.models.wiki import WikiPage, WikiRevision
from r2.models.account import Account
from r2.lib.db.tdb_cassandra import NotFound


CANDIDATE_FILES = {
    'useragreement': [
        'docs/useragreement.md',
        'docs/UserAgreement.md',
        'docs/USER_AGREEMENT.md',
    ],
    'privacypolicy': [
        'docs/privacypolicy.md',
        'docs/PrivacyPolicy.md',
        'docs/PRIVACY.md',
    ],
    'contentpolicy': [
        'docs/contentpolicy.md',
        'docs/ContentPolicy.md',
    ],
}

PLACEHOLDERS = {
    'useragreement': "This is a placeholder for the User Agreement.\n\nEdit this page in the wiki to add your full user agreement.",
    'privacypolicy': "This is a placeholder for the Privacy Policy.\n\nEdit this page in the wiki to add your full privacy policy.",
    'contentpolicy': "This is a placeholder for the Content Policy.\n\nEdit this page in the wiki to add your content policy.",
}


def _read_candidate(name):
    for path in CANDIDATE_FILES.get(name, []):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as fh:
                return fh.read()
    return None


def ensure_page(wiki_name, display_name):
    try:
        WikiPage.get(Frontpage, wiki_name)
        print('Wiki page exists: {}'.format(wiki_name))
        return
    except NotFound:
        print('Wiki page not found: {} — creating'.format(wiki_name))

    content = _read_candidate(wiki_name) or PLACEHOLDERS.get(wiki_name, '')

    # create the page and add a revision
    page = WikiPage.create(Frontpage, wiki_name)
    system_user = Account.system_user()
    try:
        page.revise(content, previous=None, author=(system_user and system_user._id36) or None, force=True)
    except Exception:
        # older code paths expect author id36 or None; try without author
        page.revise(content, previous=None, force=True)
    print('Created: {} (content length {})'.format(wiki_name, len(content)))


def main():
    # Use config values if available, otherwise fall back to defaults
    names = []
    try:
        names.append(g.wiki_page_user_agreement)
    except Exception:
        names.append('useragreement')
    try:
        names.append(g.wiki_page_privacy_policy)
    except Exception:
        names.append('privacypolicy')
    try:
        names.append(g.wiki_page_content_policy)
    except Exception:
        names.append('contentpolicy')

    # ensure uniqueness and known order
    names = [n for n in names if n]
    seen = set()
    names = [x for x in names if not (x in seen or seen.add(x))]

    for n in names:
        ensure_page(n, n)


if __name__ == '__main__':
    main()
