#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTS = {'.py', '.sh', '.yml', '.yaml', '.md', '.cfg', '.ini', '.env', '.txt', '.conf', '.json'}

SKIP_PHRASES = [
    'Common Public Attribution License',
    'The Original Code is reddit',
]

changed = []

pattern_prefix = re.compile(r"\bREDDIT_([A-Za-z0-9_]+)\b")
pattern_word = re.compile(r"\bREDDIT\b")

for p in ROOT.rglob('*'):
    if not p.is_file():
        continue
    if p.suffix.lower() not in TEXT_EXTS and p.suffix != '':
        continue
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        continue
    if any(phrase in text for phrase in SKIP_PHRASES):
        # skip files containing license/legal header
        continue
    new_text = pattern_prefix.sub(r'TIPPR_\1', text)
    # replace standalone TIPPR -> TIPPR, avoid touching lowercase tippr
    new_text = pattern_word.sub('TIPPR', new_text)
    if new_text != text:
        p.write_text(new_text, encoding='utf-8')
        changed.append(str(p.relative_to(ROOT)))

print('Updated files:', len(changed))
for f in changed:
    print(' -', f)
print('\nReview before committing.')
