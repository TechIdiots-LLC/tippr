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
