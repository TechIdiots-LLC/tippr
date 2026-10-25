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
"""The backup folder and request queue on this server's disk: what
r2.lib.backups reads for /admin/backups, and scripts/backup_relay.py for a
backend's frontends. Nothing but the standard library, so the relay can
load it without starting the app."""

import json
import os
import re

DEFAULT_BACKUP_DIR = "/var/lib/tippr/backups"
QUEUE_DIR = "/var/lib/tippr/backup-queue"
JOB_FILE = "job.json"
NAME_RE = re.compile(r"^tippr-backup-\d{8}-\d{6}$")


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def backups(root):
    """The backups in the folder root, newest first (each its manifest)."""
    try:
        names = sorted((n for n in os.listdir(root) if NAME_RE.match(n)),
                       reverse=True)
    except OSError:
        return []
    result = []
    for name in names:
        manifest = read_json(os.path.join(root, name, "manifest.json"))
        result.append(manifest or {"name": name, "state": "unknown"})
    return result


def job(root):
    """The request being run, or the last one (job.json)."""
    return read_json(os.path.join(root, JOB_FILE))


def pending(queue_dir=QUEUE_DIR):
    """The requests waiting in the queue (without transfer keys)."""
    try:
        entries = sorted(e for e in os.listdir(queue_dir)
                         if e.endswith(".json"))
    except OSError:
        return []
    result = []
    for entry in entries:
        request = read_json(os.path.join(queue_dir, entry))
        if request:
            request.pop("key", None)
            result.append(request)
    return result


def write_request(queue_dir, name, request):
    """Queue a request for tippr-backup.service (name.json in queue_dir)."""
    tmp = os.path.join(queue_dir, name + ".tmp")
    # it may hold another server's transfer key: owner only
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(request, f)
    # the path unit watches *.json, so it only sees the finished file
    os.rename(tmp, os.path.join(queue_dir, name + ".json"))
