#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_FILES = {ROOT / 'LICENSE', ROOT / 'install' / 'done.sh'}

TEXT_EXTS = {'.py', '.sh', '.yml', '.yaml', '.md', '.cfg', '.ini', '.html', '.tmpl', '.less', '.js', '.css', '.json', '.conf', '.txt', '.pl', '.php', '.xml'}

CONTENT_PATTERNS = [
    (re.compile(r"\breddit\b"), 'tippr'),
    (re.compile(r"\bReddit\b"), 'Tippr'),
    (re.compile(r"\bREDDIT\b"), 'TIPPR'),
    (re.compile(r"\bsnoo\b"), 'tippr'),
    (re.compile(r"\bSnoo\b"), 'Tippr'),
    (re.compile(r"\bSNOO\b"), 'TIPPR'),
    (re.compile(r"reddit\s*,?\s*Inc\.?", re.IGNORECASE), 'TechIdiots LLC'),
]

SKIP_IF_CONTAINS = [
    'Common Public Attribution License',
    'The Original Code is reddit',
    'The Original Developer is the Initial Developer',
]

changed_files = []

def is_binary(path: Path):
    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:
                return True
    except Exception:
        return True
    return False

# 1) Replace content in text files
for p in ROOT.rglob('*'):
    if p.is_file():
        if p in EXCLUDE_FILES:
            continue
        if p.suffix.lower() not in TEXT_EXTS:
            # still check small text files without ext
            try:
                if p.suffix == '':
                    pass
                else:
                    continue
            except Exception:
                continue
        try:
            if is_binary(p):
                continue
            text = p.read_text(encoding='utf-8')
        except Exception:
            continue
        if any(keyword in text for keyword in SKIP_IF_CONTAINS):
            continue
        new_text = text
        for pattern, repl in CONTENT_PATTERNS:
            new_text = pattern.sub(repl, new_text)
        if new_text != text:
            p.write_text(new_text, encoding='utf-8')
            changed_files.append(str(p.relative_to(ROOT)))

# 2) Rename files and directories containing 'tippr' or 'snoo' (case-insensitive)
renamed = []
# Walk bottom-up to rename files before directories
for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
    dirp = Path(dirpath)
    # files
    for name in filenames:
        if re.search(r'tippr', name, re.IGNORECASE) or re.search(r'snoo', name, re.IGNORECASE):
            src = dirp / name
            newname = re.sub(r'tippr', 'tippr', name, flags=re.IGNORECASE)
            newname = re.sub(r'snoo', 'tippr', newname, flags=re.IGNORECASE)
            dst = dirp / newname
            if dst.exists():
                print(f"Skipping rename {src} -> {dst}: target exists", file=sys.stderr)
                continue
            try:
                src.rename(dst)
                renamed.append((str(src.relative_to(ROOT)), str(dst.relative_to(ROOT))))
            except Exception as e:
                print(f"Failed to rename {src}: {e}", file=sys.stderr)
    # directories
    for name in dirnames:
        if re.search(r'tippr', name, re.IGNORECASE) or re.search(r'snoo', name, re.IGNORECASE):
            src = dirp / name
            newname = re.sub(r'tippr', 'tippr', name, flags=re.IGNORECASE)
            newname = re.sub(r'snoo', 'tippr', newname, flags=re.IGNORECASE)
            dst = dirp / newname
            if dst.exists():
                print(f"Skipping rename {src} -> {dst}: target exists", file=sys.stderr)
                continue
            try:
                src.rename(dst)
                renamed.append((str(src.relative_to(ROOT)), str(dst.relative_to(ROOT))))
            except Exception as e:
                print(f"Failed to rename {src}: {e}", file=sys.stderr)

print('\nSummary:')
print(f'Content-updated files: {len(changed_files)}')
for f in changed_files[:50]:
    print(' -', f)
if len(changed_files) > 50:
    print(' - ...')
print(f'Renamed entries: {len(renamed)}')
for s, d in renamed[:50]:
    print(f' - {s} -> {d}')
if len(renamed) > 50:
    print(' - ...')

print('\nNext steps: review changes, stage and commit.')
