#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################

"""The Docker jobs container runs the systemd timers' jobs itself
(docker/tippr_docker.py), reading each timer's OnCalendar. A timer written
in a form its parser doesn't know stops the container, which a release only
finds out in the smoke test; check every timer here instead."""

import ast
import datetime
import glob
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def load_next_run():
    # just the function: the rest of the script needs the container
    path = os.path.join(ROOT, "docker", "tippr_docker.py")
    with open(path) as f:
        tree = ast.parse(f.read())
    fn = next(node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "next_run")
    namespace = {"re": re, "datetime": datetime}
    exec(compile(ast.Module([fn], []), path, "exec"), namespace)
    return namespace["next_run"]


class TestDockerTimers(unittest.TestCase):
    def test_every_timer_parses(self):
        next_run = load_next_run()
        now = datetime.datetime(2026, 10, 19, 23, 59, 30)
        timers = glob.glob(os.path.join(ROOT, "systemd", "*.timer"))
        self.assertTrue(timers)
        for path in timers:
            with open(path) as f:
                match = re.search(r"(?m)^OnCalendar=(.*)$", f.read())
            if not match:
                continue
            with self.subTest(timer=os.path.basename(path)):
                self.assertGreater(next_run(match.group(1), now), now)

    def test_forms(self):
        next_run = load_next_run()
        now = datetime.datetime(2026, 10, 19, 10, 7, 30)
        self.assertEqual(next_run("*:0/15", now), now.replace(minute=15, second=0))
        self.assertEqual(next_run("*:05", now), now.replace(hour=11, minute=5, second=0))
        self.assertEqual(next_run("*-*-* 00:30", now),
                         datetime.datetime(2026, 10, 20, 0, 30))
        self.assertEqual(next_run("*-*-* 16:30:00", now),
                         now.replace(hour=16, minute=30, second=0))
        self.assertEqual(next_run("hourly", now), now.replace(hour=11, minute=0, second=0))
