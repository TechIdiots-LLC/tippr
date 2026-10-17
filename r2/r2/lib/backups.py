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
"""The web side of site backups (/admin/backups and the transfer API).

The backups themselves are made by scripts/tippr_backup.py, run as root by
tippr-backup.service. The web app can't do that work (pg_dump as root,
stopping services), so it queues requests: a JSON file in QUEUE_DIR, which
tippr-backup.path notices. Progress is read back from each backup's
manifest.json and from job.json in the backup folder.

Another tippr server can copy this server's backups with a transfer key
made here; only a hash of the key is kept (site settings group "backups",
which backups leave out).
"""

import datetime
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from pylons import app_globals as g

from r2.lib import site_settings

DEFAULT_BACKUP_DIR = "/var/lib/tippr/backups"
QUEUE_DIR = "/var/lib/tippr/backup-queue"
JOB_FILE = "job.json"
NAME_RE = re.compile(r"^tippr-backup-\d{8}-\d{6}$")
# must match scripts/tippr_backup.py
CHUNK_SIZE = 16 * 1024 * 1024
TRANSFER_KEY_DAYS = 7
SETTINGS_GROUP = "backups"


def backup_dir():
    return g.config.get("backup_dir") or DEFAULT_BACKUP_DIR


def service_installed():
    """Whether tippr-backup.path is set up to run requests (the installer
    makes the queue folder)."""
    return os.path.isdir(QUEUE_DIR) and os.access(QUEUE_DIR, os.W_OK)


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def list_backups():
    """The backups in backup_dir, newest first (each its manifest)."""
    root = backup_dir()
    try:
        names = sorted((n for n in os.listdir(root) if NAME_RE.match(n)),
                       reverse=True)
    except OSError:
        return []
    result = []
    for name in names:
        manifest = _read_json(os.path.join(root, name, "manifest.json"))
        result.append(manifest or {"name": name, "state": "unknown"})
    return result


def get_backup(name):
    if not NAME_RE.match(name or ""):
        return None
    return _read_json(os.path.join(backup_dir(), name, "manifest.json"))


def job_status():
    """The request being run, or the last one (job.json)."""
    return _read_json(os.path.join(backup_dir(), JOB_FILE))


def pending_requests():
    try:
        entries = sorted(e for e in os.listdir(QUEUE_DIR)
                         if e.endswith(".json"))
    except OSError:
        return []
    result = []
    for entry in entries:
        request = _read_json(os.path.join(QUEUE_DIR, entry))
        if request:
            request.pop("key", None)
            result.append(request)
    return result


def queue_request(action, requested_by, **fields):
    """Hand a request to tippr-backup.service."""
    request = dict(fields, action=action, requested_by=requested_by,
                   requested=datetime.datetime.utcnow().isoformat() + "Z")
    name = "%d-%s" % (time.time() * 1000, secrets.token_hex(4))
    tmp = os.path.join(QUEUE_DIR, name + ".tmp")
    # it may hold another server's transfer key: owner only
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(request, f)
    # the path unit watches *.json, so it only sees the finished file
    os.rename(tmp, os.path.join(QUEUE_DIR, name + ".json"))


###############################################################################
# Transfer keys
###############################################################################

def _hash_key(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def transfer_key_info():
    """The current key's details (never the key), or None."""
    info = site_settings.get_settings(SETTINGS_GROUP).get("transfer_key")
    if not info:
        return None
    info = dict(info)
    info["expired"] = info.get("expires", 0) < time.time()
    return info


def create_transfer_key(created_by):
    """Make a new key (replacing any old one) and return it; it can't be
    shown again."""
    key = "tpk_" + secrets.token_urlsafe(32)
    now = time.time()
    settings = site_settings.get_settings(SETTINGS_GROUP)
    settings["transfer_key"] = {
        "sha256": _hash_key(key),
        "created": now,
        "expires": now + TRANSFER_KEY_DAYS * 86400,
        "created_by": created_by,
    }
    site_settings.save_settings(SETTINGS_GROUP, settings)
    return key


def revoke_transfer_key():
    settings = site_settings.get_settings(SETTINGS_GROUP)
    settings.pop("transfer_key", None)
    site_settings.save_settings(SETTINGS_GROUP, settings)


def check_transfer_key(key):
    info = transfer_key_info()
    if not key or not info or info["expired"]:
        return False
    return hmac.compare_digest(_hash_key(key), info["sha256"])


###############################################################################
# Sending a backup to another server
###############################################################################

def read_chunk(name, path, offset):
    """Up to CHUNK_SIZE bytes of one file of a finished backup, or None if
    there's no such file."""
    manifest = get_backup(name)
    if not manifest or manifest.get("state") != "done":
        return None
    if path not in {f["path"] for f in manifest.get("files", ())}:
        return None
    full = os.path.join(backup_dir(), name, path)
    with open(full, "rb") as f:
        f.seek(max(0, offset))
        return f.read(CHUNK_SIZE)


def public_summary(manifest):
    """What another server sees in the backup list."""
    keys = ("name", "state", "step", "started", "finished", "offline",
            "size", "error", "source", "format")
    return {k: manifest.get(k) for k in keys}
