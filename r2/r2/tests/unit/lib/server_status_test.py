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
"""A server's report for /admin/servers: which services, and its role."""

import unittest
from types import SimpleNamespace
from unittest import mock

from r2.lib import server_status


def systemctl(states, enabled=None):
    """A subprocess.run answering `systemctl show` from states:
    {unit: "LoadState ActiveState UnitFileState"}, and `systemctl
    is-enabled` from enabled: {unit: answer}."""
    def run(args, **kw):
        unit = args[2][:-len(".service")]
        if args[1] == "is-enabled":
            return SimpleNamespace(stdout=(enabled or {}).get(unit, "enabled"))
        return SimpleNamespace(stdout=states.get(unit, "not-found inactive"))
    return run


class ServicesTest(unittest.TestCase):
    def services(self, states, enabled=None):
        with mock.patch.object(server_status.subprocess, "run",
                               systemctl(states, enabled)):
            return {s["unit"]: s["state"] for s in server_status._services()}

    def test_init_script_services(self):
        # Cassandra's and ZooKeeper's units are made from init scripts
        found = self.services(
            {"cassandra": "loaded inactive generated",
             "zookeeper": "loaded inactive generated"},
            enabled={"cassandra": "disabled", "zookeeper": "enabled"})
        self.assertEqual(found, {"zookeeper": "inactive"})

    def test_running_and_failed_are_listed(self):
        found = self.services({
            "nginx": "loaded active enabled",
            "cassandra": "loaded failed enabled",
        })
        self.assertEqual(found, {"nginx": "active", "cassandra": "failed"})

    def test_turned_off_here_is_left_out(self):
        # a frontend's databases, a backend's web app (docs/SERVERS.md)
        found = self.services({
            "postgresql": "loaded inactive disabled",
            "tippr-paster": "loaded inactive masked",
            "nginx": "loaded active enabled",
        })
        self.assertEqual(found, {"nginx": "active"})

    def test_stopped_but_meant_to_run_is_listed(self):
        found = self.services({"rabbitmq-server": "loaded inactive enabled"})
        self.assertEqual(found, {"rabbitmq-server": "inactive"})

    def test_role(self):
        with mock.patch.object(server_status, "_services", lambda: []), \
                mock.patch.object(server_status, "_disks", lambda: []):
            self.assertEqual(server_status.collect()["role"], "all")
            self.assertEqual(server_status.collect(role="frontend")["role"],
                             "frontend")
