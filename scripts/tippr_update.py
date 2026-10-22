#!/usr/bin/python3
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
"""Update this server to the release asked for on /admin/servers
(r2.lib.server_update).

Installed by the installer as /usr/local/sbin/tippr-update (root's own
copy: it runs as root, so not from the site user's source tree or
virtualenv) and run once a minute by tippr-update.timer. It uses only the
system Python and python3-kazoo. Most runs see nothing to do and stop.

When there is a request it hasn't done:

1. it waits while another server is updating (one at a time);
2. downloads the release's installer tarball and SHA256SUMS from GitHub,
   from the repository in /etc/tippr/updates.conf only, and checks the
   tarball against them;
3. makes a site backup first, if asked (tippr-backup export);
4. stops the site, keeps the old code as <src>.old, unpacks the new code
   and runs tippr-firstboot <domain>, as docs/PROXMOX.md does by hand;
5. checks that the site answers. If it doesn't, it puts the old code back
   and runs the installer again.

How it goes is written to ZooKeeper for the page, and to
/var/log/tippr-update.log. Only installs with tippr-firstboot (Proxmox
containers) can be updated this way; others are told so.

    tippr-update            do any update asked for (the timer)
    tippr-update --status   show the request and this server's status
"""

import hashlib
import http.client
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import time
import urllib.request

CONF = "/etc/tippr/updates.conf"
FIRSTBOOT = "/usr/local/sbin/tippr-firstboot"
BACKUP = "/usr/local/bin/tippr-backup"
LOG = "/var/log/tippr-update.log"
WORK = "/var/lib/tippr/updates"

# the same as r2.lib.server_update
REQUEST_PATH = "/tippr/update/request"
STATUS_PATH = "/tippr/update/status"
LOCK_PATH = "/tippr/update/lock"
ACTIVE_STATES = ("downloading", "backing_up", "installing", "checking",
                 "rolling_back")
# an "active" status this old is from an updater that died
STALE_ACTIVE_SECONDS = 3 * 3600

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$")
REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
DOWNLOAD_TIMEOUT = 60
INSTALL_TIMEOUT = 3 * 3600
CHECK_SECONDS = 300


class UpdateError(Exception):
    pass


def log(message):
    line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_tail(lines=15):
    try:
        with open(LOG, errors="replace") as f:
            return [l.rstrip("\n")[:300] for l in f.readlines()[-lines:]]
    except OSError:
        return []


###############################################################################
# Settings
###############################################################################

def read_conf(path=CONF):
    """/etc/tippr/updates.conf (KEY=VALUE lines): root's, so the site's
    user can't point updates elsewhere. None if it's missing or anyone but
    root could change it."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    if st.st_uid != 0 or st.st_mode & 0o022:
        log("%s isn't root's alone (owner %d, mode %o): not updating"
            % (path, st.st_uid, st.st_mode & 0o777))
        return None
    conf = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                conf[key.strip()] = value.strip().strip('"').strip("'")
    return conf


def read_ini(path):
    """The few settings needed from the site's ini: ZooKeeper's address and
    login, and the domain. (Read as text, not run.)"""
    import configparser
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(path)
    return parser.defaults()


def server_id():
    """As r2.lib.server_status.server_id."""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path) as f:
                value = f.read().strip()
            if value:
                return value[:12]
        except OSError:
            pass
    import socket
    return hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]


def current_version(src):
    try:
        with open(os.path.join(src, "tippr", "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return ""


###############################################################################
# ZooKeeper
###############################################################################

class Zk:
    """A short connection for each read or write: an update restarts
    things, ZooKeeper included, so nothing is held open across one."""

    def __init__(self, ini):
        self.hosts = ini.get("zookeeper_connection_string", "localhost:2181")
        self.user = ini.get("zookeeper_username", "")
        self.password = ini.get("zookeeper_password", "")

    def connect(self):
        from kazoo.client import KazooClient
        zk = KazooClient(hosts=self.hosts, timeout=10, auth_data=[
            ("digest", "%s:%s" % (self.user, self.password))]
            if self.user else None)
        zk.start(timeout=15)
        return zk

    def acl(self):
        if not self.user:
            return None
        from kazoo.security import make_digest_acl
        return [make_digest_acl(self.user, self.password, all=True)]

    def get(self, path):
        zk = self.connect()
        try:
            data, _stat = zk.get(path)
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None
        finally:
            zk.stop()
            zk.close()

    def claim(self, me, status):
        """Start this server's turn: under a lock, so two servers can't both
        see nobody updating and start together. False if another server is
        updating."""
        zk = self.connect()
        try:
            lock = zk.Lock(LOCK_PATH, me)
            if not lock.acquire(blocking=True, timeout=30):
                return False
            try:
                for server in (zk.get_children(STATUS_PATH)
                               if zk.exists(STATUS_PATH) else []):
                    if server == me:
                        continue
                    try:
                        other = json.loads(zk.get("%s/%s" % (
                            STATUS_PATH, server))[0].decode("utf-8"))
                    except Exception:
                        continue
                    if (other.get("state") in ACTIVE_STATES and
                            time.time() - other.get("updated", 0)
                            < STALE_ACTIVE_SECONDS):
                        return False
                status.set("downloading", zk=zk)
                return True
            finally:
                lock.release()
        finally:
            zk.stop()
            zk.close()

    def _write(self, zk, path, data):
        zk.ensure_path(os.path.dirname(path), acl=self.acl())
        if zk.exists(path):
            zk.set(path, data)
        else:
            zk.create(path, data, acl=self.acl())

    def put(self, path, value, zk=None):
        """Write value (JSON) at path: with zk, on that connection; else on
        a new one, retried for a while (ZooKeeper may be restarting)."""
        data = json.dumps(value, sort_keys=True).encode("utf-8")
        if zk is not None:
            self._write(zk, path, data)
            return True
        for attempt in range(12):
            try:
                conn = self.connect()
            except Exception as e:
                log("couldn't reach ZooKeeper (%s); trying again" % e)
                time.sleep(10)
                continue
            try:
                self._write(conn, path, data)
                return True
            except Exception as e:
                log("couldn't write to ZooKeeper (%s); trying again" % e)
                time.sleep(10)
            finally:
                conn.stop()
                conn.close()
        log("couldn't write %s to ZooKeeper" % path)
        return False


class Status:
    """This server's status record for the page."""

    def __init__(self, zk, me, request, from_version):
        self.zk, self.me = zk, me
        self.record = dict(request_id=request["id"],
                           version=request["version"],
                           from_version=from_version,
                           started=int(time.time()))

    def set(self, state, message="", zk=None):
        log("%s: %s %s" % (self.record["version"], state, message))
        self.record.update(state=state, message=message,
                           updated=int(time.time()), log=log_tail())
        self.zk.put("%s/%s" % (STATUS_PATH, self.me), self.record, zk=zk)


