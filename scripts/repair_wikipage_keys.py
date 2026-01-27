#!/usr/bin/env python3
"""Repair wikipage keys that contain an escaped backslash+t sequence ("\\t").

This script is non-destructive by default: it exports `tippr.wikipage` with
`cqlsh COPY`, finds keys containing a literal backslash+"t" sequence, and
creates a corrected CSV where the key has a real tab (0x09) instead. With
`--apply` the corrected rows are imported back into Cassandra to create
duplicate rows under the corrected keys (original rows are left intact).

Usage:
  repair_wikipage_keys.py --preview
  repair_wikipage_keys.py --apply

Requires `cqlsh` on PATH and permission to read/write /tmp files.
"""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path


EXPORT_CSV = Path('/tmp/wikipage_full.csv')
CORRECTED_CSV = Path('/tmp/wikipage_wikipage_corrected.csv')


def run_cmd(cmd):
    print('RUN:', ' '.join(cmd))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res


def export_wikipage():
    if EXPORT_CSV.exists():
        print('Removing existing', EXPORT_CSV)
        EXPORT_CSV.unlink()
    cmd = ['cqlsh', '-e', f"COPY tippr.wikipage TO '{EXPORT_CSV}' WITH HEADER = TRUE;"]
    r = run_cmd(cmd)
    if r.returncode != 0:
        print('EXPORT failed:', r.stderr.decode('utf-8', 'replace'))
        sys.exit(1)
    print('Exported to', EXPORT_CSV)


def preview_and_prepare():
    with EXPORT_CSV.open('r', newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if 'key' not in (reader.fieldnames or []):
        print('Unexpected CSV header:', reader.fieldnames)
        sys.exit(1)

    matches = []
    for r in rows:
        k = r['key']
        if k and ('\\t' in k or '\\t' in k):
            # When CSV contains escaped backslashes they appear as '\\t' in file,
            # but csv module will give a Python string with '\t' sequence; we
            # search for backslash+"t" and replace that with a literal tab.
            if '\\t' in k:
                # defensive: normalize double-backslash to single-backslash
                k_norm = k.replace('\\\\t', '\\t')
            else:
                k_norm = k
            if '\\t' in k_norm:
                corrected = k_norm.replace('\\t', '\t')
            else:
                continue
            matches.append((k, corrected, r))

    print('Found', len(matches), 'matching rows (escaped \\t -> will become real tab)')
    sample = matches[:20]
    for old, new, _ in sample:
        print('OLD_REPR:', repr(old))
        print('NEW_REPR:', repr(new))

    if not matches:
        print('No keys found to repair.')
        return matches

    # write corrected CSV with same headers but corrected key values
    # Use a tab delimiter so this CSV can be imported with
    # `COPY ... WITH DELIMITER='\t'` without needing a header-tweak hack.
    header = reader.fieldnames
    with CORRECTED_CSV.open('w', newline='', encoding='utf-8') as outfh:
        writer = csv.DictWriter(outfh, fieldnames=header, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for old, new, row in matches:
            row_copy = dict(row)
            row_copy['key'] = new
            writer.writerow(row_copy)

    print('Wrote corrected rows to', CORRECTED_CSV)
    return matches


def apply_import():
    if not CORRECTED_CSV.exists():
        print('Corrected CSV not found:', CORRECTED_CSV)
        sys.exit(1)
    # Use an actual tab character in the COPY command string so cqlsh sees a
    # 1-character delimiter. subprocess will pass this as a single -e arg.
    tab = '\t'
    cmd = ['cqlsh', '-e', f"COPY tippr.wikipage (key, columns) FROM '{CORRECTED_CSV}' WITH DELIMITER = '{tab}' AND HEADER = TRUE;"]
    r = run_cmd(cmd)
    if r.returncode != 0:
        print('IMPORT failed:', r.stderr.decode('utf-8', 'replace'))
        sys.exit(1)
    print('Import succeeded from', CORRECTED_CSV)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('--preview', '--apply'):
        print('Usage: repair_wikipage_keys.py --preview|--apply')
        sys.exit(1)

    mode = sys.argv[1]
    print('Mode:', mode)
    export_wikipage()
    matches = preview_and_prepare()
    if mode == '--apply':
        if not matches:
            print('Nothing to apply.')
            return
        print('Applying corrected rows into Cassandra (non-destructive).')
        apply_import()
        print('Done. Verify rows and endpoints before removing old keys.')


if __name__ == '__main__':
    main()
