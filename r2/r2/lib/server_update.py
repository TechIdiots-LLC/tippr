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
"""Updating the servers to a new release from /admin/servers.

The web app can't update anything itself: it runs as the site's user, and
an update replaces the code and re-runs the installer as root. So the page
only asks: it writes a request (a release's version) to ZooKeeper, which
every server reads. On each server, tippr-update.timer runs
/usr/local/sbin/tippr-update (scripts/tippr_update.py, a root-owned copy)
once a minute; it sees the request, updates that server and reports how
it's going under STATUS_PATH/<server id>, which the page shows.

The updater downloads only from the repository in /etc/tippr/updates.conf
(root's, written by the installer), and checks the installer tarball
against the release's SHA256SUMS; the request names a version, nothing
else. Servers update one at a time. If the site doesn't answer afterwards,
the updater puts the old code back.
"""

import json
import secrets
import time

# the same paths as scripts/tippr_update.py (server_update_test checks)
REQUEST_PATH = "/tippr/update/request"
STATUS_PATH = "/tippr/update/status"

# the updater's states, and what the page calls them
STATES = {
    "waiting": "waiting its turn",
    "downloading": "downloading",
    "backing_up": "backing up the site",
    "installing": "installing",
    "checking": "checking the site",
    "rolling_back": "putting the old version back",
    "done": "updated",
    "failed": "failed",
    "rolled_back": "failed, old version back",
    "unsupported": "can't update from here",
    "disabled": "updates are off",
}
ACTIVE_STATES = ("downloading", "backing_up", "installing", "checking",
                 "rolling_back")
FINISHED_STATES = ("done", "failed", "rolled_back", "unsupported", "disabled")


def _get(zk, path):
    try:
        data, _stat = zk.get(path)
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def request(zk):
    """The update asked for, or None."""
    return _get(zk, REQUEST_PATH)


def statuses(zk):
    """{server id: the updater's last report}."""
    found = {}
    try:
        ids = zk.get_children(STATUS_PATH)
    except Exception:
        return found
    for server in ids:
        status = _get(zk, "%s/%s" % (STATUS_PATH, server))
        if status:
            found[server] = status
    return found


def ask(zk, version, requested_by, backup=True):
    """Ask every server to update to version (replacing an earlier ask)."""
    data = json.dumps(dict(
        id=secrets.token_hex(8), version=version, requested_by=requested_by,
        requested=int(time.time()), backup=bool(backup))).encode("utf-8")
    acl = [zk.make_acl(read=True, write=True, create=True, delete=True)]
    zk.ensure_path("/tippr/update", acl=acl)
    if zk.exists(REQUEST_PATH):
        zk.set(REQUEST_PATH, data)
    else:
        zk.create(REQUEST_PATH, data, acl=acl)


def cancel(zk):
    """Take the ask back (servers already updating carry on)."""
    if zk.exists(REQUEST_PATH):
        zk.delete(REQUEST_PATH)


def in_progress(zk):
    """Whether a server is updating right now."""
    return any(s.get("state") in ACTIVE_STATES and
               time.time() - s.get("updated", 0) < 3 * 3600
               for s in statuses(zk).values())