###############################################################################
# The update
###############################################################################

def download(url, dest):
    log("downloading %s" % url)
    request = urllib.request.Request(url, headers={"User-Agent": "tippr-update"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response, \
            open(dest, "wb") as f:
        shutil.copyfileobj(response, f, 1024 * 1024)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_release(repo, version):
    """The release's installer tarball, checked against its SHA256SUMS."""
    name = "tippr-%s-installer.tar.gz" % version
    folder = os.path.join(WORK, version)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    base = "https://github.com/%s/releases/download/v%s/" % (repo, version)
    tarball = os.path.join(folder, name)
    sums = os.path.join(folder, "SHA256SUMS")
    try:
        download(base + "SHA256SUMS", sums)
        download(base + name, tarball)
    except OSError as e:
        raise UpdateError("couldn't download the release: %s" % e)
    wanted = None
    with open(sums) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                wanted = parts[0].lower()
    if not wanted:
        raise UpdateError("SHA256SUMS doesn't list %s" % name)
    if sha256(tarball) != wanted:
        raise UpdateError("%s doesn't match its checksum" % name)
    log("checksum OK")
    return tarball


def unpack(tarball, dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    with tarfile.open(tarball) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            # (a Python without extraction filters: check the names)
            for member in tar.getmembers():
                if (member.name.startswith("/") or ".." in member.name.split("/")
                        or member.issym() or member.islnk()):
                    raise UpdateError("unsafe path in the tarball: %s" % member.name)
            tar.extractall(dest)
    if not os.path.exists(os.path.join(dest, "tippr", "install-tippr.sh")):
        raise UpdateError("the tarball has no tippr/install-tippr.sh")


def run(command, timeout=None):
    """Run a command with its output in the log; its exit status."""
    log("running: %s" % " ".join(command))
    with open(LOG, "a") as out:
        try:
            return subprocess.run(command, stdout=out, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            log("timed out after %d seconds" % timeout)
            return -1


def site_answers(domain, seconds=CHECK_SECONDS):
    """Whether the front page comes back 200 within seconds."""
    deadline = time.time() + seconds
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    while time.time() < deadline:
        for conn in (http.client.HTTPSConnection("127.0.0.1", 443, timeout=20,
                                                 context=context),
                     http.client.HTTPConnection("127.0.0.1", 80, timeout=20)):
            try:
                conn.request("GET", "/", headers={"Host": domain,
                                                  "User-Agent": "tippr-update"})
                if conn.getresponse().status == 200:
                    return True
            except (OSError, http.client.HTTPException):
                pass
            finally:
                conn.close()
        time.sleep(10)
    return False


def install(src, user, domain):
    """Run the installer (tippr-firstboot) from the code now in src."""
    shutil.copyfile(os.path.join(src, "tippr", "proxmox", "tippr-firstboot"),
                    FIRSTBOOT)
    os.chmod(FIRSTBOOT, 0o755)
    subprocess.run(["chown", "-R", "%s:%s" % (user, user), src], check=True)
    return run([FIRSTBOOT, domain], timeout=INSTALL_TIMEOUT) == 0


def update(conf, ini, status, request):
    version = request["version"]
    src = conf.get("TIPPR_SRC", "/home/tippr/src").rstrip("/")
    user = conf.get("TIPPR_USER", "tippr")
    repo = conf.get("TIPPR_RELEASE_REPO", "")
    domain = (ini.get("domain") or "").strip().lower()
    if not REPO_RE.match(repo):
        raise UpdateError("TIPPR_RELEASE_REPO in %s isn't owner/name" % CONF)
    if not DOMAIN_RE.match(domain):
        raise UpdateError("the site's domain (%r) doesn't look like one" % domain)

    tarball = fetch_release(repo, version)
    new, old, failed = src + ".new", src + ".old", src + ".failed"
    unpack(tarball, new)

    if request.get("backup", True) and os.path.exists(BACKUP):
        status.set("backing_up")
        if run([BACKUP, "export"], timeout=INSTALL_TIMEOUT) != 0:
            raise UpdateError("the backup failed, so nothing was changed "
                              "(see %s)" % LOG)

    status.set("installing", "the site is down until this finishes "
                             "(5-10 minutes)")
    run(["systemctl", "stop", "tippr.target"])
    if os.path.exists(old):
        shutil.rmtree(old)
    os.rename(src, old)
    os.rename(new, src)
    ok = install(src, user, domain)
    if ok:
        status.set("checking")
        ok = site_answers(domain)
    if ok:
        shutil.rmtree(os.path.join(WORK, version), ignore_errors=True)
        status.set("done", "%s is kept as %s, to go back by hand"
                   % (os.path.basename(old), old))
        return

    status.set("rolling_back", "the new version didn't come up")
    run(["systemctl", "stop", "tippr.target"])
    if os.path.exists(failed):
        shutil.rmtree(failed)
    os.rename(src, failed)
    os.rename(old, src)
    if install(src, user, domain) and site_answers(domain):
        status.set("rolled_back", "%s didn't come up, so the old version is "
                   "back; the new code is in %s (see %s)"
                   % (version, failed, LOG))
    else:
        status.set("failed", "%s didn't come up, and the old version didn't "
                   "either: see %s" % (version, LOG))


def handle(conf):
    ini = read_ini(conf.get("TIPPR_INI", "/home/tippr/src/tippr/r2/run.ini"))
    zk = Zk(ini)
    me = server_id()
    try:
        request = zk.get(REQUEST_PATH)
    except Exception as e:
        log("couldn't reach ZooKeeper: %s" % e)
        return 1
    if not request or not request.get("id"):
        return 0
    mine = zk.get("%s/%s" % (STATUS_PATH, me)) or {}
    if mine.get("request_id") == request["id"]:
        if (mine.get("state") in ACTIVE_STATES and
                time.time() - mine.get("updated", 0) > STALE_ACTIVE_SECONDS):
            # (not tried again by itself: ask again from the page)
            mine.update(state="failed", updated=int(time.time()),
                        message="the updater stopped partway; see %s" % LOG)
            zk.put("%s/%s" % (STATUS_PATH, me), mine)
            return 0
        if mine.get("state") != "waiting":
            return 0                      # done, or doing it

    src = conf.get("TIPPR_SRC", "/home/tippr/src").rstrip("/")
    status = Status(zk, me, request, current_version(src))
    version = str(request.get("version", ""))
    if conf.get("TIPPR_WEB_UPDATES") != "1":
        status.set("disabled", "TIPPR_WEB_UPDATES is off for this server")
        return 0
    if not os.path.exists(FIRSTBOOT):
        status.set("unsupported", "this install has no tippr-firstboot "
                   "(a Proxmox container's): update it by hand")
        return 0
    if not VERSION_RE.match(version):
        status.set("failed", "%r isn't a version" % version)
        return 0
    if current_version(src) == version:
        status.set("done", "already on %s" % version)
        return 0

    # one server at a time: wait for any other that's updating
    if not zk.claim(me, status):
        if mine.get("state") != "waiting" or mine.get("request_id") != request["id"]:
            status.set("waiting", "another server is updating")
        return 0

    try:
        update(conf, ini, status, request)
    except UpdateError as e:
        status.set("failed", str(e))
    except Exception as e:
        log("unexpected error: %r" % e)
        status.set("failed", "unexpected error: %s (see %s)" % (e, LOG))
    return 0


def main():
    if os.geteuid() != 0:
        print("tippr-update: run as root")
        return 1
    conf = read_conf()
    if conf is None:
        return 0
    if "--status" in sys.argv:
        ini = read_ini(conf.get("TIPPR_INI", "/home/tippr/src/tippr/r2/run.ini"))
        zk = Zk(ini)
        print(json.dumps(dict(request=zk.get(REQUEST_PATH),
                              status=zk.get("%s/%s" % (STATUS_PATH, server_id()))),
                         indent=1))
        return 0
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    return handle(conf)


if __name__ == "__main__":
    sys.exit(main())
