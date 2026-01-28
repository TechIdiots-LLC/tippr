#!/usr/bin/env python3
"""Import policy wiki pages by generating pickled blobs and issuing CQL UPDATEs
via snap cqlsh. This avoids app-driver issues and creates rows visible to cqlsh.
"""
import os
import time
import pickle
import subprocess
from pathlib import Path

DOC_DIR = Path(os.getenv('TIPPR_DOC_DIR', '/opt/tippr/docs/policies'))
PAGES = {
    'useragreement': 'TERMS_OF_USE.md',
    'privacypolicy': 'PRIVACY_POLICY.md',
    'contentpolicy': 'CONTENT_POLICY.md',
    'moderatorguidelines': 'MODERATOR_GUIDELINES.md',
}
KEY_PREFIX = '1\t'  # vault 1 + tab


def dump_pickle_hex(value):
    now_us = int(time.time() * 1e6)
    data = pickle.dumps((value, now_us))
    return data.hex()


def run_cql(cql, host='127.0.0.1', port='9042', user='cassandra', password='cassandra'):
    # Prefer a system-installed `cqlsh` if available, otherwise fall back to
    # the snap-provided one. This makes the script work on clean installs where
    # `cqlsh` was installed via apt or pip instead of snap.
    system_cmd = ['cqlsh', host, port, '-u', user, '-p', password, '-e', cql]
    snap_cmd = ['snap', 'run', 'cqlsh', host, port, '-u', user, '-p', password, '-e', cql]

    for cmd in (system_cmd, snap_cmd):
        try:
            print('RUN:', ' '.join(cmd))
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            # Command not found; try the next option
            print('Command not found:', cmd[0])
            continue
        if r.returncode != 0:
            print('CQL ERROR:', r.stderr.decode('utf-8', 'replace'))
            return False
        return True

    print('No cqlsh binary found (tried system and snap).')
    return False


def main():
    import argparse
    p = argparse.ArgumentParser(description='Import policy pages into Cassandra via cqlsh')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true')
    p.add_argument('--host', default=os.getenv('CASSANDRA_HOST', '127.0.0.1'))
    p.add_argument('--port', default=os.getenv('CASSANDRA_PORT', '9042'))
    p.add_argument('--user', default=os.getenv('CASSANDRA_USER', 'cassandra'))
    p.add_argument('--password', default=os.getenv('CASSANDRA_PASS', 'cassandra'))
    p.add_argument('--docdir', default=os.getenv('TIPPR_DOC_DIR', str(DOC_DIR)))
    args = p.parse_args()

    if not args.force and os.getenv('TIPPR_ALLOW_MUTATE') != '1':
        print('Refusing to run without --force or TIPPR_ALLOW_MUTATE=1')
        return 2

    docdir = Path(args.docdir)
    for name, fname in PAGES.items():
        path = docdir / fname
        if not path.exists():
            print('Missing', path)
            continue
        content = path.read_text(encoding='utf-8')
        key = KEY_PREFIX + name
        cols = {
            'content': content,
            'name': name,
            'vault': '1',
            'permlevel': '0',
            'date': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()),
        }
        map_entries = []
        for colname, val in cols.items():
            hexblob = dump_pickle_hex(val)
            map_entries.append(f"'{colname}': 0x{hexblob}")
        map_literal = '{' + ', '.join(map_entries) + '}'
        key_escaped = key.replace("\\t", "\t")
        cql = f"UPDATE tippr.wikipage SET columns = columns + {map_literal} WHERE key = '{key_escaped}';"
        print('Prepared CQL for', name)
        if args.dry_run:
            print('DRY-RUN:', cql)
            continue
        ok = run_cql(cql, host=args.host, port=str(args.port), user=args.user, password=args.password)
        if not ok:
            print('Failed to write', name)
        else:
            print('Wrote', name)

if __name__ == '__main__':
    main()
