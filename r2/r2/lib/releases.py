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
"""tippr's published releases, for /admin/servers: which is newest, and
whether a server runs an older one.

Releases are read from GitHub's API for release_repo (in the ini; the
project's own by default) and kept for an hour, as GitHub allows 60 asks an
hour without a key. Only releases with an installer tarball and its
checksums count: those are what an update installs (docs/RELEASING.md).
"""

import re

import requests
from pylons import app_globals as g

DEFAULT_REPO = "TechIdiots-LLC/tippr"
CACHE_KEY = "tippr_releases"
CACHE_SECONDS = 3600
# a failed ask isn't repeated for this long
ERROR_CACHE_SECONDS = 600
TIMEOUT = 10

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")


def version_key(version):
    """A sortable key for "1.2.3" or "1.2.3-rc1" (a pre-release comes
    before its release); None if it isn't one."""
    m = VERSION_RE.match((version or "").strip().lstrip("v"))
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    pre_key = ()
    if pre:
        pre_key = tuple((0, int(part), "") if part.isdigit() else (1, 0, part)
                        for part in re.split(r"[.]|(?<=\D)(?=\d)", pre)
                        if part)
    return (int(major), int(minor), int(patch), 0 if pre else 1, pre_key)


def newer(a, b):
    """Whether version a is newer than version b (False if either isn't
    one)."""
    ka, kb = version_key(a), version_key(b)
    return bool(ka and kb and ka > kb)


def repo():
    value = (g.config.get("release_repo") or DEFAULT_REPO).strip()
    return value if re.match(r"^[\w.-]+/[\w.-]+$", value) else DEFAULT_REPO


def _installable(release):
    version = (release.get("tag_name") or "").lstrip("v")
    names = {a.get("name") for a in release.get("assets") or []}
    return (version_key(version) is not None and not release.get("draft") and
            "tippr-%s-installer.tar.gz" % version in names and
            "SHA256SUMS" in names)


def _fetch():
    response = requests.get(
        "https://api.github.com/repos/%s/releases" % repo(),
        params={"per_page": 30}, timeout=TIMEOUT,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "tippr-releases"})
    response.raise_for_status()
    found = []
    for release in response.json():
        if not _installable(release):
            continue
        found.append(dict(
            version=release["tag_name"].lstrip("v"),
            name=release.get("name") or release["tag_name"],
            url=release.get("html_url"),
            published=release.get("published_at"),
            prerelease=bool(release.get("prerelease")),
        ))
    found.sort(key=lambda r: version_key(r["version"]), reverse=True)
    return found


def releases(refresh=False):
    """{"releases": [...] newest first, "error": None or why GitHub couldn't
    be asked}."""
    cached = None if refresh else g.gencache.get(CACHE_KEY)
    if cached is not None:
        return cached
    try:
        cached = dict(releases=_fetch(), error=None)
        g.gencache.set(CACHE_KEY, cached, time=CACHE_SECONDS)
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        g.log.warning("releases: couldn't ask GitHub: %s", e)
        cached = dict(releases=[], error=str(e)[:200])
        g.gencache.set(CACHE_KEY, cached, time=ERROR_CACHE_SECONDS)
    return cached


def latest(prerelease=False):
    """The newest installable release (pre-releases only if asked), or
    None."""
    for release in releases()["releases"]:
        if prerelease or not release["prerelease"]:
            return release
    return None


def get(version):
    for release in releases()["releases"]:
        if release["version"] == version:
            return release
    return None
