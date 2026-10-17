#!/usr/bin/env python3
"""Export a whole tippr site to a folder, and restore it on another server.

Installed as `tippr-backup` (run as root):

    tippr-backup export [--offline]     write a backup to backup_dir
    tippr-backup list                   list the backups in backup_dir
    tippr-backup restore DIR [--yes]    replace this site's data with DIR
    tippr-backup import URL --key KEY [--fresh [--offline]] [--name NAME]
                                        copy a backup from another tippr
                                        server (its /admin/backups makes
                                        the transfer key)
    tippr-backup process-queue          run requests made on /admin/backups

A backup is a folder holding everything that can't be rebuilt:

    manifest.json        what is in it, and its progress while running
    postgres/*.dump      pg_dump (custom format) of each PostgreSQL database
    cassandra/           the keyspace's table definitions and every row
                         (one gzipped JSON line per row)
    zookeeper.json       the ZooKeeper tree: saved site settings, throttles,
                         and live config / secrets when they are kept there
    media.tar.gz         uploaded media (filesystem media provider)
    secrets.json         the signing secrets, so logins and links keep working

Not included, because they are rebuilt or transient: the search index
(restore rebuilds it), memcached (restore flushes it) and RabbitMQ queues
(--offline waits for them to empty first).

Restore reads the ini on the server it runs on, so the data goes wherever
that server is configured to keep it: export from a single VM and restore
on an app server whose ini points at separate database, Cassandra and
ZooKeeper machines. Only this server's own passwords are kept; the signing
secrets come from the backup.

Backups belong to the user tippr runs as (the ini's owner), readable by
nobody else. The web app reads them to list them and to send them to
another server that presents the transfer key; it can read all of this
data anyway.

This script uses only the venv's cassandra-driver, kazoo and requests, not
r2, so it works when the app can't start.
"""

import argparse
import base64
import configparser
import datetime
import fcntl
import gzip
import hashlib
import json
import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time

FORMAT_VERSION = 1
DEFAULT_BACKUP_DIR = "/var/lib/tippr/backups"
QUEUE_DIR = "/var/lib/tippr/backup-queue"
# one backup, import or restore at a time per site (in backup_dir)
LOCK_FILE = ".lock"
SECRETS_ENV = "/etc/tippr/secrets.env"
KEYSPACE = "tippr"
NAME_RE = re.compile(r"^tippr-backup-\d{8}-\d{6}$")
# the current or last request from /admin/backups (in backup_dir)
JOB_FILE = "job.json"
# ZooKeeper nodes not backed up: ZooKeeper's own config and quotas, and
# this server's transfer key (it must not open up the server the backup is
# restored on)
ZK_SKIP = ("/zookeeper", "/tippr/settings/backups")
# the transfer API sends files in pieces this big (one request each, well
# inside gunicorn's timeout); must match r2.lib.backups.CHUNK_SIZE
CHUNK_SIZE = 16 * 1024 * 1024
# the web app and its websockets; stopped first so nothing new is queued
WEB_UNITS = ("tippr-paster.service", "tippr-websockets.service")


class BackupError(Exception):
    pass


###############################################################################
# Configuration (the ini)
###############################################################################

class Config:
    def __init__(self, ini_path):
        self.ini_path = os.path.abspath(ini_path)
        self.root = os.path.dirname(self.ini_path)
        parser = configparser.ConfigParser(
            defaults={"here": self.root}, strict=False)
        parser.optionxform = str
        if not parser.read(self.ini_path):
            raise BackupError("can't read %s" % self.ini_path)
        self.parser = parser
        st = os.stat(self.ini_path)
        self.uid, self.gid = st.st_uid, st.st_gid
        self.user = pwd.getpwuid(st.st_uid).pw_name

    def get(self, name, default=None, section="DEFAULT"):
        try:
            return self.parser.get(section, name).strip()
        except (configparser.Error, KeyError):
            return default

    @property
    def backup_dir(self):
        return self.get("backup_dir") or DEFAULT_BACKUP_DIR

    def databases(self):
        """{dbname: (host, port, user, password)}, one per real database
        (r2's logical databases usually all share one)."""
        result = {}
        for logical in _split(self.get("databases", "")):
            params = _split(self.get(logical + "_db", ""))
            params += ["*"] * (5 - len(params))
            name, host, user, password, port = params[:5]
            user = self.get("db_user") if user == "*" else user
            password = self.get("db_pass") if password == "*" else password
            port = self.get("db_port", "5432") if port == "*" else port
            result.setdefault(name, (host, port, user, password))
        return result

    def cassandra_hosts(self):
        return [s.split(":", 1)[0]
                for s in _split(self.get("cassandra_seeds", "127.0.0.1"))]

    def zookeeper(self):
        return (self.get("zookeeper_connection_string", "localhost:2181"),
                self.get("zookeeper_username", ""),
                self.get("zookeeper_password", ""))

    def media_root(self):
        if self.get("media_provider", "filesystem") != "filesystem":
            return None
        return self.get("media_fs_root")

    def memcache_hosts(self):
        hosts = set()
        for key, value in self.parser.items("DEFAULT"):
            if key.endswith("memcaches") or key == "lockcaches":
                hosts.update(_split(value))
        return sorted(hosts)

    def signing_secrets(self):
        """The [secrets] section plus tracking_secret, as written (the
        installer doesn't escape them)."""
        secrets = {}
        if self.parser.has_section("secrets"):
            defaults = self.parser.defaults()
            secrets = {k: v for k, v in
                       self.parser.items("secrets", raw=True)
                       if k not in defaults}
        if self.parser.has_option("DEFAULT", "tracking_secret"):
            secrets["tracking_secret"] = self.parser.get(
                "DEFAULT", "tracking_secret", raw=True).strip()
        return secrets


