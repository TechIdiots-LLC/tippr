#!/usr/bin/env python3
"""
Comprehensive Tippr -> Tippr Rebranding Script

This script systematically renames all tippr references to tippr while
PRESERVING license headers as required by the CPAL license.

Usage:
    python rebrand_to_tippr.py --dry-run     # Preview changes without modifying
    python rebrand_to_tippr.py               # Apply changes
    python rebrand_to_tippr.py --verbose     # Show detailed output

The script handles:
1. Content replacement in source files (preserving license headers)
2. File and directory renaming
3. vault -> vault renaming (configurable via rebrand_config.py)
4. URL updates (tippr.net -> tippr.net)
5. Cookie, variable, and class name updates

Configuration:
    Edit rebrand_config.py to customize:
    - SUBREDDIT_REPLACEMENT: "vault" or "subtippr"
    - Domain mappings
    - Special term handling
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Set, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Import configuration
try:
    from rebrand_config import (
        SUBREDDIT_REPLACEMENT,
        URL_PREFIX_MAP,
        OLD_DOMAIN,
        NEW_DOMAIN,
        SUBDOMAIN_MAP,
        PRESERVED_PATTERNS,
        SKIP_FILES,
        SKIP_DIRECTORIES,
        MULTIREDDIT_REPLACEMENT,
        GOLD_REPLACEMENT,
        RENAME_COOKIES,
    )
    CONFIG_LOADED = True
except ImportError:
    print("Warning: Could not import rebrand_config.py, using defaults")
    CONFIG_LOADED = False
    SUBREDDIT_REPLACEMENT = "vault"
    URL_PREFIX_MAP = {"vault": "/v/", "subtippr": "/s/", None: "/v/"}
    OLD_DOMAIN = "tippr.net"
    NEW_DOMAIN = "tippr.net"
    SUBDOMAIN_MAP = {}
    PRESERVED_PATTERNS = []
    SKIP_FILES = []
    SKIP_DIRECTORIES = [".git", "node_modules", "__pycache__"]
    MULTIREDDIT_REPLACEMENT = "multivault"
    GOLD_REPLACEMENT = None
    RENAME_COOKIES = True

# =============================================================================
# CONFIGURATION
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

# Compute vault replacement values based on config
if SUBREDDIT_REPLACEMENT == "vault":
    SR_SINGULAR = "vault"
    SR_SINGULAR_CAP = "Vault"
    SR_PLURAL = "vaults"
    SR_PLURAL_CAP = "Vaults"
    SR_URL_PREFIX = "/v/"
elif SUBREDDIT_REPLACEMENT == "subtippr":
    SR_SINGULAR = "subtippr"
    SR_SINGULAR_CAP = "Subtippr"
    SR_PLURAL = "subtipprs"
    SR_PLURAL_CAP = "Subtipprs"
    SR_URL_PREFIX = "/s/"
else:
    # Keep as vault
    SR_SINGULAR = "vault"
    SR_SINGULAR_CAP = "Vault"
    SR_PLURAL = "vaults"
    SR_PLURAL_CAP = "Vaults"
    SR_URL_PREFIX = "/v/"

# Files to completely exclude from processing
EXCLUDE_PATHS = {
    ROOT / 'LICENSE',
    ROOT / 'CPAL_LICENSE.txt',
    ROOT / '.git',
}

# File extensions to process
TEXT_EXTENSIONS = {
    '.py', '.sh', '.yml', '.yaml', '.md', '.cfg', '.ini', '.html', '.mako',
    '.tmpl', '.less', '.js', '.jsx', '.ts', '.tsx', '.css', '.scss',
    '.json', '.conf', '.txt', '.pl', '.php', '.xml', '.rst', '.update',
    '.sql', '.cql', '.erb', '.rake', '.gemspec', '.gradle',
}

# =============================================================================
# LICENSE HEADER DETECTION
# =============================================================================

# These patterns identify license header blocks that must be preserved
LICENSE_MARKERS = [
    'Common Public Attribution License',
    'http://code.reddit.com/LICENSE',
    'The Original Code is tippr',
    'The Original Developer is the Initial Developer',
    'Initial Developer of the Original Code is tippr Inc',
    'All portions of the code written by tippr are Copyright',
    'tippr Inc. All Rights Reserved',
    'EXHIBIT A',
    'EXHIBIT B',
]

# Regex to identify the license header block (typically first 20-30 lines)
LICENSE_HEADER_PATTERN = re.compile(
    r'^(#[^\n]*\n)*'  # Comment lines at start
    r'.*?'
    r'(Common Public Attribution License|http://code\.tippr\.com/LICENSE)'
    r'.*?'
    r'(All Rights Reserved\.?|EXHIBIT [AB])',
    re.MULTILINE | re.DOTALL
)


def find_license_header_end(content: str) -> int:
    """
    Find where the license header ends in a file.
    Returns the character position after the license header, or 0 if no header found.
    """
    lines = content.split('\n')

    # Look for license markers in the first 50 lines
    in_license = False
    license_end_line = 0

    for i, line in enumerate(lines[:50]):
        # Check if this line contains license markers
        if any(marker in line for marker in LICENSE_MARKERS):
            in_license = True
            license_end_line = i
        elif in_license:
            # Check if we've exited the license block
            # License usually ends with a blank line or non-comment code
            if line.strip() == '' or (not line.startswith('#') and not line.startswith('//')):
                # Found end of license header
                license_end_line = i
                break
            license_end_line = i

    if not in_license:
        return 0

    # Return character position
    return sum(len(line) + 1 for line in lines[:license_end_line + 1])


# =============================================================================
# REPLACEMENT PATTERNS
# =============================================================================

@dataclass
class ReplacementRule:
    """A single replacement rule with pattern and replacement."""
    pattern: re.Pattern
    replacement: str
    description: str
    # If True, only apply outside license headers
    skip_in_license: bool = True


# Core branding replacements
CONTENT_REPLACEMENTS: List[ReplacementRule] = [
    # === URLS ===
    ReplacementRule(
        re.compile(r'https?://(?:www\.)?tippr\.com(?!/r/redditdev)'),
        'https://www.tippr.net',
        'Main site URL',
    ),
    ReplacementRule(
        re.compile(r'https?://about\.tippr\.com'),
        'https://about.tippr.net',
        'About page URL',
    ),
    ReplacementRule(
        re.compile(r'https?://m\.tippr\.com'),
        'https://m.tippr.net',
        'Mobile site URL',
    ),
    ReplacementRule(
        re.compile(r'https?://oauth\.tippr\.com'),
        'https://oauth.tippr.net',
        'OAuth URL',
    ),
    ReplacementRule(
        re.compile(r'https?://api\.tippr\.com'),
        'https://api.tippr.net',
        'API URL',
    ),
    ReplacementRule(
        re.compile(r'https?://i\.tippr\.com'),
        'https://i.tippr.net',
        'Image URL',
    ),

    # === CLASS NAMES ===
    ReplacementRule(
        re.compile(r'\bRedditApp\b'),
        'TipprApp',
        'TipprApp class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditController\b'),
        'TipprController',
        'TipprController class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditError\b'),
        'TipprError',
        'TipprError class/template',
    ),
    ReplacementRule(
        re.compile(r'\bRedditFooter\b'),
        'TipprFooter',
        'TipprFooter class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditInfoBar\b'),
        'TipprInfoBar',
        'TipprInfoBar class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditTraffic\b'),
        'TipprTraffic',
        'TipprTraffic class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditJsonTemplate\b'),
        'TipprJsonTemplate',
        'TipprJsonTemplate class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditGiftsController\b'),
        'TipprGiftsController',
        'TipprGiftsController class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditsController\b'),
        'VaultsController',
        'VaultsController class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditDetectorBase\b'),
        'TipprDetectorBase',
        'TipprDetectorBase class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditBrowser\b'),
        'TipprBrowser',
        'TipprBrowser class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditIsFunDetector\b'),
        'TipprIsFunDetector',
        'TipprIsFunDetector class',
    ),
    ReplacementRule(
        re.compile(r'\bRedditAndroidDetector\b'),
        'TipprAndroidDetector',
        'TipprAndroidDetector class',
    ),

    # === COOKIE NAMES ===
    ReplacementRule(
        re.compile(r'\breddit_session\b'),
        'tippr_session',
        'Session cookie name',
    ),
    ReplacementRule(
        re.compile(r'\breddit_admin\b'),
        'tippr_admin',
        'Admin cookie name',
    ),
    ReplacementRule(
        re.compile(r'\breddit_otp\b'),
        'tippr_otp',
        'OTP cookie name',
    ),
    ReplacementRule(
        re.compile(r'\breddit_mobility\b'),
        'tippr_mobility',
        'Mobility cookie name',
    ),
    ReplacementRule(
        re.compile(r'\breddit_first\b'),
        'tippr_first',
        'First visit cookie name',
    ),

    # === ENVIRONMENT VARIABLES ===
    ReplacementRule(
        re.compile(r'\bREDDIT_NAME\b'),
        'TIPPR_NAME',
        'TIPPR_NAME env var',
    ),
    ReplacementRule(
        re.compile(r'\bREDDIT_TAKEDOWN\b'),
        'TIPPR_TAKEDOWN',
        'TIPPR_TAKEDOWN env var',
    ),
    ReplacementRule(
        re.compile(r'\bREDDIT_ERROR_NAME\b'),
        'TIPPR_ERROR_NAME',
        'TIPPR_ERROR_NAME env var',
    ),
    ReplacementRule(
        re.compile(r'\bREDDIT_INI\b'),
        'TIPPR_INI',
        'TIPPR_INI env var',
    ),

    # === VARIABLE/ATTRIBUTE NAMES ===
    ReplacementRule(
        re.compile(r'\breddit_host\b'),
        'tippr_host',
        'tippr_host variable',
    ),
    ReplacementRule(
        re.compile(r'\breddit_pid\b'),
        'tippr_pid',
        'tippr_pid variable',
    ),
    ReplacementRule(
        re.compile(r'\breddit-domain-extension\b'),
        'tippr-domain-extension',
        'tippr-domain-extension key',
    ),
    ReplacementRule(
        re.compile(r'\breddit-prefer-lang\b'),
        'tippr-prefer-lang',
        'tippr-prefer-lang key',
    ),
    ReplacementRule(
        re.compile(r'\breddit-domain-prefix\b'),
        'tippr-domain-prefix',
        'tippr-domain-prefix key',
    ),
    ReplacementRule(
        re.compile(r'\b_reddit_controllers\b'),
        '_tippr_controllers',
        '_tippr_controllers variable',
    ),

    # === CONFIG VALUES ===
    ReplacementRule(
        re.compile(r'\bautomatic_reddits\b'),
        'automatic_vaults',
        'automatic_vaults config',
    ),
    ReplacementRule(
        re.compile(r'\blounge_reddit\b'),
        'lounge_vault',
        'lounge_vault config',
    ),
    ReplacementRule(
        re.compile(r'\bredditgifts_webhook\b'),
        'tipprgifts_webhook',
        'tipprgifts_webhook config',
    ),
    ReplacementRule(
        re.compile(r'\bredditbot\b'),
        'tipprbot',
        'User agent bot name',
    ),
    ReplacementRule(
        re.compile(r'\bformatter_reddit\b'),
        'formatter_tippr',
        'Formatter name',
    ),
    ReplacementRule(
        re.compile(r'\[formatter_tippr\]'),
        '[formatter_tippr]',
        'Formatter section',
    ),

    # === DATABASE/KEYSPACE ===
    ReplacementRule(
        re.compile(r'keyspace\s*=\s*["\']tippr["\']'),
        'keyspace = "tippr"',
        'Cassandra keyspace',
    ),
    ReplacementRule(
        re.compile(r'pool\s*=\s*["\']reddit-app["\']'),
        'pool = "tippr-app"',
        'Connection pool name',
    ),

    # === VAULT -> VAULT/SUBTIPPR (configurable) ===
    # These are case-sensitive to handle different contexts
    ReplacementRule(
        re.compile(r'\bSubreddit\b'),
        SR_SINGULAR_CAP,
        f'Vault -> {SR_SINGULAR_CAP}',
    ),
    ReplacementRule(
        re.compile(r'\bsubreddit\b'),
        SR_SINGULAR,
        f'vault -> {SR_SINGULAR}',
    ),
    ReplacementRule(
        re.compile(r'\bSUBREDDIT\b'),
        SR_SINGULAR.upper(),
        f'VAULT -> {SR_SINGULAR.upper()}',
    ),
    ReplacementRule(
        re.compile(r'\bsubreddits\b'),
        SR_PLURAL,
        f'vaults -> {SR_PLURAL}',
    ),
    ReplacementRule(
        re.compile(r'\bSubreddits\b'),
        SR_PLURAL_CAP,
        f'Vaults -> {SR_PLURAL_CAP}',
    ),
    ReplacementRule(
        re.compile(r'\bSUBREDDITS\b'),
        SR_PLURAL.upper(),
        f'VAULTS -> {SR_PLURAL.upper()}',
    ),
    # URL path /r/ -> /v/ or /s/ (configurable)
    ReplacementRule(
        re.compile(r"(['\"])/r/"),
        f"\\1{SR_URL_PREFIX}",
        f'/v/ URL prefix -> {SR_URL_PREFIX}',
    ),
    # Multivault handling
    ReplacementRule(
        re.compile(r'\bmultireddit\b'),
        MULTIREDDIT_REPLACEMENT if MULTIREDDIT_REPLACEMENT else 'multivault',
        f'multivault -> {MULTIREDDIT_REPLACEMENT or "(unchanged)"}',
    ),
    ReplacementRule(
        re.compile(r'\bMultireddit\b'),
        (MULTIREDDIT_REPLACEMENT or 'multivault').title(),
        f'Multivault -> {(MULTIREDDIT_REPLACEMENT or "multivault").title()}',
    ),

    # === GENERIC TIPPR REFERENCES (apply last, most general) ===
    # These should NOT be applied in license headers
    ReplacementRule(
        re.compile(r"logging\.getLogger\(['\"]tippr['\"]\)"),
        "logging.getLogger('tippr')",
        'Logger name',
    ),
    ReplacementRule(
        re.compile(r'\breddit\.com\b(?!/LICENSE)'),
        'tippr.net',
        'Domain references',
    ),

    # Generic word boundaries - be careful with these
    ReplacementRule(
        re.compile(r'(?<![/\w])tippr(?![/\w\-])(?!\.com/LICENSE)'),
        'tippr',
        'Generic tippr word',
    ),
    ReplacementRule(
        re.compile(r'(?<![/\w])Tippr(?![/\w\-])'),
        'Tippr',
        'Generic Tippr word capitalized',
    ),
    ReplacementRule(
        re.compile(r'(?<![/\w])TIPPR(?![/\w\-])'),
        'TIPPR',
        'Generic TIPPR word uppercase',
    ),
]


# =============================================================================
# FILE RENAMING PATTERNS
# =============================================================================

FILE_RENAME_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'tippr', re.IGNORECASE), 'tippr'),
    (re.compile(r'vault', re.IGNORECASE), SR_SINGULAR),
    (re.compile(r'multivault', re.IGNORECASE), MULTIREDDIT_REPLACEMENT or 'multivault'),
]


# =============================================================================
# PROCESSING FUNCTIONS
# =============================================================================

@dataclass
class ChangeStats:
    """Track statistics about changes made."""
    files_processed: int = 0
    files_modified: int = 0
    files_skipped: int = 0
    files_renamed: int = 0
    dirs_renamed: int = 0
    total_replacements: int = 0
    replacement_counts: dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    renamed_items: List[Tuple[str, str]] = field(default_factory=list)


def is_binary(path: Path) -> bool:
    """Check if a file is binary."""
    try:
        with open(path, 'rb') as f:
            chunk = f.read(8192)
            if b'\0' in chunk:
                return True
            # Check for high ratio of non-text bytes
            non_text = sum(1 for b in chunk if b < 32 and b not in (9, 10, 13))
            if len(chunk) > 0 and non_text / len(chunk) > 0.3:
                return True
    except Exception:
        return True
    return False


def should_skip_path(path: Path) -> bool:
    """Check if a path should be skipped entirely."""
    # Skip excluded paths
    for exclude in EXCLUDE_PATHS:
        try:
            path.relative_to(exclude)
            return True
        except ValueError:
            pass

    # Skip .git directory
    if '.git' in path.parts:
        return True

    # Skip node_modules, __pycache__, etc.
    skip_dirs = {'node_modules', '__pycache__', '.tox', '.pytest_cache', 'venv', '.venv', 'dist', 'build', '*.egg-info'}
    if any(part in skip_dirs or part.endswith('.egg-info') for part in path.parts):
        return True

    return False


def process_file_content(path: Path, dry_run: bool, verbose: bool, stats: ChangeStats) -> None:
    """Process a single file's content for replacements."""
    if should_skip_path(path):
        stats.files_skipped += 1
        return

    if path.suffix.lower() not in TEXT_EXTENSIONS and path.suffix != '':
        stats.files_skipped += 1
        return

    if is_binary(path):
        stats.files_skipped += 1
        return

    try:
        content = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding='latin-1')
        except Exception as e:
            stats.errors.append(f"Could not read {path}: {e}")
            return
    except Exception as e:
        stats.errors.append(f"Could not read {path}: {e}")
        return

    stats.files_processed += 1

    # Find where the license header ends
    license_end = find_license_header_end(content)

    # Split content into license header and rest
    license_header = content[:license_end] if license_end > 0 else ""
    rest_of_file = content[license_end:]

    # Apply replacements only to non-license content
    modified_rest = rest_of_file
    file_changes = 0

    for rule in CONTENT_REPLACEMENTS:
        if rule.skip_in_license or license_end == 0:
            # Apply to rest of file only
            new_rest, count = rule.pattern.subn(rule.replacement, modified_rest)
            if count > 0:
                modified_rest = new_rest
                file_changes += count
                stats.total_replacements += count
                stats.replacement_counts[rule.description] = stats.replacement_counts.get(rule.description, 0) + count
                if verbose:
                    print(f"  [{rule.description}] {count} replacement(s)")

    # Reconstruct the file
    new_content = license_header + modified_rest

    if new_content != content:
        stats.files_modified += 1
        stats.modified_files.append(str(path.relative_to(ROOT)))

        if not dry_run:
            try:
                path.write_text(new_content, encoding='utf-8')
            except Exception as e:
                stats.errors.append(f"Could not write {path}: {e}")


