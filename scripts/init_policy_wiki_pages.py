#!/usr/bin/env python
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

"""
Initialize Wiki Policy Pages

This script initializes the wiki pages for Terms of Use, Privacy Policy,
Content Policy, and Moderator Guidelines from the markdown files in docs/policies/.

Run this script after setting up the database to populate the initial
policy wiki pages.

Usage:
    python scripts/init_policy_wiki_pages.py
"""

import os
import sys


def main(root_dir=None):
    # Setup paths - handle both direct execution and tippr-run
    if root_dir is None:
        # When run via tippr-run, the app is already loaded
        # Try to find root from current working directory or known paths
        if os.path.exists('/home/tippr/src/tippr/docs/policies'):
            root_dir = '/home/tippr/src/tippr'
        elif os.path.exists('docs/policies'):
            root_dir = os.getcwd()
        elif os.path.exists('../docs/policies'):
            root_dir = os.path.abspath('..')
        else:
            root_dir = os.getcwd()
    
    r2_dir = os.path.join(root_dir, 'r2')
    
    print(f"Using root_dir: {root_dir}")
    
    # Import from already-loaded app (tippr-run loads the app before running scripts)
    from pylons import app_globals as g
    from r2.models.vault import Frontpage
    from r2.models.wiki import WikiPage
    from r2.models import Account

    # Define the policy pages to create
    policies = [
        {
            'wiki_name': g.wiki_page_user_agreement,
            'file_path': os.path.join(root_dir, 'docs', 'policies', 'TERMS_OF_USE.md'),
            'display_name': 'User Agreement (Terms of Use)',
        },
        {
            'wiki_name': g.wiki_page_privacy_policy,
            'file_path': os.path.join(root_dir, 'docs', 'policies', 'PRIVACY_POLICY.md'),
            'display_name': 'Privacy Policy',
        },
        {
            'wiki_name': g.wiki_page_content_policy,
            'file_path': os.path.join(root_dir, 'docs', 'policies', 'CONTENT_POLICY.md'),
            'display_name': 'Content Policy',
        },
        {
            'wiki_name': getattr(g, 'wiki_page_moderator_guidelines', 'moderatorguidelines'),
            'file_path': os.path.join(root_dir, 'docs', 'policies', 'MODERATOR_GUIDELINES.md'),
            'display_name': 'Moderator Guidelines',
        },
    ]

    # Get or create system user
    try:
        system_user = Account.system_user()
    except Exception:
        # Fall back to admin user or first user
        print("Warning: Could not get system user, trying to find admin...")
        try:
            system_user = Account._by_name('admin')
        except Exception:
            print("Error: Could not find a user to author wiki pages.")
            print("Please create an admin user first.")
            return 1

    print(f"Using user '{system_user.name}' to create wiki pages.\n")

    # Create each policy page
    for policy in policies:
        wiki_name = policy['wiki_name']
        file_path = policy['file_path']
        display_name = policy['display_name']

        print(f"Processing: {display_name}")
        print(f"  Wiki page: {wiki_name}")
        print(f"  Source file: {file_path}")

        # Check if source file exists
        if not os.path.exists(file_path):
            print(f"  WARNING: Source file not found, skipping.\n")
            continue

        # Read the content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if wiki page already exists
        try:
            existing_page = WikiPage.get(Frontpage, wiki_name)
            print(f"  Wiki page already exists. Updating...")
            existing_page.revise(content, author=system_user, reason="Updated from docs/policies/")
            print(f"  SUCCESS: Updated {display_name}\n")
        except Exception:
            # Page doesn't exist, create it
            try:
                print(f"  Creating new wiki page...")
                wp = WikiPage.create(Frontpage, wiki_name)
                wp.revise(content, author=system_user, reason="Initial creation from docs/policies/")
                print(f"  SUCCESS: Created {display_name}\n")
            except Exception as e:
                print(f"  ERROR: Failed to create wiki page: {e}\n")
                continue

    print("=" * 60)
    print("Policy wiki pages initialization complete!")
    print("\nThe following pages are now available:")
    print("  - /help/useragreement")
    print("  - /help/privacypolicy")
    print("  - /help/contentpolicy")
    print("  - /help/moderatorguidelines")
    print("\nYou can edit these pages through the wiki interface.")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
else:
    # When loaded via tippr-run or paster run, execute main automatically
    main()
