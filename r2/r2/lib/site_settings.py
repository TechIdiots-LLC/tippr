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
        self.listeners = []

        @client.DataWatch(self.path)
        def watcher(data, stat):
            try:
                self.data = json.loads(data) if data else {}
            except ValueError:
                log.exception("site_settings: bad JSON in %s", self.path)
                self.data = {}
            self.notify()

    def notify(self):
        for listener in self.listeners:
            try:
                listener(dict(self.data))
            except Exception:
                log.exception("site_settings: listener for %s failed",
                              self.path)


def _group(name):
    group = _groups.get(name)
    if group is None:
        group = _groups[name] = _SettingsGroup(g.zookeeper, name)
    return group


def on_change(name, listener):
    """Call listener(data) now and whenever the group changes (in this or
    any other process)."""
    group = _group(name)
    group.listeners.append(listener)
    listener(dict(group.data))


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
    group.notify()
