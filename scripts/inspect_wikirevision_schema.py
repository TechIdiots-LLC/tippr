"""Inspect the `wikirevision` table schema via the Datastax driver.

This script connects to Cassandra and prints columns and partition key.
"""
import argparse
from cassandra.cluster import Cluster


def main():
    p = argparse.ArgumentParser(description='Inspect wikirevision table schema')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', default=9042, type=int)
    args = p.parse_args()

    cl = Cluster([args.host])
    session = cl.connect()
    meta = cl.metadata
    ks = meta.keyspaces.get('tippr')
    if not ks:
        print('No keyspace tippr')
        return 1
    t = ks.tables.get('wikirevision')
    if not t:
        print('No table wikirevision')
        return 1
    print('columns:', list(t.columns.keys()))
    print('partition_key:', [c.name for c in t.partition_key])
    print('comment:', t.options.get('comment'))


if __name__ == '__main__':
    main()
