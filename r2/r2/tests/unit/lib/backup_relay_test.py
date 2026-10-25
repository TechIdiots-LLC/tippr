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
"""/admin/backups on a frontend: requests through ZooKeeper to the backend
(scripts/backup_relay.py), and its backups and progress back."""

import importlib.util
import json
import os
import shutil
import tempfile
import time
from unittest.mock import MagicMock, patch

import r2
from r2.lib import backups
from r2.tests import TipprTestCase

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(r2.__file__)))), "scripts", "backup_relay.py")


def load_relay():
    spec = importlib.util.spec_from_file_location("backup_relay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeZk:
    """Enough of a KazooClient (and of r2's, for make_acl)."""

    def __init__(self):
        self.nodes = {}

    def make_acl(self, **kw):
        return "acl"

    def ensure_path(self, path, acl=None):
        self.nodes.setdefault(path, b"")

    def exists(self, path):
        return path in self.nodes

    def create(self, path, data, acl=None, makepath=False):
        self.nodes[path] = data

    def set(self, path, data):
        self.nodes[path] = data

    def get(self, path):
        if path not in self.nodes:
            raise KeyError(path)
        return self.nodes[path], None

    def delete(self, path):
        del self.nodes[path]

    def get_children(self, path):
        prefix = path + "/"
        return [p[len(prefix):] for p in self.nodes
                if p.startswith(prefix) and "/" not in p[len(prefix):]]


class TestBackupRelay(TipprTestCase):
    def setUp(self):
        self.relay = load_relay()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.root = os.path.join(self.dir, "backups")
        self.queue = os.path.join(self.dir, "queue")
        os.makedirs(self.queue)
        os.makedirs(os.path.join(self.root, "tippr-backup-20261024-120000"))
        with open(os.path.join(self.root, "tippr-backup-20261024-120000",
                               "manifest.json"), "w") as f:
            json.dump({"name": "tippr-backup-20261024-120000",
                       "state": "done", "files": [{"path": "db.sql"}]}, f)
        self.zk = FakeZk()
        fake_g = MagicMock(zookeeper=self.zk,
                           config={"server_role": "frontend"})
        p = patch("r2.lib.backups.g", fake_g)
        p.start()
        self.addCleanup(p.stop)

    def test_a_frontends_request_reaches_the_backend(self):
        backups.queue_request("export", "admin", offline=False)
        # waiting in ZooKeeper, shown on the page
        self.assertEqual([r["action"] for r in backups.pending_requests()],
                         ["export"])
        self.assertEqual(self.relay.relay(self.zk, None, self.root,
                                          self.queue), 1)
        # now a file tippr-backup.path runs, and gone from ZooKeeper
        files = os.listdir(self.queue)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith(".json"))
        self.assertEqual(oct(os.stat(os.path.join(self.queue, files[0]))
                             .st_mode & 0o777), "0o600")
        self.assertEqual(self.zk.get_children(backups.ZK_QUEUE), [])

    def test_the_page_sees_the_backends_backups(self):
        self.assertFalse(backups.service_installed())
        self.relay.relay(self.zk, None, self.root, self.queue)
        self.assertTrue(backups.service_installed())
        listed = backups.list_backups()
        self.assertEqual([b["name"] for b in listed],
                         ["tippr-backup-20261024-120000"])
        # without the file list (ZooKeeper nodes stay small)
        self.assertNotIn("files", listed[0])
        self.assertEqual(backups.backup_dir(), self.root)
        self.assertIsNotNone(backups.get_backup("tippr-backup-20261024-120000"))
        self.assertIsNone(backups.get_backup("tippr-backup-20261024-130000"))
        # the files aren't on a frontend
        self.assertIsNone(backups.read_chunk("tippr-backup-20261024-120000",
                                             "db.sql", 0))

    def test_an_old_state_means_the_relay_stopped(self):
        self.relay.relay(self.zk, None, self.root, self.queue)
        state = json.loads(self.zk.get(backups.ZK_STATE)[0])
        state["updated"] = time.time() - backups.STATE_FRESH_SECONDS - 1
        self.zk.set(backups.ZK_STATE, json.dumps(state).encode())
        self.assertFalse(backups.service_installed())

    def test_one_server_reads_its_own_disk(self):
        with patch("r2.lib.backups.g", MagicMock(
                config={"backup_dir": self.root})):
            self.assertFalse(backups.remote())
            self.assertEqual([b["name"] for b in backups.list_backups()],
                             ["tippr-backup-20261024-120000"])
