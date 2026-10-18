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
