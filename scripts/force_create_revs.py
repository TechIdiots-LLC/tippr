#!/usr/bin/env python3
"""Create WikiRevision rows from docs/policies files.

This script mutates the database. It requires either `--force` on the
command-line or the environment variable `TIPPR_ALLOW_MUTATE=1` to actually
perform writes. Use `--dry-run` to preview the actions.
"""
import argparse
import os
import sys
from pylons import app_globals as g
from r2.models.vault import Frontpage
from r2.models.wiki import WikiPage, WikiRevision
from r2.models import Account


def parse_args():
    p = argparse.ArgumentParser(description='Create wiki revisions from docs/policies')
    p.add_argument('--root', help='Repository root (defaults to parent of scripts dir)')
    p.add_argument('--dry-run', action='store_true', help="Don't write; only show what would be done")
    p.add_argument('--force', action='store_true', help='Allow destructive writes')
    return p.parse_args()


def main():
    args = parse_args()

    if not args.force and os.getenv('TIPPR_ALLOW_MUTATE') != '1':
        print('Refusing to run without --force or TIPPR_ALLOW_MUTATE=1')
        sys.exit(2)

    root = args.root or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    system_user = Account._by_name(g.system_user)
    policies = [g.wiki_page_user_agreement, g.wiki_page_privacy_policy, g.wiki_page_content_policy, getattr(g, 'wiki_page_moderator_guidelines', 'moderatorguidelines')]
    mapping = {'useragreement': 'TERMS_OF_USE.md', 'privacypolicy': 'PRIVACY_POLICY.md', 'contentpolicy': 'CONTENT_POLICY.md', 'moderatorguidelines': 'MODERATOR_GUIDELINES.md'}

    for wiki_name in policies:
        try:
            wp = WikiPage.get(Frontpage, wiki_name)
        except Exception as e:
            print('No page for', wiki_name, 'skipping', e)
            continue

        file_path = os.path.join(root, 'docs', 'policies', mapping.get(wiki_name, ''))
        if not os.path.exists(file_path):
            print('Source file missing for', wiki_name, 'skipping')
            continue

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        print('Creating revision for', wiki_name)
        if args.dry_run:
            print('DRY-RUN: would create revision for', wiki_name)
            continue

        try:
            wr = WikiRevision.create(wp._id, content, author=system_user, reason='Import from docs/policies')
            print('Created revision', getattr(wr, '_id', None))
        except Exception as e:
            print('Failed create for', wiki_name, e)


if __name__ == '__main__':
    main()
