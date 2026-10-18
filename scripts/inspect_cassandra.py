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

"""Inspect the app's Cassandra connection pool(s).

This is a read-only inspection helper intended to run in the app's
runtime environment (so `pylons.app_globals` is available).
"""
import sys
import argparse
from pylons import app_globals as g


def main():
    p = argparse.ArgumentParser(description='Inspect app Cassandra pools')
    p.add_argument('--quiet', action='store_true')
    args = p.parse_args()

    try:
        pools = getattr(g, 'cassandra_pools', {})
    except Exception as e:
        print('Error accessing app_globals.cassandra_pools:', e)
        sys.exit(1)

    for name, pool in pools.items():
        print(f'Pool: {name}')
        try:
            print('  server_list:', getattr(pool, 'server_list', None))
            cluster = getattr(pool, 'cluster', None)
            if cluster is not None:
                print('  contact_points:', getattr(cluster, 'contact_points', None))
                print('  metadata cluster name:', getattr(cluster, 'metadata', None) and getattr(cluster.metadata, 'cluster_name', None))
            session = getattr(pool, 'session', None)
            print('  session keyspace:', getattr(session, 'keyspace', None))
        except Exception as e:
            print('  error inspecting pool:', e)


if __name__ == '__main__':
    main()
