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
"""Report this server's state for /admin/servers (r2.lib.server_status).

Run once a minute by tippr-job-server_status.timer, on every server:

    python scripts/server_status.py [path/to/run.ini]

It reads the ini only for ZooKeeper's address and login (and server_name),
and doesn't load the app, so it's quick. --print shows the report instead.
"""

import configparser
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)

# the module on its own, not the r2 package (whose start-up the app needs)
_spec = importlib.util.spec_from_file_location(
    "server_status", os.path.join(SRC, "r2", "r2", "lib", "server_status.py"))
server_status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server_status)


def settings(ini):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(ini)
    return parser.defaults()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ini = args[0] if args else os.environ.get(
        "TIPPR_INI", os.path.join(SRC, "r2", "run.ini"))
    config = settings(ini)
    state = server_status.collect(name=config.get("server_name") or None,
                                  src=SRC)
    if "--print" in sys.argv:
        print(json.dumps(state, indent=1, sort_keys=True))
        return

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
        server_status.publish(zk, state, acl=acl)
    finally:
        zk.stop()
        zk.close()


if __name__ == "__main__":
    main()
