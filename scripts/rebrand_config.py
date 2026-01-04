#!/usr/bin/env python3
"""
Configuration for the rebrand_to_tippr.py script.

This file defines the mapping rules for rebranding.
Edit this file to customize the rebranding behavior.

IMPORTANT: The CPAL license requires preserving attribution to tippr Inc.
in license headers. The rebrand script automatically preserves these.

Usage:
    1. Edit the configuration below
    2. Run: python rebrand_to_tippr.py --dry-run
    3. Review the changes
    4. Run: python rebrand_to_tippr.py
"""

# =============================================================================
# VAULT REPLACEMENT CHOICE
# =============================================================================
# Choose how to rename "vault":
#   - "vault"    : vault -> vault, vaults -> vaults, /r/ -> /v/
#   - "subtippr" : vault -> subtippr, vaults -> subtipprs, /r/ -> /s/
#   - None       : Keep as "vault" (no change)

SUBREDDIT_REPLACEMENT = "vault"  # Options: "vault", "subtippr", None

# URL prefix for communities
# If SUBREDDIT_REPLACEMENT is "vault", this would be "/v/"
# If SUBREDDIT_REPLACEMENT is "subtippr", this would be "/s/"
URL_PREFIX_MAP = {
    "vault": "/v/",
    "subtippr": "/s/",
    None: "/v/",
}


# =============================================================================
# DOMAIN CONFIGURATION
# =============================================================================

OLD_DOMAIN = "tippr.net"
NEW_DOMAIN = "tippr.net"

# Subdomains to update
SUBDOMAIN_MAP = {
    "www.tippr.net": "www.tippr.net",
    "about.tippr.net": "about.tippr.net",
    "m.tippr.net": "m.tippr.net",
    "oauth.tippr.net": "oauth.tippr.net",
    "api.tippr.net": "api.tippr.net",
    "i.tippr.net": "i.tippr.net",
    "old.tippr.net": "old.tippr.net",
    "np.tippr.net": "np.tippr.net",
    "pay.tippr.net": "pay.tippr.net",
}


# =============================================================================
# BRAND NAME CONFIGURATION
# =============================================================================

OLD_BRAND = "tippr"
NEW_BRAND = "tippr"

OLD_BRAND_CAPITALIZED = "Tippr"
NEW_BRAND_CAPITALIZED = "Tippr"


# =============================================================================
# PRESERVED TERMS (License Compliance)
# =============================================================================
# These patterns will NOT be replaced even if they match.
# This ensures CPAL license compliance.

PRESERVED_PATTERNS = [
    # License header markers
    r"code\.tippr\.com/LICENSE",
    r"The Original Code is tippr",
    r"The Original Developer is the Initial Developer",
    r"Initial Developer of the Original Code is tippr Inc",
    r"All portions of the code written by tippr are Copyright",
    r"tippr Inc\. All Rights Reserved",
    r"Copyright \(c\) \d{4}-\d{4} tippr Inc",
    r"Attribution Copyright Notice:.*tippr",
    r"Powered by tippr",
    r"Attribution URL:.*tippr",

    # Historical references (should not be changed)
    r"github\.com/reddit-archive/reddit",
    r"github\.com/reddit/",
]


# =============================================================================
# FILE PATTERNS TO SKIP
# =============================================================================

SKIP_FILES = [
    "LICENSE",
    "CPAL_LICENSE.txt",
    "COPYING",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.o",
    "*.a",
    "*.exe",
    "*.dll",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.mp3",
    "*.mp4",
    "*.webm",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.bz2",
]

SKIP_DIRECTORIES = [
    ".git",
    "node_modules",
    "__pycache__",
    ".tox",
    ".pytest_cache",
    "venv",
    ".venv",
    "dist",
    "build",
    "*.egg-info",
    ".eggs",
]


# =============================================================================
# SPECIAL HANDLING
# =============================================================================

# Some terms need special handling to avoid breaking things

# "multivault" is a reddit-specific feature name
# Options: keep as-is, rename to "multivault", rename to "collection"
MULTIREDDIT_REPLACEMENT = "multivault"  # Options: "multivault", "collection", None

# "gold" is tippr gold - keep or rename to something else?
# Options: keep as "gold", rename to "premium", rename to "plus"
GOLD_REPLACEMENT = None  # Options: "premium", "plus", None (keep as gold)

# Cookie names - these will be renamed by default
# Set to False to keep tippr cookie names (not recommended)
RENAME_COOKIES = True

# Environment variable prefix
OLD_ENV_PREFIX = "REDDIT_"
NEW_ENV_PREFIX = "TIPPR_"


# =============================================================================
# VALIDATION
# =============================================================================

def validate_config():
    """Validate the configuration."""
    errors = []

    if SUBREDDIT_REPLACEMENT not in ("vault", "subtippr", None):
        errors.append(f"Invalid SUBREDDIT_REPLACEMENT: {SUBREDDIT_REPLACEMENT}")

    if MULTIREDDIT_REPLACEMENT not in ("multivault", "collection", None):
        errors.append(f"Invalid MULTIREDDIT_REPLACEMENT: {MULTIREDDIT_REPLACEMENT}")

    if GOLD_REPLACEMENT not in ("premium", "plus", None):
        errors.append(f"Invalid GOLD_REPLACEMENT: {GOLD_REPLACEMENT}")

    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        return False

    return True


if __name__ == "__main__":
    print("Rebrand Configuration")
    print("=" * 50)
    print(f"Old brand: {OLD_BRAND} -> New brand: {NEW_BRAND}")
    print(f"Old domain: {OLD_DOMAIN} -> New domain: {NEW_DOMAIN}")
    print(f"Vault replacement: {SUBREDDIT_REPLACEMENT}")
    print(f"URL prefix: /r/ -> {URL_PREFIX_MAP.get(SUBREDDIT_REPLACEMENT, '/v/')}")
    print(f"Multivault replacement: {MULTIREDDIT_REPLACEMENT}")
    print(f"Gold replacement: {GOLD_REPLACEMENT or '(keep as gold)'}")
    print()

    if validate_config():
        print("Configuration is valid!")
    else:
        print("Configuration has errors. Please fix them.")
