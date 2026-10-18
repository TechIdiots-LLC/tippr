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

"""
Small coworker script: perform repo-wide safe replacements to rename
`add_vault` -> `add_vault` and `_vault_path` -> `_vault_path` in templates and python files.
Run from the repo root and review changes before committing.
"""
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTS = {'.py', '.html', '.xml', '.mako', '.tmpl', '.js', '.css'}

REPLACEMENTS = [
    # function/call replacements
    (re.compile(r"\badd_sr\b"), 'add_vault'),
    # underscore variables
    (re.compile(r"\b_sr_path\b"), '_vault_path'),
    (re.compile(r"\b_sr\b"), '_vault'),
    # function-name variants
    (re.compile(r"\badd_sr_message_nolock\b"), 'add_vault_message_nolock'),
    (re.compile(r"\badd_srs\b"), 'add_vaults'),
]

SKIP_DIRS = {'venv', '.git', 'node_modules', 'build', 'dist'}

def should_edit(path: Path):
    if any(p in path.parts for p in SKIP_DIRS):
        return False
    if path.suffix.lower() in EXTS:
        return True
    return False


def process_file(path: Path):
    # Read raw bytes and try UTF-8, fall back to Latin-1 for legacy files
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8')
        used_encoding = 'utf-8'
    except UnicodeDecodeError:
        try:
            text = raw.decode('latin-1')
            used_encoding = 'latin-1'
        except Exception:
            # give up on this file
            raise

    new_text = text
    for pattern, repl in REPLACEMENTS:
        new_text = pattern.sub(repl, new_text)
    if new_text != text:
        bak = path.with_suffix(path.suffix + '.bak')
        # preserve original bytes in the backup
        bak.write_bytes(raw)
        # overwrite file with utf-8 encoded content
        path.write_text(new_text, encoding='utf-8')
        return True
    return False


def main():
    changed = []
    for p in ROOT.rglob('*'):
        if p.is_file() and should_edit(p):
            try:
                if process_file(p):
                    changed.append(str(p.relative_to(ROOT)))
            except Exception as e:
                print(f"Failed to process {p}: {e}")
    if changed:
        print('Modified files:')
        for c in changed:
            print(' -', c)
    else:
        print('No files modified')

if __name__ == '__main__':
    main()
