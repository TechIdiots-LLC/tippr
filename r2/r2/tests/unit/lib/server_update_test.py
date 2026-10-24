#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

import hashlib
import importlib.util
import io
import json
import os
import shutil
import tarfile
import tempfile
import time
from unittest.mock import MagicMock, patch

import r2
from r2.lib import server_update
from r2.tests import TipprTestCase

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(r2.__file__)))), "scripts", "tippr_update.py")


def load_updater():
    spec = importlib.util.spec_from_file_location("tippr_update", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeZk:
    """Enough of a KazooClient for r2.lib.server_update."""

    def __init__(self):
        self.nodes = {}

    def make_acl(self, **kw):
        return "acl"

    def ensure_path(self, path, acl=None):
        self.nodes.setdefault(path, b"")

    def exists(self, path):
        return path in self.nodes

    def create(self, path, data, acl=None):
        self.nodes[path] = data

    def set(self, path, data):
        self.nodes[path] = data

    def delete(self, path):
        del self.nodes[path]

    def get(self, path):
        return self.nodes[path], None

    def get_children(self, path):
        prefix = path + "/"
        return [p[len(prefix):] for p in self.nodes
                if p.startswith(prefix) and "/" not in p[len(prefix):]]


class TestRequests(TipprTestCase):
    def test_paths_match_the_updater(self):
        updater = load_updater()
        self.assertEqual(updater.REQUEST_PATH, server_update.REQUEST_PATH)
        self.assertEqual(updater.STATUS_PATH, server_update.STATUS_PATH)
        self.assertEqual(updater.ACTIVE_STATES, server_update.ACTIVE_STATES)

    def test_ask_and_cancel(self):
        zk = FakeZk()
        server_update.ask(zk, "0.15.0", "admin", backup=False)
        first = server_update.request(zk)
        self.assertEqual((first["version"], first["requested_by"],
                          first["backup"]), ("0.15.0", "admin", False))
        server_update.ask(zk, "0.15.1", "admin")
        second = server_update.request(zk)
        self.assertEqual(second["version"], "0.15.1")
        self.assertNotEqual(first["id"], second["id"])
        server_update.cancel(zk)
        self.assertIsNone(server_update.request(zk))

    def test_in_progress(self):
        zk = FakeZk()
        self.assertFalse(server_update.in_progress(zk))
        zk.create(server_update.STATUS_PATH + "/a", json.dumps(
            dict(state="installing", updated=time.time())).encode())
        self.assertTrue(server_update.in_progress(zk))
        zk.set(server_update.STATUS_PATH + "/a", json.dumps(
            dict(state="installing", updated=time.time() - 5 * 3600)).encode())
        self.assertFalse(server_update.in_progress(zk))
        zk.set(server_update.STATUS_PATH + "/a", json.dumps(
            dict(state="done", updated=time.time())).encode())
        self.assertFalse(server_update.in_progress(zk))


class TestUpdater(TipprTestCase):
    def setUp(self):
        self.updater = load_updater()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.updater.LOG = os.path.join(self.dir, "update.log")
        self.updater.WORK = os.path.join(self.dir, "work")

    def test_conf_must_be_roots_alone(self):
        path = os.path.join(self.dir, "updates.conf")
        with open(path, "w") as f:
            f.write("# comment\nTIPPR_WEB_UPDATES=1\nTIPPR_RELEASE_REPO=a/b\n")
        os.chmod(path, 0o644)
        with patch.object(self.updater.os, "stat", lambda p: MagicMock(
                st_uid=0, st_mode=0o100644)):
            conf = self.updater.read_conf(path)
        self.assertEqual(conf, {"TIPPR_WEB_UPDATES": "1",
                                "TIPPR_RELEASE_REPO": "a/b"})
        for uid, mode in ((1000, 0o100644), (0, 0o100666), (0, 0o100664)):
            with patch.object(self.updater.os, "stat", lambda p: MagicMock(
                    st_uid=uid, st_mode=mode)):
                self.assertIsNone(self.updater.read_conf(path))

    def test_how_a_server_is_checked_after_installing(self):
        # pages (one server, a frontend), or a backend's app and database
        # (it serves none; docs/SERVERS.md)
        with patch.object(self.updater, "site_answers", lambda d: "site") as _, \
                patch.object(self.updater, "backend_answers", lambda: "backend"):
            self.assertEqual(self.updater.came_back({}, "x.example"), "site")
            self.assertEqual(self.updater.came_back(
                {"TIPPR_ROLE": "frontend"}, "x.example"), "site")
            self.assertEqual(self.updater.came_back(
                {"TIPPR_ROLE": "backend"}, "x.example"), "backend")

    def _release(self, tarball_bytes, sums):
        def download(url, dest):
            with open(dest, "wb") as f:
                f.write(sums if url.endswith("SHA256SUMS") else tarball_bytes)
        return download

    def test_checksum_must_match(self):
        data = b"tarball"
        good = ("%s  tippr-1.0.0-installer.tar.gz\n"
                % hashlib.sha256(data).hexdigest()).encode()
        with patch.object(self.updater, "download", self._release(data, good)):
            self.assertTrue(self.updater.fetch_release("a/b", "1.0.0")
                            .endswith("tippr-1.0.0-installer.tar.gz"))
        bad = ("%s  tippr-1.0.0-installer.tar.gz\n" % ("0" * 64)).encode()
        with patch.object(self.updater, "download", self._release(data, bad)):
            with self.assertRaises(self.updater.UpdateError):
                self.updater.fetch_release("a/b", "1.0.0")
        unlisted = b"abc  something-else.tar.gz\n"
        with patch.object(self.updater, "download",
                          self._release(data, unlisted)):
            with self.assertRaises(self.updater.UpdateError):
                self.updater.fetch_release("a/b", "1.0.0")

    def _tarball(self, names):
        path = os.path.join(self.dir, "t.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            for name in names:
                info = tarfile.TarInfo(name)
                info.size = 2
                tar.addfile(info, io.BytesIO(b"hi"))
        return path

    def test_unpack(self):
        dest = os.path.join(self.dir, "src.new")
        self.updater.unpack(self._tarball(["tippr/install-tippr.sh",
                                           "i18n/README"]), dest)
        self.assertTrue(os.path.exists(os.path.join(dest, "tippr",
                                                    "install-tippr.sh")))
        with self.assertRaises(Exception):
            self.updater.unpack(self._tarball(["tippr/install-tippr.sh",
                                               "../escape"]), dest)
        with self.assertRaises(self.updater.UpdateError):
            self.updater.unpack(self._tarball(["something/else"]), dest)


class TestHandle(TipprTestCase):
    """What tippr-update decides to do with a request."""

    def setUp(self):
        self.updater = load_updater()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.updater.LOG = os.path.join(self.dir, "update.log")
        self.src = os.path.join(self.dir, "src")
        os.makedirs(os.path.join(self.src, "tippr"))
        with open(os.path.join(self.src, "tippr", "VERSION"), "w") as f:
            f.write("0.14.0\n")
        self.firstboot = os.path.join(self.dir, "tippr-firstboot")
        open(self.firstboot, "w").close()
        self.updater.FIRSTBOOT = self.firstboot
        self.nodes = {}
        self.claimed = True
        updater = self.updater
        test = self

        class Zk:
            def __init__(self, ini):
                pass

            def get(self, path):
                return test.nodes.get(path)

            def put(self, path, value, zk=None, attempts=12):
                test.nodes[path] = json.loads(json.dumps(value))
                return True

            def claim(self, me, status):
                if test.claimed:
                    status.set("downloading")
                return test.claimed

        self.updated = []
        for name, value in (
                ("Zk", Zk),
                ("read_ini", lambda path: {"domain": "example.com"}),
                ("server_id", lambda: "me"),
                ("update", lambda conf, ini, status, request:
                    self.updated.append(request["version"]))):
            p = patch.object(updater, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.conf = dict(TIPPR_WEB_UPDATES="1", TIPPR_SRC=self.src,
                         TIPPR_RELEASE_REPO="a/b")

    def ask(self, version="0.15.0", rid="r1"):
        self.nodes[self.updater.REQUEST_PATH] = dict(id=rid, version=version)

    def mine(self):
        return self.nodes.get(self.updater.STATUS_PATH + "/me") or {}

    def test_nothing_asked(self):
        self.updater.handle(self.conf)
        self.assertEqual((self.updated, self.mine()), ([], {}))

    def test_updates_once(self):
        self.ask()
        self.updater.handle(self.conf)
        self.assertEqual(self.updated, ["0.15.0"])
        self.assertEqual(self.mine()["from_version"], "0.14.0")
        # the same request again: already done (or doing)
        self.updater.handle(self.conf)
        self.assertEqual(self.updated, ["0.15.0"])

    def test_off_unsupported_and_bad_versions(self):
        self.ask()
        self.updater.handle(dict(self.conf, TIPPR_WEB_UPDATES="0"))
        self.assertEqual(self.mine()["state"], "disabled")
        self.ask(rid="r2")
        os.remove(self.firstboot)
        self.updater.handle(self.conf)
        self.assertEqual(self.mine()["state"], "unsupported")
        open(self.firstboot, "w").close()
        self.ask(version="1.0; rm -rf /", rid="r3")
        self.updater.handle(self.conf)
        self.assertEqual(self.mine()["state"], "failed")
        self.assertEqual(self.updated, [])

    def test_already_on_it(self):
        self.ask(version="0.14.0")
        self.updater.handle(self.conf)
        self.assertEqual(self.mine()["state"], "done")
        self.assertEqual(self.updated, [])

    def test_waits_for_another_server(self):
        self.ask()
        self.claimed = False
        self.updater.handle(self.conf)
        self.assertEqual(self.mine()["state"], "waiting")
        self.assertEqual(self.updated, [])
        # its turn comes
        self.claimed = True
        self.updater.handle(self.conf)
        self.assertEqual(self.updated, ["0.15.0"])

    def test_an_updater_that_died_is_reported(self):
        self.ask()
        self.nodes[self.updater.STATUS_PATH + "/me"] = dict(
            request_id="r1", state="installing", updated=time.time() - 4 * 3600)
        self.updater.handle(self.conf)
        self.assertEqual(self.mine()["state"], "failed")
        self.assertEqual(self.updated, [])


class TestProgress(TipprTestCase):
    """While the backup or the installer runs, the page's report keeps up."""

    def setUp(self):
        self.updater = load_updater()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.updater.LOG = os.path.join(self.dir, "update.log")
        self.updater.PROGRESS_SECONDS = 0.2
        self.puts = []
        test = self

        class Zk:
            def put(self, path, value, zk=None, attempts=12):
                test.puts.append((json.loads(json.dumps(value)), attempts))
                return True

        self.status = self.updater.Status(Zk(), "me", dict(id="r1", version="0.15.0"),
                                          "0.14.0")

    def test_run_reports_while_it_runs(self):
        calls = []
        code = self.updater.run(["sh", "-c", "echo working; sleep 1"],
                                progress=lambda: calls.append(1))
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(calls), 2)
        with open(self.updater.LOG) as f:
            self.assertIn("working", f.read())

    def test_run_times_out(self):
        start = time.time()
        self.assertEqual(self.updater.run(["sleep", "10"], timeout=0.5), -1)
        self.assertLess(time.time() - start, 5)

    def test_a_progress_error_doesnt_stop_it(self):
        def broken():
            raise RuntimeError("ZooKeeper is restarting")
        self.assertEqual(self.updater.run(["sleep", "0.5"], progress=broken), 0)

    def test_progress_keeps_the_step_and_tries_once(self):
        self.status.set("installing", "the site is down")
        started = self.puts[-1][0]["step_started"]
        self.updater.log("pip install ...")
        self.status.progress()
        record, attempts = self.puts[-1]
        self.assertEqual(attempts, 1)
        self.assertEqual(record["state"], "installing")
        self.assertEqual(record["step_started"], started)
        self.assertIn("pip install", record["log"][-1])

    def test_a_new_step_starts_its_clock(self):
        self.status.set("backing_up")
        self.status.record["step_started"] -= 100
        self.status.set("backing_up")
        self.assertLess(self.puts[-1][0]["step_started"], time.time() - 50)
        self.status.set("installing")
        self.assertGreaterEqual(self.puts[-1][0]["step_started"], int(time.time()) - 1)
