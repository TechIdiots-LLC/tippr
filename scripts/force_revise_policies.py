#!/usr/bin/env python3
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

"""Revise existing WikiPages from docs/policies files.

This script performs mutations. It requires `--force` or TIPPR_ALLOW_MUTATE=1.
Use `--dry-run` to preview.
"""
import argparse
import os
import sys
from pylons import app_globals as g
from r2.models.vault import Frontpage
from r2.models.wiki import WikiPage, WikiRevision
from r2.models import Account


def parse_args():
    p = argparse.ArgumentParser(description='Revise policy wiki pages from docs/policies')
    p.add_argument('--root', help='Repository root (defaults to parent of scripts dir)')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true')
    return p.parse_args()


def main():
    args = parse_args()
    if not args.force and os.getenv('TIPPR_ALLOW_MUTATE') != '1':
        print('Refusing to run without --force or TIPPR_ALLOW_MUTATE=1')
        sys.exit(2)

    system_user = Account._by_name(g.system_user)
    policies = [g.wiki_page_user_agreement, g.wiki_page_privacy_policy, g.wiki_page_content_policy, getattr(g, 'wiki_page_moderator_guidelines', 'moderatorguidelines')]
    root = args.root or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    for wiki_name in policies:
        try:
            wp = WikiPage.get(Frontpage, wiki_name)
        except Exception as e:
            print('No page for', wiki_name, 'skipping', e)
            continue
        file_path = os.path.join(root, 'docs', 'policies', wiki_name.upper() + '.md')
        # fallback: try known filenames
        if not os.path.exists(file_path):
            mapping = {'useragreement': 'TERMS_OF_USE.md', 'privacypolicy': 'PRIVACY_POLICY.md', 'contentpolicy': 'CONTENT_POLICY.md', 'moderatorguidelines': 'MODERATOR_GUIDELINES.md'}
            file_path = os.path.join(root, 'docs', 'policies', mapping.get(wiki_name, ''))
        if not os.path.exists(file_path):
            print('Source file missing for', wiki_name, 'skipping')
            continue
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # this site's details in place of the templates' placeholders
        from r2.lib import site_info
        content = site_info.fill_policy(content)
        # "Last Revised" becomes today if the text changed (an unchanged
        # policy keeps its date, and isn't revised again)
        content, changed = site_info.stamp_revised(content, wp.content)
        if not changed:
            print('Unchanged:', wiki_name)
            continue
        print('Revising', wiki_name)
        if args.dry_run:
            print('DRY-RUN: would revise', wiki_name)
            continue
        try:
            wr = wp.revise(content, author=system_user, force=True, reason='Re-import from docs/policies')
            print('Created revision', getattr(wr, '_id', None))
        except Exception as e:
            print('Failed revise', wiki_name, e)


if __name__ == '__main__':
    main()
else:
    main()

