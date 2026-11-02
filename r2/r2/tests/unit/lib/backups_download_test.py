#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""Downloading a backup as one tar (r2.lib.backups.download)."""

import io
import json
import os
import shutil
import tarfile
import tempfile
from unittest.mock import patch

from r2.lib import backups
from r2.tests import TipprTestCase

NAME = "tippr-backup-20261101-120000"


class TestDownload(TipprTestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.folder = os.path.join(self.root, NAME)
        os.makedirs(os.path.join(self.folder, "postgres"))
        self.contents = {
            "postgres/main.dump": os.urandom(3000),
            "media.tar.gz": b"x" * 512,
            "zookeeper.json": b"{}",
        }
        for path, data in self.contents.items():
            with open(os.path.join(self.folder, path), "wb") as f:
                f.write(data)
        self.write_manifest("done", list(self.contents))
        for p in (patch.object(backups, "backup_dir", lambda: self.root),
                  patch.object(backups, "remote", lambda: False)):
            p.start()
            self.addCleanup(p.stop)

    def write_manifest(self, state, paths):
        self.manifest = json.dumps({"name": NAME, "state": state,
                                    "files": [{"path": p} for p in paths]})
        with open(os.path.join(self.folder, "manifest.json"), "w") as f:
            f.write(self.manifest)

    def test_a_tar_of_the_backup_folder(self):
        size, chunks = backups.download(NAME)
        data = b"".join(chunks)
        self.assertEqual(len(data), size)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            names = tar.getnames()
            self.assertEqual(names[0], NAME + "/manifest.json")
            self.assertEqual(
                tar.extractfile(NAME + "/manifest.json").read().decode(),
                self.manifest)
            for path, contents in self.contents.items():
                self.assertEqual(tar.extractfile(NAME + "/" + path).read(),
                                 contents)

    def test_only_finished_backups(self):
        self.write_manifest("running", list(self.contents))
        self.assertIsNone(backups.download(NAME))

    def test_no_such_backup(self):
        self.assertIsNone(backups.download("tippr-backup-20200101-000000"))
        self.assertIsNone(backups.download("../etc"))

    def test_only_files_in_the_folder(self):
        self.write_manifest("done", ["../../outside"])
        self.assertIsNone(backups.download(NAME))

    def test_not_on_a_frontend(self):
        with patch.object(backups, "remote", lambda: True):
            self.assertIsNone(backups.download(NAME))
