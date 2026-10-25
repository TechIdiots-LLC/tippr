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
"""The web side of site backups (/admin/backups and the transfer API).

The backups themselves are made by scripts/tippr_backup.py, run as root by
tippr-backup.service. The web app can't do that work (pg_dump as root,
stopping services), so it queues requests: a JSON file in QUEUE_DIR, which
tippr-backup.path notices. Progress is read back from each backup's
manifest.json and from job.json in the backup folder.

Another tippr server can copy this server's backups with a transfer key
made here; only a hash of the key is kept (site settings group "backups",
which backups leave out).

On a frontend (docs/SERVERS.md) the backups, and tippr-backup, are on the
backend: requests go to ZooKeeper (ZK_QUEUE) instead, and the list and
progress come from what the backend publishes there (ZK_STATE), both
through scripts/backup_relay.py on the backend. Another server can't copy
a split site's backups through a frontend (the files aren't there).
"""

import datetime
import hashlib
import hmac
import json
import os
import secrets
import time

from pylons import app_globals as g

from r2.lib import backup_files, site_settings
from r2.lib.backup_files import (
    DEFAULT_BACKUP_DIR,
    NAME_RE,
    QUEUE_DIR,
)

# must match scripts/tippr_backup.py
CHUNK_SIZE = 16 * 1024 * 1024
TRANSFER_KEY_DAYS = 7
SETTINGS_GROUP = "backups"

# a frontend's requests, and the backend's backups and progress
# (scripts/backup_relay.py), in ZooKeeper
ZK_QUEUE = "/tippr/backups/queue"
ZK_STATE = "/tippr/backups/state"
# the relay publishes every few seconds: older means it isn't running
STATE_FRESH_SECONDS = 600


def remote():
    """Whether the backups are on another server: this one is a frontend,
    and they're on its backend (docs/SERVERS.md)."""
    return g.config.get("server_role") == "frontend"


def _state():
    """What the backend last published, or {}."""
    try:
        data, _stat = g.zookeeper.get(ZK_STATE)
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


def backup_dir():
    if remote():
        return _state().get("backup_dir") or DEFAULT_BACKUP_DIR
    return g.config.get("backup_dir") or DEFAULT_BACKUP_DIR


def service_installed():
    """Whether tippr-backup.path is set up to run requests (the installer
    makes the queue folder), here or, from a frontend, on the backend."""
    if remote():
        return time.time() - _state().get("updated", 0) < STATE_FRESH_SECONDS
    return os.path.isdir(QUEUE_DIR) and os.access(QUEUE_DIR, os.W_OK)


def list_backups():
    """The backups in backup_dir, newest first (each its manifest)."""
    if remote():
        return _state().get("backups") or []
    return backup_files.backups(backup_dir())


def get_backup(name):
    if not NAME_RE.match(name or ""):
        return None
    if remote():
        return next((b for b in list_backups() if b.get("name") == name),
                    None)
    return backup_files.read_json(
        os.path.join(backup_dir(), name, "manifest.json"))


def job_status():
    """The request being run, or the last one (job.json)."""
    if remote():
        return _state().get("job")
    return backup_files.job(backup_dir())


def pending_requests():
    if not remote():
        return backup_files.pending()
    # the ones the backend has, and any it hasn't picked up yet
    result = list(_state().get("pending") or [])
    for request in _zk_queued():
        request.pop("key", None)
        result.append(request)
    return result


def _zk_queued():
    try:
        names = sorted(g.zookeeper.get_children(ZK_QUEUE))
    except Exception:
        return []
    found = []
    for name in names:
        try:
            data, _stat = g.zookeeper.get("%s/%s" % (ZK_QUEUE, name))
            found.append(json.loads(data.decode("utf-8")))
        except Exception:
            continue
    return found


def queue_request(action, requested_by, **fields):
    """Hand a request to tippr-backup.service (on a frontend, through
    ZooKeeper to the backend's)."""
    request = dict(fields, action=action, requested_by=requested_by,
                   requested=datetime.datetime.utcnow().isoformat() + "Z")
    name = "%d-%s" % (time.time() * 1000, secrets.token_hex(4))
    if remote():
        # (it may hold another server's transfer key: the app's nodes are
        # for its own ZooKeeper login only)
        zk = g.zookeeper
        acl = [zk.make_acl(read=True, write=True, create=True, delete=True)]
        zk.ensure_path(ZK_QUEUE, acl=acl)
        zk.create("%s/%s" % (ZK_QUEUE, name),
                  json.dumps(request).encode("utf-8"), acl=acl)
        return
    backup_files.write_request(QUEUE_DIR, name, request)


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
    there's no such file (or, on a frontend, the files aren't here)."""
    if remote():
        return None
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