def rename_files_and_dirs(dry_run: bool, verbose: bool, stats: ChangeStats) -> None:
    """Rename files and directories containing 'tippr' or 'vault'."""
    # Collect all items to rename (process bottom-up)
    items_to_rename: List[Tuple[Path, Path]] = []

    for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
        dirp = Path(dirpath)

        if should_skip_path(dirp):
            continue

        # Check files
        for name in filenames:
            src = dirp / name
            if should_skip_path(src):
                continue

            new_name = name
            for pattern, repl in FILE_RENAME_PATTERNS:
                new_name = pattern.sub(repl, new_name)

            if new_name != name:
                items_to_rename.append((src, dirp / new_name))

        # Check directories
        for name in dirnames:
            src = dirp / name
            if should_skip_path(src):
                continue

            new_name = name
            for pattern, repl in FILE_RENAME_PATTERNS:
                new_name = pattern.sub(repl, new_name)

            if new_name != name:
                items_to_rename.append((src, dirp / new_name))

    # Perform renames
    for src, dst in items_to_rename:
        if dst.exists():
            stats.errors.append(f"Cannot rename {src} -> {dst}: target exists")
            continue

        if verbose:
            print(f"  Rename: {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

        if src.is_file():
            stats.files_renamed += 1
        else:
            stats.dirs_renamed += 1

        stats.renamed_items.append((str(src.relative_to(ROOT)), str(dst.relative_to(ROOT))))

        if not dry_run:
            try:
                src.rename(dst)
            except Exception as e:
                stats.errors.append(f"Failed to rename {src}: {e}")


def update_imports_after_rename(dry_run: bool, verbose: bool, stats: ChangeStats) -> None:
    """Update Python imports after file renames."""
    # This would need to update imports like:
    # from r2.lib.reddit_base import -> from r2.lib.tippr_base import
    # This is complex and might need manual review
    pass


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Rebrand tippr codebase to tippr',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python rebrand_to_tippr.py --dry-run     # Preview all changes
    python rebrand_to_tippr.py --verbose     # Apply with detailed output
    python rebrand_to_tippr.py               # Apply changes quietly

Note: This script preserves license headers as required by the CPAL license.
        """
    )
    parser.add_argument('--dry-run', '-n', action='store_true',
                       help='Preview changes without modifying files')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed output')
    parser.add_argument('--content-only', action='store_true',
                       help='Only update file contents, do not rename files')
    parser.add_argument('--rename-only', action='store_true',
                       help='Only rename files, do not update contents')

    args = parser.parse_args()

    print("=" * 70)
    print("Tippr -> Tippr Rebranding Script")
    print("=" * 70)
    print(f"Root directory: {ROOT}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    if args.dry_run:
        print("*** DRY RUN - No files will be modified ***")
        print()

    stats = ChangeStats()

    # Phase 1: Update file contents
    if not args.rename_only:
        print("Phase 1: Updating file contents...")
        print("-" * 40)

        for path in ROOT.rglob('*'):
            if path.is_file():
                if args.verbose:
                    print(f"Processing: {path.relative_to(ROOT)}")
                process_file_content(path, args.dry_run, args.verbose, stats)

        print()

    # Phase 2: Rename files and directories
    if not args.content_only:
        print("Phase 2: Renaming files and directories...")
        print("-" * 40)
        rename_files_and_dirs(args.dry_run, args.verbose, stats)
        print()

    # Print summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files processed:     {stats.files_processed}")
    print(f"Files modified:      {stats.files_modified}")
    print(f"Files skipped:       {stats.files_skipped}")
    print(f"Files renamed:       {stats.files_renamed}")
    print(f"Directories renamed: {stats.dirs_renamed}")
    print(f"Total replacements:  {stats.total_replacements}")
    print()

    if stats.replacement_counts:
        print("Replacements by type:")
        for desc, count in sorted(stats.replacement_counts.items(), key=lambda x: -x[1]):
            print(f"  {desc}: {count}")
        print()

    if stats.modified_files and args.verbose:
        print("Modified files:")
        for f in stats.modified_files[:50]:
            print(f"  {f}")
        if len(stats.modified_files) > 50:
            print(f"  ... and {len(stats.modified_files) - 50} more")
        print()

    if stats.renamed_items and args.verbose:
        print("Renamed items:")
        for src, dst in stats.renamed_items[:30]:
            print(f"  {src} -> {dst}")
        if len(stats.renamed_items) > 30:
            print(f"  ... and {len(stats.renamed_items) - 30} more")
        print()

    if stats.errors:
        print("ERRORS:")
        for err in stats.errors:
            print(f"  {err}")
        print()

    if args.dry_run:
        print("*** This was a DRY RUN - no files were modified ***")
        print("Run without --dry-run to apply changes.")
    else:
        print("Changes applied successfully!")
        print()
        print("Next steps:")
        print("  1. Review the changes: git diff")
        print("  2. Run tests to verify nothing broke")
        print("  3. Commit the changes: git add -A && git commit -m 'Rebrand tippr to tippr'")


if __name__ == '__main__':
    main()
