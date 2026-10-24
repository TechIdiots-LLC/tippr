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
"""Each server's state, for /admin/servers.

Every server runs scripts/server_status.py once a minute (the
tippr-job-server_status timer): it reports this server's version, load,
memory, disks and services to ZooKeeper, under SERVERS_PATH/<id>, which
every server can read. A page request reaches only one frontend, so this is
how /admin/servers sees them all; one not heard from in a while is shown as
such.

A server is told apart by its id (from /etc/machine-id, which is unique per
machine or container and stays the same) and named by server_name in the
ini (the installer's TIPPR_SERVER_NAME), or else its host name.

This module only uses the standard library at import, so the reporter is
quick to start.
"""

import json
import os
import shutil
import socket
import subprocess
import time

SERVERS_PATH = "/tippr/servers"
STALE_SECONDS = 180  # not heard from in this long: shown as missing
# Only each server's latest report is kept (each one replaces the last). One
# not heard from in this long is removed (sooner: "forget" on the page).
FORGET_SECONDS = 7 * 24 * 3600

# disks worth knowing about (those that exist here); several on one
# filesystem are reported once
DISK_PATHS = [
    ("/", "system"),
    ("/srv/www/media", "media"),
    ("/var/lib/postgresql", "PostgreSQL"),
    ("/var/lib/cassandra", "Cassandra"),
    ("/var/lib/opensearch", "OpenSearch"),
    ("/var/lib/zookeeper", "ZooKeeper"),
    ("/var/lib/rabbitmq", "RabbitMQ"),
    ("/var/lib/tippr/backups", "backups"),
]

# services worth knowing about (those installed here)
SERVICES = [
    ("nginx", "nginx"),
    ("tippr-paster", "web app"),
    ("tippr-consumers", "queue processors"),
    ("tippr-websockets", "websockets"),
    ("tippr-activity", "activity"),
    ("memcached", "memcached"),
    ("postgresql", "PostgreSQL"),
    ("cassandra", "Cassandra"),
    ("rabbitmq-server", "RabbitMQ"),
    ("zookeeper", "ZooKeeper"),
    ("opensearch", "OpenSearch"),
]


def server_id():
    """This machine's id: the start of /etc/machine-id (or of a hash of
    the host name, without one)."""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path) as f:
                value = f.read().strip()
            if value:
                return value[:12]
        except OSError:
            pass
    import hashlib
    return hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def _memory():
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            info[name] = int(parts[0]) * 1024
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    return dict(total=total, used=max(0, total - available),
                swap_total=swap_total,
                swap_used=max(0, swap_total - info.get("SwapFree", 0)))


def _disks():
    found = {}
    for path, label in DISK_PATHS:
        try:
            dev = os.stat(path).st_dev
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        if dev in found:
            found[dev]["labels"].append(label)
            continue
        found[dev] = dict(path=path, labels=[label], total=usage.total,
                          used=usage.used, free=usage.free)
    return list(found.values())


def _services():
    """The SERVICES installed here, and their states. One that's turned off
    and stopped is left out: this server doesn't run it (a frontend's
    databases, a backend's web app; docs/SERVERS.md)."""
    result = []
    for unit, label in SERVICES:
        try:
            out = subprocess.run(
                ["systemctl", "show", unit + ".service",
                 "-p", "LoadState", "-p", "ActiveState",
                 "-p", "UnitFileState", "--value"],
                capture_output=True, text=True, timeout=5).stdout.split()
        except (OSError, subprocess.SubprocessError):
            continue
        if len(out) < 2 or out[0] != "loaded":
            continue
        if out[1] == "inactive" and _turned_off(unit, out[2:3]):
            continue
        result.append(dict(unit=unit, label=label, state=out[1]))
    return result


def _turned_off(unit, file_state):
    """Whether unit is disabled. Ones made from init scripts (Cassandra's,
    ZooKeeper's) say "generated" instead, so ask is-enabled for those."""
    if file_state and file_state[0] in ("disabled", "masked"):
        return True
    if file_state and file_state[0] != "generated":
        return False
    try:
        return subprocess.run(
            ["systemctl", "is-enabled", unit + ".service"],
            capture_output=True, text=True,
            timeout=5).stdout.strip().endswith("disabled")
    except (OSError, subprocess.SubprocessError):
        return False


def _version(src):
    version = _read(os.path.join(src, "VERSION")).strip()
    commit = ""
    try:
        commit = subprocess.run(
            ["git", "-C", src, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return version, commit


def collect(name=None, src=None, role=None):
    """This server's state (a dict, as stored). role: all, backend or
    frontend (server_role, from the installer; docs/SERVERS.md)."""
    src = src or os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    version, commit = _version(src)
    uptime = _read("/proc/uptime").split()
    try:
        load = os.getloadavg()
    except OSError:
        load = (0, 0, 0)
    return dict(
        id=server_id(),
        name=name or socket.gethostname(),
        host=socket.gethostname(),
        role=role or "all",
        version=version,
        commit=commit,
        reported=int(time.time()),
        uptime=int(float(uptime[0])) if uptime else None,
        cpus=os.cpu_count() or 1,
        load=[round(x, 2) for x in load],
        memory=_memory(),
        disks=_disks(),
        services=_services(),
    )


def publish(zk, state, acl=None):
    """Store state under SERVERS_PATH/<id> (zk: a started KazooClient)."""
    path = "%s/%s" % (SERVERS_PATH, state["id"])
    data = json.dumps(state, sort_keys=True).encode("utf-8")
    zk.ensure_path(SERVERS_PATH, acl=acl)
    if zk.exists(path):
        zk.set(path, data)
    else:
        zk.create(path, data, acl=acl)
    # servers gone for a week: no longer listed
    for old in read_all(zk):
        if old["age"] > FORGET_SECONDS:
            forget(zk, old["id"])


def read_all(zk):
    """Every server's last report, with "age" (seconds since) and "stale",
    sorted by name."""
    servers = []
    try:
        ids = zk.get_children(SERVERS_PATH)
    except Exception:
        return []
    now = time.time()
    for server in ids:
        try:
            data, _stat = zk.get("%s/%s" % (SERVERS_PATH, server))
            state = json.loads(data.decode("utf-8"))
        except Exception:
            continue
        state["age"] = int(now - state.get("reported", 0))
        state["stale"] = state["age"] > STALE_SECONDS
        servers.append(state)
    return sorted(servers, key=lambda s: (s.get("name") or "", s["id"]))


def forget(zk, server):
    """Remove a server's report (one taken out of service)."""
    path = "%s/%s" % (SERVERS_PATH, server)
    if zk.exists(path):
        zk.delete(path)
