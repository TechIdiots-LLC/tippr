"""Scan WikiRevision rows and look for pages of interest.

This script can be heavy on large clusters; use `--limit` to control
how many rows to scan and `--match` to filter pageids.
"""
import argparse
from r2.models.wiki import WikiRevision


def main():
    p = argparse.ArgumentParser(description='Inspect WikiRevision rows')
    p.add_argument('--limit', type=int, default=5000)
    p.add_argument('--match', nargs='+', default=['useragreement', 'privacypolicy'])
    args = p.parse_args()

    count = 0
    for idx, (t_id, cols) in enumerate(WikiRevision._cf.get_range()):
        if idx >= args.limit:
            break
        try:
            wr = WikiRevision._from_serialized_columns(t_id, cols)
        except Exception:
            continue
        pid = getattr(wr, 'pageid', None)
        if pid and any(m in pid for m in args.match):
            print('FOUND REVID', t_id, 'pageid=', pid)
            count += 1
    print('COUNT', count)


if __name__ == '__main__':
    main()
