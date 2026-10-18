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

"""Boot the r2 app briefly to trigger automatic DB/CF creation.

Usage: python tools/bootstrap_db.py [--ini PATH_TO_INI]

Defaults to `r2/example.ini` and will load the PasteDeploy app which
initializes pylons app globals and triggers model/table creation when
`db_create_tables` is enabled in the ini.
"""
import argparse
import importlib
import os
import queue
import sys
import time
import traceback

from paste.deploy import loadapp

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ini', default='r2/example.ini', help='Path to ini (relative to repo root or absolute)')
    args = parser.parse_args()

    ini_path = args.ini

    # Resolve paths
    if not os.path.isabs(ini_path):
        ini_path = os.path.abspath(ini_path)

    if not os.path.exists(ini_path):
        print('INI file not found:', ini_path)
        return 2

    # The `relative_to` argument should be the directory containing the ini
    relative_to = os.path.dirname(ini_path)

    # Ensure the package import path includes the r2 package root
    repo_root = os.path.dirname(relative_to) if os.path.basename(relative_to) == 'r2' else relative_to
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    # Also add the r2 directory itself
    r2_dir = os.path.join(repo_root, 'r2')
    if os.path.isdir(r2_dir) and r2_dir not in sys.path:
        sys.path.insert(0, r2_dir)
    # Invalidate import caches so new path is recognized
    importlib.invalidate_caches()

    print('sys.path:', sys.path[:5])

    # Test that we can import r2 and its make_app
    try:
        import r2
        print('r2 module loaded from:', r2.__file__)
        print('r2 module attributes:', [a for a in dir(r2) if not a.startswith('_')])
        if hasattr(r2, 'make_app'):
            print('r2.make_app found:', r2.make_app)
        else:
            print('WARNING: r2.make_app not found!')
            # Try to import it directly
            try:
                from r2.config.middleware import make_app
                print('Direct import of make_app succeeded:', make_app)
            except Exception as e:
                print('Direct import of make_app failed:', e)
                traceback.print_exc()
    except Exception as e:
        print('Failed to import r2:', e)
        traceback.print_exc()
        return 4

    # Some tests expect this
    try:
        from baseplate.lib import events as baseplate_events
        baseplate_events.EventQueue = queue.Queue
    except Exception:
        pass

    print('Loading app from', ini_path)
    # Use PasteDeploy to load the app. This will initialize pylons app_globals
    # and (importantly) execute module-level code that creates tables/CFs
    # when `db_create_tables` is enabled in the ini.
    app_spec = 'config:' + os.path.basename(ini_path)
    try:
        wsgiapp = loadapp(app_spec, relative_to=relative_to)
    except Exception as e:
        print('Error loading app:', e)
        traceback.print_exc()
        return 3

    # Allow a short pause for any background initialization
    print('App loaded; waiting briefly for DB initialization to complete...')
    time.sleep(3)
    print('Done. If Postgres/Cassandra were reachable and `db_create_tables` is true, tables/CFs should be created.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