def _split(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


###############################################################################
# Helpers
###############################################################################

# the user tippr runs as, which owns backups (set from the ini's owner)
OWNER = None
# the /admin/backups request being run, shown on that page
JOB = None


def log(message):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = "[%s] %s" % (stamp, message)
    print(line, flush=True)
    if JOB is not None:
        JOB.log(line)


class Job:
    """The status of a request from /admin/backups, in backup_dir/job.json
    so the page can show it (even while the web app is stopped for it)."""

    def __init__(self, backup_dir, request):
        self.path = os.path.join(backup_dir, JOB_FILE)
        self.data = {
            "action": request.get("action"),
            "requested_by": request.get("requested_by"),
            "requested": request.get("requested"),
            "name": request.get("name"),
            "source": request.get("url"),
            "state": "running",
            "started": now_iso(),
            "finished": None,
            "error": None,
            "log": [],
        }
        self.save()

    def log(self, line):
        self.data["log"] = (self.data["log"] + [line])[-40:]
        self.save()

    def finish(self, error=None):
        self.data["state"] = "failed" if error else "done"
        self.data["error"] = error
        self.data["finished"] = now_iso()
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        write_json(self.path, self.data)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")


def run(cmd, env=None, user=None, cwd=None):
    program = cmd[0]
    if user and os.geteuid() == 0:
        cmd = ["runuser", "-u", user, "--"] + cmd
    result = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True,
                            text=True)
    if result.returncode != 0:
        raise BackupError("%s failed: %s" % (
            program, (result.stderr or result.stdout).strip()[-2000:]))
    return result.stdout


def systemctl(*args):
    if shutil.which("systemctl") and os.path.isdir("/run/systemd/system"):
        subprocess.run(["systemctl"] + list(args), check=False)


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    private_file(tmp)
    os.replace(tmp, path)


def private_file(path):
    """Backup data holds password hashes, emails and secrets: only the
    tippr user (and root) may read it."""
    os.chmod(path, 0o600)
    if OWNER is not None and os.geteuid() == 0:
        os.chown(path, *OWNER)


def private_dir(path):
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)
    if OWNER is not None and os.geteuid() == 0:
        os.chown(path, *OWNER)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_files(path):
    """Every file in a backup except the manifest, with size and hash (the
    manifest lists them so a copy can be checked)."""
    files = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, path)
            if rel == "manifest.json" or rel.endswith(".tmp"):
                continue
            files.append({"path": rel, "size": os.path.getsize(full),
                          "sha256": file_sha256(full)})
    return files


def dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def git_commit(config):
    try:
        return subprocess.run(
            # as root, git refuses a checkout owned by the tippr user
            ["git", "-c", "safe.directory=*", "-C", config.root,
             "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


###############################################################################
# Export
###############################################################################

class Export:
    def __init__(self, config, offline=False, requested_by=None, dest=None):
        self.config = config
        self.offline = offline
        name = "tippr-backup-" + datetime.datetime.now().strftime(
            "%Y%m%d-%H%M%S")
        self.path = os.path.join(dest or config.backup_dir, name)
        self.manifest = {
            "format": FORMAT_VERSION,
            "name": name,
            "state": "running",
            "step": "starting",
            "started": now_iso(),
            "finished": None,
            "offline": offline,
            "requested_by": requested_by,
            "source": {
                "hostname": socket.gethostname(),
                "domain": config.get("domain"),
                "commit": git_commit(config),
            },
            "components": {},
            "error": None,
        }

    def save(self):
        write_json(os.path.join(self.path, "manifest.json"), self.manifest)

    def step(self, name):
        log(name)
        self.manifest["step"] = name
        self.save()

    def run(self):
        private_dir(os.path.dirname(self.path))
        os.makedirs(self.path)
        private_dir(self.path)
        self.save()
        stopped = False
        try:
            if self.offline:
                self.step("taking the site offline")
                take_offline()
                stopped = True
            self.export_postgres()
            self.export_cassandra()
            self.export_zookeeper()
            self.export_media()
            self.export_secrets()
            self.step("checking the files")
            self.manifest["files"] = backup_files(self.path)
            self.manifest["state"] = "done"
            self.manifest["step"] = "done"
        except Exception as e:
            self.manifest["state"] = "failed"
            self.manifest["error"] = str(e)
            log("FAILED: %s" % e)
            raise
        finally:
            if stopped:
                log("bringing the site back")
                systemctl("start", "tippr.target")
            self.manifest["finished"] = now_iso()
            self.manifest["size"] = dir_size(self.path)
            self.save()
        log("backup written to %s" % self.path)
        return self.path

    def export_postgres(self):
        self.step("exporting PostgreSQL")
        private_dir(os.path.join(self.path, "postgres"))
        dumped = {}
        for name, (host, port, user, password) in \
                self.config.databases().items():
            out = os.path.join(self.path, "postgres", name + ".dump")
            env = dict(os.environ, PGPASSWORD=password or "")
            run(["pg_dump", "--format=custom", "--no-owner",
                 "--host", host, "--port", str(port), "--username", user,
                 "--file", out, name], env=env)
            private_file(out)
            dumped[name] = {"file": "postgres/%s.dump" % name,
                            "size": os.path.getsize(out)}
        self.manifest["components"]["postgres"] = dumped

    def export_cassandra(self):
        from cassandra.cluster import Cluster
        from cassandra.query import SimpleStatement

        self.step("exporting Cassandra")
        folder = os.path.join(self.path, "cassandra")
        private_dir(folder)
        cluster = Cluster(self.config.cassandra_hosts())
        session = cluster.connect()
        session.default_timeout = 120
        try:
            keyspace = cluster.metadata.keyspaces.get(KEYSPACE)
            if keyspace is None:
                raise BackupError("Cassandra has no %s keyspace" % KEYSPACE)
            schema = {
                "keyspace": keyspace.as_cql_query(),
                "tables": {name: table.as_cql_query()
                           for name, table in keyspace.tables.items()},
            }
            write_json(os.path.join(folder, "schema.json"), schema)
            rows = {}
            tables = sorted(keyspace.tables)
            for i, table in enumerate(tables, 1):
                self.step("exporting Cassandra (%d/%d: %s)"
                          % (i, len(tables), table))
                out = os.path.join(folder, table + ".jsonl.gz")
                statement = SimpleStatement(
                    "SELECT JSON * FROM %s.%s" % (KEYSPACE, table),
                    fetch_size=500)
                count = 0
                with gzip.open(out, "wt", encoding="utf-8") as f:
                    for row in session.execute(statement):
                        f.write(row[0])
                        f.write("\n")
                        count += 1
                private_file(out)
                rows[table] = count
            self.manifest["components"]["cassandra"] = {
                "keyspace": KEYSPACE, "tables": len(tables),
                "rows": sum(rows.values()), "rows_by_table": rows}
        finally:
            cluster.shutdown()

    def export_zookeeper(self):
        self.step("exporting ZooKeeper")
        zk = zk_connect(self.config)
        nodes = []
        try:
            def walk(path):
                for child in sorted(zk.get_children(path)):
                    child_path = path.rstrip("/") + "/" + child
                    if child_path in ZK_SKIP:
                        continue
                    data, stat = zk.get(child_path)
                    if stat.ephemeralOwner:
                        continue  # locks and other per-process nodes
                    nodes.append({
                        "path": child_path,
                        "data": base64.b64encode(data or b"").decode(),
                    })
                    walk(child_path)
            walk("/")
        finally:
            zk.stop()
        out = os.path.join(self.path, "zookeeper.json")
        write_json(out, {"nodes": nodes})
        self.manifest["components"]["zookeeper"] = {"nodes": len(nodes)}

    def export_media(self):
        root = self.config.media_root()
        if not root:
            self.manifest["components"]["media"] = {
                "skipped": "media is not stored on this server "
                           "(media_provider isn't filesystem)"}
            return
        self.step("exporting media")
        out = os.path.join(self.path, "media.tar.gz")
        files = 0
        with tarfile.open(out, "w:gz") as tar:
            if os.path.isdir(root):
                for entry in sorted(os.listdir(root)):
                    tar.add(os.path.join(root, entry), arcname=entry)
                files = sum(len(f) for _, _, f in os.walk(root))
        private_file(out)
        self.manifest["components"]["media"] = {
            "file": "media.tar.gz", "files": files,
            "size": os.path.getsize(out)}

    def export_secrets(self):
        self.step("exporting signing secrets")
        secrets = self.config.signing_secrets()
        write_json(os.path.join(self.path, "secrets.json"), secrets)
        self.manifest["components"]["secrets"] = {"names": sorted(secrets)}
        # for reference: the site's own settings, which restore leaves alone
        update = os.path.join(self.config.root, "development.update")
        if os.path.exists(update):
            out = os.path.join(self.path, "development.update")
            shutil.copyfile(update, out)
            private_file(out)


def take_offline(timeout=300):
    """Stop the web app, let the consumers finish what's queued, then stop
    the rest, so the backup isn't missing queued work."""
    for unit in WEB_UNITS:
        systemctl("stop", unit)
    # Wait until the queues are empty, or stop shrinking: some queues have
    # no reader (event_collector without an events pipeline, consumers set
    # to 0) and never empty. Batch consumers poll rather than subscribe, so
    # RabbitMQ's consumer counts can't tell the two apart.
    deadline = time.time() + timeout
    last, unchanged_since = None, time.time()
    while time.time() < deadline:
        waiting = queued_messages()
        if not waiting:
            break
        if waiting != last:
            last, unchanged_since = waiting, time.time()
        elif time.time() - unchanged_since >= 20:
            log("%d messages are in queues nothing is reading; continuing"
                % waiting)
            break
        log("waiting for %d queued messages" % waiting)
        time.sleep(5)
    else:
        log("queues didn't empty in %ds; continuing" % timeout)
    systemctl("stop", "tippr.target")


def queued_messages():
    if not shutil.which("rabbitmqctl"):
        return 0
    result = subprocess.run(
        ["rabbitmqctl", "-q", "list_queues", "name", "messages"],
        capture_output=True, text=True)
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            total += int(parts[1])
    return total


def zk_connect(config):
    from kazoo.client import KazooClient
    hosts, username, password = config.zookeeper()
    auth = [("digest", "%s:%s" % (username, password))] if username else None
    zk = KazooClient(hosts, timeout=10, auth_data=auth)
    zk.start(timeout=15)
    return zk


###############################################################################
# Restore
###############################################################################

class Restore:
    def __init__(self, config, path):
        self.config = config
        self.path = os.path.abspath(path)
        manifest_path = os.path.join(self.path, "manifest.json")
        try:
            with open(manifest_path) as f:
                self.manifest = json.load(f)
        except (OSError, ValueError) as e:
            raise BackupError("%s isn't a tippr backup: %s" % (path, e))
        if self.manifest.get("format") != FORMAT_VERSION:
            raise BackupError("unsupported backup format %r"
                              % self.manifest.get("format"))
        if self.manifest.get("state") != "done":
            raise BackupError("this backup didn't finish (state: %s)"
                              % self.manifest.get("state"))

    def summary(self):
        m = self.manifest
        comp = m["components"]
        lines = [
            "backup:   %s" % self.path,
            "made:     %s on %s (%s), commit %s" % (
                m["started"], m["source"]["hostname"], m["source"]["domain"],
                m["source"]["commit"]),
            "postgres: %s" % ", ".join(comp.get("postgres", {})),
            "cassandra: %s rows in %s tables" % (
                comp.get("cassandra", {}).get("rows"),
                comp.get("cassandra", {}).get("tables")),
            "zookeeper: %s nodes" % comp.get("zookeeper", {}).get("nodes"),
            "media:    %s" % (comp.get("media", {}).get("files", "skipped")),
        ]
        here = git_commit(self.config)
        if m["source"]["commit"] and here and here != m["source"]["commit"]:
            lines.append("note:     this server runs commit %s; the backup "
                         "came from %s" % (here, m["source"]["commit"]))
        return "\n".join(lines)

    def run(self):
        log("stopping tippr")
        systemctl("stop", "tippr.target")
        try:
            self.restore_postgres()
            self.restore_cassandra()
            self.restore_zookeeper()
            self.restore_media()
            self.restore_secrets()
        except Exception:
            log("RESTORE FAILED; tippr is left stopped because its data is "
                "only partly restored. Fix the problem and run the restore "
                "again (it starts over), or start tippr with tippr-start.")
            raise
        log("flushing memcached")
        for host in self.config.memcache_hosts():
            flush_memcached(host)
        log("starting tippr")
        systemctl("start", "tippr.target")
        log("rebuilding the search index")
        try:
            run(["tippr-run", "-c", "from pylons import app_globals as g; "
                 "g.search.rebuild_index(recreate=True)"],
                user=self.config.user, cwd=self.config.root)
        except (BackupError, OSError) as e:
            log("search index rebuild failed (%s); run it later with: "
                "tippr-run -c 'from pylons import app_globals as g; "
                "g.search.rebuild_index(recreate=True)'" % e)
        log("restore finished")

    def restore_postgres(self):
        targets = self.config.databases()
        for name, info in self.manifest["components"]["postgres"].items():
            if name in targets:
                host, port, user, password = targets[name]
            else:
                # the backup has a database this server doesn't list; put it
                # next to the main one
                host, port, user, password = next(iter(targets.values()))
            log("restoring PostgreSQL database %s on %s" % (name, host))
            env = dict(os.environ, PGPASSWORD=password or "")
            run(["pg_restore", "--clean", "--if-exists", "--no-owner",
                 "--no-privileges", "--exit-on-error", "--single-transaction",
                 "--host", host, "--port", str(port), "--username", user,
                 "--dbname", name, os.path.join(self.path, info["file"])],
                env=env)

    def restore_cassandra(self):
        from cassandra.cluster import Cluster
        from cassandra.concurrent import execute_concurrent_with_args

        folder = os.path.join(self.path, "cassandra")
        with open(os.path.join(folder, "schema.json")) as f:
            schema = json.load(f)
        cluster = Cluster(self.config.cassandra_hosts())
        session = cluster.connect()
        session.default_timeout = 120
        try:
            if KEYSPACE not in cluster.metadata.keyspaces:
                # this server's own keyspace settings win when it has one
                session.execute(schema["keyspace"])
            tables = sorted(schema["tables"])
            for i, table in enumerate(tables, 1):
                log("restoring Cassandra table %d/%d: %s"
                    % (i, len(tables), table))
                cql = schema["tables"][table]
                session.execute(cql.replace(
                    "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
                session.execute("TRUNCATE %s.%s" % (KEYSPACE, table))
                insert = session.prepare(
                    "INSERT INTO %s.%s JSON ?" % (KEYSPACE, table))
                path = os.path.join(folder, table + ".jsonl.gz")
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    batch = []
                    for line in f:
                        batch.append((line.rstrip("\n"),))
                        if len(batch) >= 2000:
                            _insert_all(session, insert, batch,
                                        execute_concurrent_with_args)
                            batch = []
                    if batch:
                        _insert_all(session, insert, batch,
                                    execute_concurrent_with_args)
        finally:
            cluster.shutdown()

    def restore_zookeeper(self):
        from kazoo.security import make_digest_acl
        with open(os.path.join(self.path, "zookeeper.json")) as f:
            nodes = json.load(f)["nodes"]
        log("restoring %d ZooKeeper nodes" % len(nodes))
        _, username, password = self.config.zookeeper()
        acl = [make_digest_acl(username, password, all=True)] \
            if username else None
        from kazoo.exceptions import NoAuthError
        zk = zk_connect(self.config)
        try:
            for node in nodes:
                path, data = node["path"], base64.b64decode(node["data"])
                try:
                    if not zk.exists(path):
                        zk.create(path, data, acl=acl, makepath=True)
                    elif zk.get(path)[0] != data:
                        zk.set(path, data)
                except NoAuthError:
                    log("can't write ZooKeeper node %s (its ACL doesn't "
                        "allow %s); left as it is" % (path, username))
        finally:
            zk.stop()

    def restore_media(self):
        info = self.manifest["components"].get("media", {})
        root = self.config.media_root()
        if "file" not in info:
            return
        if not root:
            log("skipping media: this server doesn't store media locally "
                "(media.tar.gz is in the backup)")
            return
        log("restoring media into %s" % root)
        os.makedirs(root, exist_ok=True)
        with tarfile.open(os.path.join(self.path, info["file"])) as tar:
            tar.extractall(root, filter="data")
        for dirpath, dirnames, filenames in os.walk(root):
            for name in [dirpath] + [os.path.join(dirpath, n)
                                     for n in filenames]:
                os.chown(name, self.config.uid, self.config.gid)

    def restore_secrets(self):
        with open(os.path.join(self.path, "secrets.json")) as f:
            secrets = json.load(f)
        current = self.config.signing_secrets()
        changed = {name: value for name, value in secrets.items()
                   if current.get(name) != value}
        if not changed:
            return
        log("installing the backup's signing secrets")
        # the installer keeps them in secrets.env and writes them into
        # development.secrets, which "make ini" merges into the ini
        applied = set()
        if os.path.exists(SECRETS_ENV):
            applied |= _set_env_values(SECRETS_ENV, {
                "TIPPR_SECRET_" + name.upper(): name
                for name in changed}, changed)
        dev_secrets = os.path.join(self.config.root, "development.secrets")
        if os.path.exists(dev_secrets):
            applied |= _set_ini_values(dev_secrets, changed)
            # make doesn't see development.secrets as a dependency, so
            # remove the ini (as the installer does) to regenerate it
            dev_ini = os.path.join(self.config.root, "development.ini")
            if os.path.exists(dev_ini):
                os.remove(dev_ini)
            run(["make", "ini"], user=self.config.user, cwd=self.config.root,
                env=dict(os.environ, PATH=os.path.dirname(sys.executable)
                         + ":" + os.environ.get("PATH", "")))
            if (os.path.exists(dev_ini)
                    and not os.path.islink(self.config.ini_path)
                    and os.path.basename(self.config.ini_path) == "run.ini"):
                shutil.copyfile(dev_ini, self.config.ini_path)
        by_hand = sorted(set(changed) - applied)
        if by_hand:
            log("these settings differ from the backup and aren't managed "
                "by the installer; copy them from the backup's secrets.json "
                "into your ini if you need them: %s" % ", ".join(by_hand))


def _insert_all(session, insert, rows, execute_concurrent_with_args):
    results = execute_concurrent_with_args(
        session, insert, rows, concurrency=64, raise_on_first_error=True)
    for ok, result in results:
        if not ok:
            raise BackupError("Cassandra insert failed: %s" % result)


def _set_env_values(path, names, values):
    """Update the KEY=value lines already in the file (names maps each env
    key to a secret name). Returns the secret names updated."""
    with open(path) as f:
        lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0]
        if key in names:
            lines[i] = "%s=%s" % (key, values[names[key]])
            done.add(names[key])
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return done


def _set_ini_values(path, values):
    """Replace "name = value" lines (any section), unescaped like the
    installer writes the secrets. Returns the names updated."""
    with open(path) as f:
        lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in values:
            lines[i] = "%s = %s" % (key, values[key])
            done.add(key)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return done


def flush_memcached(hostport):
    host, _, port = hostport.partition(":")
    try:
        with socket.create_connection((host, int(port or 11211)),
                                      timeout=5) as s:
            s.sendall(b"flush_all\r\n")
            s.recv(64)
    except OSError as e:
        log("couldn't flush memcached at %s: %s" % (hostport, e))


###############################################################################
# Import from another server
###############################################################################

class Import:
    """Copy a backup from another tippr server's transfer API
    (r2.controllers.backup_transfer), CHUNK_SIZE bytes per request so each
    request is short and an interrupted copy resumes where it stopped."""

    def __init__(self, config, url, key, name=None, fresh=False,
                 offline=False, verify_tls=True):
        import requests
        self.config = config
        self.url = url.strip().rstrip("/")
        if not re.match(r"^https?://", self.url):
            self.url = "https://" + self.url
        self.name = name
        self.fresh = fresh
        self.offline = offline
        self.http = requests.Session()
        self.http.headers["Authorization"] = "Bearer " + key.strip()
        self.http.verify = verify_tls

    def call(self, method, path, **kw):
        import requests
        try:
            resp = self.http.request(
                method, self.url + "/backup_transfer/" + path, timeout=120,
                **kw)
        except requests.RequestException as e:
            raise BackupError("can't reach %s: %s" % (self.url, e))
        if resp.status_code == 403:
            raise BackupError("%s refused the transfer key (wrong, revoked "
                              "or expired)" % self.url)
        if resp.status_code != 200:
            raise BackupError("%s answered %s for %s"
                              % (self.url, resp.status_code, path))
        return resp

    def backups(self):
        return self.call("GET", "list").json()["backups"]

    def run(self):
        if self.fresh:
            self.name = self.request_export()
        if not self.name:
            done = [b for b in self.backups() if b.get("state") == "done"]
            if not done:
                raise BackupError("%s has no finished backups" % self.url)
            self.name = done[0]["name"]  # newest first
        if not NAME_RE.match(self.name):
            raise BackupError("bad backup name %r" % self.name)

        dest = os.path.join(self.config.backup_dir, self.name)
        if os.path.exists(os.path.join(dest, "manifest.json")):
            log("%s is already here" % self.name)
            return dest
        manifest = self.call("GET", "manifest/" + self.name).json()
        if manifest.get("state") != "done" or "files" not in manifest:
            raise BackupError("%s on %s isn't a finished backup"
                              % (self.name, self.url))

        partial = dest + ".partial"
        private_dir(self.config.backup_dir)
        private_dir(partial)
        files = manifest["files"]
        total = sum(f["size"] for f in files)
        copied = 0
        for i, info in enumerate(files, 1):
            rel = info["path"]
            if os.path.isabs(rel) or ".." in rel.split("/"):
                raise BackupError("bad file name %r" % rel)
            log("copying %d/%d: %s (%s; %d%% of %s done)" % (
                i, len(files), rel, human_size(info["size"]),
                100 * copied // max(total, 1), human_size(total)))
            self.fetch_file(info, os.path.join(partial, rel))
            copied += info["size"]

        manifest["imported_from"] = self.url
        manifest["imported"] = now_iso()
        write_json(os.path.join(partial, "manifest.json"), manifest)
        os.rename(partial, dest)
        log("copied %s from %s" % (self.name, self.url))
        return dest

    def fetch_file(self, info, out):
        private_dir(os.path.dirname(out))
        have = os.path.getsize(out) if os.path.exists(out) else 0
        if have > info["size"]:
            os.remove(out)
            have = 0
        with open(out, "ab") as f:
            while have < info["size"]:
                resp = self.call("GET", "file/" + self.name, params={
                    "path": info["path"], "offset": have})
                if not resp.content:
                    raise BackupError("%s stopped sending %s"
                                      % (self.url, info["path"]))
                f.write(resp.content)
                have += len(resp.content)
        private_file(out)
        if file_sha256(out) != info["sha256"]:
            os.remove(out)
            raise BackupError("%s arrived damaged (checksum mismatch); run "
                              "the import again" % info["path"])

    def request_export(self):
        """Ask the other server for a new backup and wait for it."""
        before = {b["name"] for b in self.backups()}
        log("asking %s for a new%s backup" % (
            self.url, " offline" if self.offline else ""))
        self.call("POST", "export", data={"offline": int(self.offline)})
        deadline = time.time() + 6 * 3600
        while time.time() < deadline:
            time.sleep(10)
            try:
                backups = self.backups()
            except BackupError:
                if self.offline:
                    continue  # its web app is stopped while it exports
                raise
            new = [b for b in backups if b["name"] not in before]
            if new:
                backup = new[0]
                if backup.get("state") == "done":
                    return backup["name"]
                if backup.get("state") == "failed":
                    raise BackupError("the backup on %s failed: %s"
                                      % (self.url, backup.get("error")))
                log("waiting for %s: %s" % (backup["name"],
                                             backup.get("step")))
        raise BackupError("gave up waiting for %s's backup" % self.url)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0


###############################################################################
# Listing and the /admin/backups queue
###############################################################################

def list_backups(config):
    root = config.backup_dir
    result = []
    if not os.path.isdir(root):
        return result
    for name in sorted(os.listdir(root), reverse=True):
        if not NAME_RE.match(name):
            continue
        try:
            with open(os.path.join(root, name, "manifest.json")) as f:
                result.append(json.load(f))
        except (OSError, ValueError):
            result.append({"name": name, "state": "unknown"})
    return result


def process_queue(config):
    """Run the requests /admin/backups wrote (the web app can't run pg_dump
    as root or stop services itself)."""
    global JOB
    if not os.path.isdir(QUEUE_DIR):
        return
    for entry in sorted(os.listdir(QUEUE_DIR)):
        if not entry.endswith(".json"):
            continue
        path = os.path.join(QUEUE_DIR, entry)
        try:
            with open(path) as f:
                request = json.load(f)
        except (OSError, ValueError):
            request = {}
        os.remove(path)  # taken; the outcome goes to job.json
        JOB = Job(config.backup_dir, request)
        log("%s requested by %s" % (request.get("action"),
                                    request.get("requested_by")))
        try:
            run_request(config, request)
        except Exception as e:
            log("FAILED: %s" % e)
            JOB.finish(error=str(e))
        else:
            JOB.finish()
        JOB = None


def run_request(config, request):
    action = request.get("action")
    name = request.get("name") or ""
    if action == "export":
        Export(config, offline=bool(request.get("offline")),
               requested_by=request.get("requested_by")).run()
    elif action == "delete":
        target = os.path.join(config.backup_dir, name)
        if not (NAME_RE.match(name) and os.path.isdir(target)):
            raise BackupError("no backup %r" % name)
        shutil.rmtree(target)
        log("deleted %s" % name)
    elif action == "restore":
        if not NAME_RE.match(name):
            raise BackupError("no backup %r" % name)
        Restore(config, os.path.join(config.backup_dir, name)).run()
    elif action == "import":
        path = Import(config, request["url"], request["key"],
                      name=name or None, fresh=bool(request.get("fresh")),
                      offline=bool(request.get("offline")),
                      verify_tls=request.get("verify_tls", True)).run()
        if request.get("restore"):
            Restore(config, path).run()
    else:
        raise BackupError("unknown request %r" % action)


def confirm_and_restore(config, path, yes=False):
    restore = Restore(config, path)
    print(restore.summary())
    print("\nThis REPLACES all of this site's data (%s) with the backup.\n"
          "This server's passwords are kept; its signing secrets are "
          "replaced." % config.get("domain"))
    if not yes:
        answer = input("Type 'restore' to continue: ")
        if answer.strip() != "restore":
            print("cancelled")
            return 1
    restore.run()
    return 0


###############################################################################

def main():
    parser = argparse.ArgumentParser(
        description="Export a tippr site to a folder, or restore one.")
    parser.add_argument("--ini", default=os.environ.get("TIPPR_INI"),
                        required="TIPPR_INI" not in os.environ,
                        help="the site's ini (default: $TIPPR_INI)")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write a backup to backup_dir")
    export.add_argument("--offline", action="store_true",
                        help="stop the site while exporting (a consistent "
                             "copy; use this when moving servers)")
    export.add_argument("--dest", help="folder to write the backup into "
                                       "(default: backup_dir from the ini)")
    sub.add_parser("list", help="list the backups in backup_dir")
    restore = sub.add_parser(
        "restore", help="replace this site's data with a backup")
    restore.add_argument("path", help="the backup folder")
    restore.add_argument("--yes", action="store_true",
                         help="don't ask for confirmation")
    imp = sub.add_parser(
        "import", help="copy a backup from another tippr server")
    imp.add_argument("url", help="the other server, e.g. https://old.example")
    imp.add_argument("--key", required=True,
                     help="a transfer key made on its /admin/backups")
    imp.add_argument("--name", help="which backup (default: its newest)")
    imp.add_argument("--fresh", action="store_true",
                     help="have it make a new backup first")
    imp.add_argument("--offline", action="store_true",
                     help="with --fresh: stop that site while it exports")
    imp.add_argument("--insecure", action="store_true",
                     help="don't check its TLS certificate (self-signed)")
    imp.add_argument("--restore", action="store_true",
                     help="restore the backup here once copied")
    imp.add_argument("--yes", action="store_true",
                     help="with --restore: don't ask for confirmation")
    sub.add_parser("process-queue", help=argparse.SUPPRESS)
    args = parser.parse_args()

    config = Config(args.ini)
    global OWNER
    OWNER = (config.uid, config.gid)

    if args.command == "list":
        for m in list_backups(config):
            print("%-32s %-8s %s" % (m.get("name"), m.get("state"),
                                     m.get("started", "")))
        return 0

    if os.geteuid() != 0:
        print("run tippr-backup as root (sudo)", file=sys.stderr)
        return 1

    private_dir(config.backup_dir)
    lock = open(os.path.join(config.backup_dir, LOCK_FILE), "w")
    if args.command == "process-queue":
        # wait out a backup run from the command line; returning instead
        # would leave the request there and systemd would retrigger at once
        fcntl.flock(lock, fcntl.LOCK_EX)
    else:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another backup or restore is running", file=sys.stderr)
            return 1

    try:
        if args.command == "export":
            Export(config, offline=args.offline, dest=args.dest).run()
        elif args.command == "process-queue":
            process_queue(config)
        elif args.command == "restore":
            return confirm_and_restore(config, args.path, args.yes)
        elif args.command == "import":
            path = Import(config, args.url, args.key, name=args.name,
                          fresh=args.fresh, offline=args.offline,
                          verify_tls=not args.insecure).run()
            if args.restore:
                return confirm_and_restore(config, path, args.yes)
            print("restore it with: tippr-backup restore %s" % path)
    except BackupError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
