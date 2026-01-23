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
Initialize Production Environment

This script initializes the required system objects for a production Tippr instance:
1. Creates the system user account (g.system_user)
2. Creates the automoderator account (if configured)
3. Creates required vaults (default, takedown, beta, promo)
4. Creates wiki pages for Terms of Use, Privacy Policy, Content Policy, 
   and Moderator Guidelines from the markdown files in docs/policies/

This is the production equivalent of inject_test_data.py but without the test content.

Usage:
    tippr-run /path/to/scripts/init_policy_wiki_pages.py
"""

import os
import sys


def main(root_dir=None):
    # Setup paths - handle both direct execution and tippr-run
    # Note: tippr-run changes to $TIPPR_SRC/tippr/r2 before running scripts,
    # so os.getcwd() will be the r2 directory and parent is tippr root.
    if root_dir is None:
        cwd = os.getcwd()
        
        # Try various paths to find the tippr root (contains docs/policies)
        possible_paths = [
            os.path.dirname(cwd),  # Parent of cwd (if cwd is r2/)
            os.path.dirname(os.path.dirname(cwd)),  # Grandparent (if cwd is r2/r2/)
            cwd,  # Current directory itself
            '/home/tippr/src/tippr',  # Common default
        ]
        
        for path in possible_paths:
            if path and os.path.exists(os.path.join(path, 'docs', 'policies')):
                root_dir = path
                break
        
        if root_dir is None:
            # Last resort: walk up from cwd until we find docs/policies
            check_dir = cwd
            for _ in range(5):  # Max 5 levels up
                if os.path.exists(os.path.join(check_dir, 'docs', 'policies')):
                    root_dir = check_dir
                    break
                parent = os.path.dirname(check_dir)
                if parent == check_dir:  # Reached filesystem root
                    break
                check_dir = parent
        
        if root_dir is None:
            root_dir = cwd
    
    r2_dir = os.path.join(root_dir, 'r2')
    
    print(f"Using root_dir: {root_dir}")
    
    # Import from already-loaded app (tippr-run loads the app before running scripts)
    from pylons import app_globals as g
    from r2.models.vault import Frontpage, Vault
    from r2.models.wiki import WikiPage
    from r2.models import Account, NotFound, register

    # Helper functions to ensure required objects exist
    def ensure_account(name):
        """Look up or create a user account and return it."""
        try:
            return Account._by_name(name)
        except NotFound:
            print(f">> Creating system user: {name}")
            return register(name, None, "127.0.0.1")  # No password = can't login directly

    def ensure_vault(name, author):
        """Look up or create a vault and return it."""
        try:
            v = Vault._by_name(name)
            print(f">> Found vault: /v/{name}")
            return v
        except NotFound:
            print(f">> Creating vault: /v/{name}")
            v = Vault._new(
                name=name,
                title=f"/v/{name}",
                author_id=author._id,
                lang="en",
                ip="127.0.0.1",
            )
            v._commit()
            return v

    # Ensure system user exists
    print("Ensuring required system objects exist...")
    system_user = ensure_account(g.system_user)
    
    # Ensure automoderator account exists
    if hasattr(g, 'automoderator_account') and g.automoderator_account:
        ensure_account(g.automoderator_account)
    
    # Ensure required vaults exist
    ensure_vault(g.default_vault, system_user)
    if hasattr(g, 'takedown_vault') and g.takedown_vault:
        ensure_vault(g.takedown_vault, system_user)
    if hasattr(g, 'beta_vault') and g.beta_vault:
        ensure_vault(g.beta_vault, system_user)
    if hasattr(g, 'promo_vault_name') and g.promo_vault_name:
        ensure_vault(g.promo_vault_name, system_user)
    
    print()

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
                import traceback
                print(f"  ERROR: Failed to create wiki page: {e}")
                traceback.print_exc()
                print()
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
