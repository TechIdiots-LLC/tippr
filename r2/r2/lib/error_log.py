# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
#
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################
"""Recent unhandled errors, for /admin/errors.

Errors are grouped by exception and the line of tippr code that raised it,
with a count, when they were first and last seen, the last path and one
traceback. The groups are kept in the hardcache (PostgreSQL), so they
survive restarts, capped at MAX_GROUPS. The full tracebacks are also in
the service's journal (journalctl -u tippr-paster).
"""

import hashlib
import os
import time
import traceback

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

KEY = "errorlog-recent"
MAX_GROUPS = 100
MAX_TRACEBACK = 8000
KEEP_SECONDS = 30 * 86400


def _where(tb):
    """The innermost frame in tippr's own code, as "file:line in func"."""
    where = None
    for frame in traceback.extract_tb(tb):
        if "site-packages" not in frame.filename:
            where = "%s:%d in %s" % (
                os.path.relpath(frame.filename, g.paths["root"] + "/.."),
                frame.lineno, frame.name)
    return where or "?"


def record(exc):
    """Add an exception being handled to the log. Never raises."""
    try:
        summary = "".join(
            traceback.format_exception_only(type(exc), exc)).strip()
        where = _where(exc.__traceback__)
        key = hashlib.sha1(
            ("%s|%s" % (type(exc).__name__, where)).encode()).hexdigest()[:12]
        now = time.time()
        try:
            path = request.environ.get("FULLPATH", request.path)
            method = request.method
        except Exception:
            path, method = "?", "?"
        try:
            user = c.user.name if c.user_is_loggedin else None
        except Exception:
            user = None

        groups = g.hardcache.get(KEY) or {}
        entry = groups.get(key) or {"count": 0, "first": now}
        entry.update({
            "summary": summary[:500],
            "where": where,
            "path": "%s %s" % (method, path[:300]),
            "user": user,
            "last": now,
            "count": entry["count"] + 1,
            "traceback": "".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__))[-MAX_TRACEBACK:],
        })
        groups[key] = entry
        if len(groups) > MAX_GROUPS:
            newest = sorted(groups.items(), key=lambda kv: kv[1]["last"],
                            reverse=True)[:MAX_GROUPS]
            groups = dict(newest)
        g.hardcache.set(KEY, groups, KEEP_SECONDS)
    except Exception:
        g.log.exception("error_log: couldn't record an error")


def recent():
    """The error groups, most recently seen first."""
    groups = g.hardcache.get(KEY) or {}
    return sorted(({"id": k, **v} for k, v in groups.items()),
                  key=lambda e: e["last"], reverse=True)


def clear():
    g.hardcache.delete(KEY)
