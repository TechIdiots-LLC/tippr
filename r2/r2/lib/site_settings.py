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
"""Site settings that admins can change while the site is running.

Each group of settings (e.g. "email") is a JSON object stored in ZooKeeper at
/tippr/settings/<group>. Values saved there override the ini file. Every
process watches its groups' nodes, so a change applies everywhere without a
restart. The nodes are only readable with the app's ZooKeeper credentials.
"""

import json
import logging

from pylons import app_globals as g

log = logging.getLogger(__name__)

SETTINGS_ROOT = "/tippr/settings"

_groups = {}


class _SettingsGroup:
    def __init__(self, client, name):
        self.path = "%s/%s" % (SETTINGS_ROOT, name)
        self.data = {}

        @client.DataWatch(self.path)
        def watcher(data, stat):
            try:
                self.data = json.loads(data) if data else {}
            except ValueError:
                log.exception("site_settings: bad JSON in %s", self.path)
                self.data = {}


def _group(name):
    group = _groups.get(name)
    if group is None:
        group = _groups[name] = _SettingsGroup(g.zookeeper, name)
    return group


def get_settings(name):
    """Return the saved overrides for a settings group (may be empty)."""
    return dict(_group(name).data)


def save_settings(name, data):
    """Replace the saved overrides for a settings group."""
    client = g.zookeeper
    group = _group(name)
    acl = [client.make_acl(read=True, write=True, create=True, delete=True,
                           admin=True)]
    client.ensure_path(SETTINGS_ROOT, acl=acl)
    client.ensure_path(group.path, acl=acl)
    client.set(group.path, json.dumps(data, sort_keys=True).encode("utf-8"))
    # the watcher will also update this, but make it visible immediately
    group.data = dict(data)
