#!/usr/bin/env python3
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
