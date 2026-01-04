#!/usr/bin/env python3
import re
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_FILES = {ROOT / 'LICENSE', ROOT / 'install' / 'done.sh'}
TEXT_EXTS = {'.py', '.sh', '.yml', '.yaml', '.md', '.cfg', '.ini', '.html', '.tmpl', '.less', '.js', '.css', '.json', '.conf', '.txt', '.pl', '.php', '.xml'}

changed = []
renamed = []

# Replace in file contents
for p in ROOT.rglob('*'):
    if not p.is_file():
        continue
    if p in EXCLUDE_FILES:
        continue
    if p.suffix.lower() not in TEXT_EXTS and p.suffix != '':
        continue
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        continue
    if 'tippr.net' in text:
        new_text = text.replace('tippr.net', 'tippr.net')
        new_text = new_text.replace('www.tippr.net', 'www.tippr.net')
        if new_text != text:
            p.write_text(new_text, encoding='utf-8')
            changed.append(str(p.relative_to(ROOT)))

# Rename files/dirs containing 'tippr.net'
for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
    dirp = Path(dirpath)
    for name in filenames:
        if 'tippr.net' in name:
            src = dirp / name
            dst = dirp / name.replace('tippr.net', 'tippr.net')
            if dst.exists():
                print(f"Skipping rename {src} -> {dst}: target exists", file=sys.stderr)
                continue
            try:
                src.rename(dst)
                renamed.append((str(src.relative_to(ROOT)), str(dst.relative_to(ROOT))))
            except Exception as e:
                print(f"Failed to rename {src}: {e}", file=sys.stderr)
    for name in dirnames:
        if 'tippr.net' in name:
            src = dirp / name
            dst = dirp / name.replace('tippr.net', 'tippr.net')
            if dst.exists():
                print(f"Skipping rename {src} -> {dst}: target exists", file=sys.stderr)
                continue
            try:
                src.rename(dst)
                renamed.append((str(src.relative_to(ROOT)), str(dst.relative_to(ROOT))))
            except Exception as e:
                print(f"Failed to rename {src}: {e}", file=sys.stderr)

print('Changed files:', len(changed))
for f in changed:
    print(' -', f)
print('Renamed entries:', len(renamed))
for s, d in renamed:
    print(' -', s, '->', d)
print('\nNext: please review, stage and commit changes.')
