#!/usr/bin/env python
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
"""/admin/backups for a backend's frontends (docs/SERVERS.md).

The backups and tippr-backup are on the backend; the page is on a
frontend. Every few seconds (tippr-backup-relay.timer, on the backend),
this moves the requests frontends left in ZooKeeper into the local queue
folder, where tippr-backup.path runs them, and publishes the backups, the
request being run and the ones waiting for the page (r2.lib.backups
ZK_QUEUE and ZK_STATE):

    python scripts/backup_relay.py [path/to/run.ini]

Like server_status.py it reads the ini only for ZooKeeper and backup_dir,
and doesn't load the app.
"""

import configparser
import importlib.util
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)

# the module on its own, not the r2 package (whose start-up the app needs)
_spec = importlib.util.spec_from_file_location(
    "backup_files", os.path.join(SRC, "r2", "r2", "lib", "backup_files.py"))
backup_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backup_files)

# the same as r2.lib.backups
ZK_QUEUE = "/tippr/backups/queue"
ZK_STATE = "/tippr/backups/state"
# ZooKeeper keeps a node under 1 MB: a manifest's file list is left out
# (the page doesn't show it), and the oldest backups if there are many
MAX_STATE_BYTES = 900 * 1024


def settings(ini):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(ini)
    return parser.defaults()


def summary(manifest):
    return {k: v for k, v in manifest.items() if k != "files"}


def relay(zk, acl, root, queue_dir):
    """Move the frontends' requests into queue_dir, then publish the state
    of root and queue_dir."""
    moved = 0
    if zk.exists(ZK_QUEUE):
        for name in sorted(zk.get_children(ZK_QUEUE)):
            path = "%s/%s" % (ZK_QUEUE, name)
            try:
                request = json.loads(zk.get(path)[0].decode("utf-8"))
            except Exception:
                zk.delete(path)
                continue
            if os.path.exists(os.path.join(queue_dir, name + ".json")):
                zk.delete(path)
                continue
            backup_files.write_request(queue_dir, name, request)
            zk.delete(path)
            moved += 1
    backups = [summary(m) for m in backup_files.backups(root)]
    state = dict(updated=int(time.time()), host=socket.gethostname(),
                 backup_dir=root, backups=backups,
                 job=backup_files.job(root),
                 pending=backup_files.pending(queue_dir))
    data = json.dumps(state).encode("utf-8")
    while len(data) > MAX_STATE_BYTES and state["backups"]:
        state["backups"].pop()
        data = json.dumps(state).encode("utf-8")
    if zk.exists(ZK_STATE):
        zk.set(ZK_STATE, data)
    else:
        zk.create(ZK_STATE, data, acl=acl, makepath=True)
    return moved


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ini = args[0] if args else os.environ.get(
        "TIPPR_INI", os.path.join(SRC, "r2", "run.ini"))
    config = settings(ini)
    root = config.get("backup_dir") or backup_files.DEFAULT_BACKUP_DIR

    from kazoo.client import KazooClient
    from kazoo.security import make_digest_acl
    user = config.get("zookeeper_username", "")
    password = config.get("zookeeper_password", "")
    zk = KazooClient(hosts=config.get("zookeeper_connection_string",
                                      "localhost:2181"),
                     timeout=10,
                     auth_data=[("digest", "%s:%s" % (user, password))]
                     if user else None)
    zk.start(timeout=15)
    try:
        # the same permissions as the app's nodes (r2.lib.zookeeper), so
        # it can read them
        acl = [make_digest_acl(user, password, all=True)] if user else None
        moved = relay(zk, acl, root, backup_files.QUEUE_DIR)
        if moved:
            print("backup relay: %d request(s) from the frontends" % moved)
    finally:
        zk.stop()
        zk.close()


if __name__ == "__main__":
    main()
