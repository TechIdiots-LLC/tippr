#!/usr/bin/env python3
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

"""The tippr image's entrypoint: configure from the environment, then run one
role. docker/docker-compose.yml runs one container per role.

    setup         one-shot: wait for the data stores, create the Cassandra
                  keyspace, the admin account, starter vaults and policy
                  pages, and build the search index
    web           the web app (gunicorn, port 8001)
    consumers     the queue consumers (TIPPR_CONSUMERS sets how many each)
    jobs          the scheduled jobs (the systemd timers' schedules)
    websockets    live updates (port 9001)
    activity      "users here now" counts (thrift, port 9002)
    geoip         country lookups for visitors' IP addresses (port 5000)
    run ARGS      paster run, like tippr-run (e.g. run -c 'print(1)')
    shell         an interactive shell with the app loaded
    config        only write the configuration (and print where it is)

Configuration comes from environment variables (see docker/.env.example),
the signing secrets from /config/secrets.env, which the first container to
start generates and every container shares, and optional extra ini settings
from /config/tippr.update. Settings saved on admin pages (/admin/site,
/admin/email, ...) are kept in ZooKeeper as usual.
"""

import base64
import configparser
import datetime
import fcntl
import os
import re
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import time

HOME = "/opt/tippr"
SRC = HOME + "/src"
R2 = SRC + "/tippr/r2"
VENV = HOME + "/venv"
SYSTEMD = SRC + "/tippr/systemd"
CONFIG_DIR = os.environ.get("TIPPR_CONFIG_DIR", "/config")
INI = os.environ.get("TIPPR_INI", R2 + "/run.ini")

SIGNING_SECRETS = (
    "SECRET", "FEEDSECRET", "ADMINSECRET", "WEBSOCKET", "WEBSOCKET_ADMIN",
    "MEDIA_EMBED", "ACTION_NAME", "EMAIL_NOTIFICATIONS", "CACHE_POISONING",
    "ADSERVER_CLICK_URL_SECRET", "MODMAIL_EMAIL_SECRET",
    "REQUEST_SIGNATURE_SECRET", "TRACKING_SECRET",
)

# queue -> processes, as install/tippr.sh sets them; TIPPR_CONSUMERS
# ("vote_link_q=2,automoderator_q=1") overrides
DEFAULT_CONSUMERS = {
    "del_account_q": 1, "scraper_q": 1, "markread_q": 1,
    "commentstree_q": 1, "newcomments_q": 1, "vote_link_q": 1,
    "vote_comment_q": 1, "automoderator_q": 0, "butler_q": 1,
    "author_query_q": 1, "vault_query_q": 1, "domain_query_q": 1,
    "privacy_export_q": 1, "search_q": 1,
}

# the timers install/tippr.sh enables; TIPPR_JOBS (comma separated timer
# names without .timer) overrides
DEFAULT_JOBS = (
    "tippr-job-update_vault_names", "tippr-job-update_tipprs",
    "tippr-job-update_promos", "tippr-job-clean_up_hardcache",
    "tippr-job-broken_things", "tippr-job-rising", "tippr-job-trylater",
    "tippr-job-update_popular_vaults", "tippr-job-update_trending_vaults",
    "tippr-job-compute_time_listings@link",
    "tippr-job-compute_time_listings@comment", "tippr-job-email",
    "tippr-job-update_gold_users", "tippr-job-feeds",
    "tippr-job-subscribers", "tippr-job-update_promo_metrics",
)


def log(message):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[%s] %s" % (stamp, message), flush=True)


def env(name, default=""):
    return os.environ.get(name, default).strip()


def require(name):
    value = env(name)
    if not value:
        sys.exit("tippr: set %s (see docker/.env.example)" % name)
    return value


###############################################################################
# Configuration
###############################################################################

def load_secrets():
    """Signing secrets and the admin password: generated once into
    /config/secrets.env, shared by every container. Values given in the
    environment (TIPPR_SECRET_<NAME>, TIPPR_ADMIN_PASSWORD) win."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = os.path.join(CONFIG_DIR, "secrets.env")
    with open(os.path.join(CONFIG_DIR, ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        values = {}
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    key, sep, value = line.strip().partition("=")
                    if sep and not key.startswith("#"):
                        values[key] = value
        changed = False
        wanted = {"TIPPR_SECRET_" + n: lambda: base64.b64encode(
                      secrets.token_bytes(32)).decode() for n in SIGNING_SECRETS}
        wanted["TIPPR_ADMIN_PASSWORD"] = lambda: secrets.token_urlsafe(18)
        for key, make in wanted.items():
            if env(key):
                if values.get(key) != env(key):
                    values[key], changed = env(key), True
            elif not values.get(key):
                values[key], changed = make(), True
        if changed:
            tmp = path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write("# generated by the tippr image; keep it with your "
                        "backups\n")
                for key in sorted(values):
                    f.write("%s=%s\n" % (key, values[key]))
            os.replace(tmp, path)
    return values


def example_db_keys():
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    parser.read(R2 + "/example.ini")
    return [k for k in parser.defaults() if re.fullmatch(r"\w+_db", k)
            and k not in ("type_db", "rel_type_db", "hardcache_db")]


def ini_value(value):
    return value.replace("%", "%%")


def write_config():
    """Write /config/docker.update and the services' configs, and merge them
    into run.ini."""
    domain = require("TIPPR_DOMAIN")
    values = load_secrets()
    production = env("TIPPR_ENVIRONMENT", "production") == "production"
    db_host = env("TIPPR_DB_HOST", "postgres")
    db_name = env("TIPPR_DB_NAME", "tippr")
    memcached = env("TIPPR_MEMCACHED", "memcached:11211")
    amqp_password = require("TIPPR_AMQP_PASSWORD")
    zk_password = env("TIPPR_ZOOKEEPER_PASSWORD") or values["TIPPR_SECRET_SECRET"][:24]

    lines = [
        "# generated by the tippr image from the environment; edit",
        "# /config/tippr.update for other settings",
        "[DEFAULT]",
        "domain = " + domain,
        "oauth_domain = " + domain,
        "https_endpoint = https://" + domain,
        "payment_domain = https://pay.%s/" % domain,
        "ad_domain = https://" + domain,
        "trust_local_proxies = true",
        "db_user = " + env("TIPPR_DB_USER", "tippr"),
        "db_pass = " + ini_value(require("TIPPR_DB_PASSWORD")),
        "db_port = " + env("TIPPR_DB_PORT", "5432"),
        "cassandra_seeds = " + env("TIPPR_CASSANDRA_HOSTS", "cassandra"),
        "zookeeper_connection_string = " + env("TIPPR_ZOOKEEPER", "zookeeper:2181"),
        "zookeeper_username = tippr",
        "zookeeper_password = " + ini_value(zk_password),
        "amqp_host = " + env("TIPPR_AMQP_HOST", "rabbitmq:5672"),
        "amqp_user = " + env("TIPPR_AMQP_USER", "tippr"),
        "amqp_pass = " + ini_value(amqp_password),
        "amqp_virtual_host = /",
        "lockcaches = " + memcached,
        "permacache_memcaches = " + memcached,
        "hardcache_memcaches = " + memcached,
        "mcrouter_addr = " + memcached,
        "search_provider = opensearch",
        "opensearch_url = " + env("TIPPR_OPENSEARCH_URL", "http://opensearch:9200"),
        "activity_endpoint = " + env("TIPPR_ACTIVITY", "activity:9002"),
        "geoip_location = " + env("TIPPR_GEOIP", "http://geoip:5000"),
        "media_provider = filesystem",
        "media_fs_root = /srv/www/media",
        "media_fs_base_url_http = https://%s/media/" % domain,
        "tracking_secret = " + values["TIPPR_SECRET_TRACKING_SECRET"],
        "plugins = ",
    ]
    for key in example_db_keys():
        lines.append("%s = %s, %s, *, *, *, *, *" % (key, db_name, db_host))
    for name, key in (("TIPPR_SITE_NAME", "site_name"),
                      ("TIPPR_SITE_DESCRIPTION", "short_description"),
                      ("TIPPR_CONTACT_EMAIL", "contact_email")):
        if env(name):
            lines.append("%s = %s" % (key, ini_value(env(name))))
    if production:
        lines += ["debug = false", "template_debug = false",
                  "reload_templates = false", "uncompressedJS = false",
                  "sqlprinting = false", "disable_captcha = false",
                  "disable_ratelimit = false",
                  "disable_require_admin_otp = false"]
    else:
        lines += ["debug = true", "reload_templates = true",
                  "uncompressedJS = false", "disable_captcha = true",
                  "disable_ratelimit = true",
                  "disable_require_admin_otp = true"]
    lines.append("")
    lines.append("[live_config]")
    lines.append("employees = %s:admin" % env("TIPPR_ADMIN_USER", "tippr"))
    lines.append("")
    lines.append("[secrets]")
    for name in SIGNING_SECRETS:
        if name != "TRACKING_SECRET":
            ini_name = {"SECRET": "SECRET", "FEEDSECRET": "FEEDSECRET",
                        "ADMINSECRET": "ADMINSECRET"}.get(name, name.lower())
            lines.append("%s = %s" % (ini_name, values["TIPPR_SECRET_" + name]))

    update = os.path.join(CONFIG_DIR, "docker.update")
    with open(update + ".tmp", "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(update + ".tmp", 0o600)
    os.replace(update + ".tmp", update)

    sources = [R2 + "/example.ini", update]
    extra = os.path.join(CONFIG_DIR, "tippr.update")
    if os.path.exists(extra):
        sources.append(extra)
    merged = subprocess.run([VENV + "/bin/python", R2 + "/updateini.py"]
                            + sources, cwd=R2, capture_output=True, text=True)
    if merged.returncode != 0:
        sys.exit("tippr: couldn't build the ini:\n" + merged.stderr)
    with open(INI + ".tmp", "w") as f:
        f.write(merged.stdout)
    os.chmod(INI + ".tmp", 0o600)
    os.replace(INI + ".tmp", INI)

    write_service_configs(values, amqp_password)
    return values


def write_service_configs(values, amqp_password):
    amqp_host = env("TIPPR_AMQP_HOST", "rabbitmq:5672")
    with open(SRC + "/websockets/tippr.ini", "w") as f:
        f.write("""[app:main]
factory = reddit_service_websockets.app:make_app
amqp.endpoint = {amqp}
amqp.vhost = /
amqp.username = {user}
amqp.password = {password}
amqp.exchange.broadcast = sutro
amqp.exchange.status = tippr_exchange
amqp.send_status_messages = false
web.ping_interval = 45
web.admin_auth = {admin}
web.conn_shed_rate = 5
metrics.namespace = websockets
metrics.endpoint =
metrics.enabled = false
secrets.path = tippr_secrets.json
sentry.dsn =
sentry.environment = production

[server:main]
factory = baseplate.server.wsgi
handler = reddit_service_websockets.socketserver:WebSocketHandler
""".format(amqp=amqp_host, user=env("TIPPR_AMQP_USER", "tippr"),
           password=ini_value(amqp_password),
           admin=values["TIPPR_SECRET_WEBSOCKET_ADMIN"]))
    with open(SRC + "/websockets/tippr_secrets.json", "w") as f:
        f.write("""{"secrets": {"secret/websockets/authorization_key": {
    "type": "versioned", "current": "%s", "encoding": "base64"}},
 "vault_token": ""}
""" % values["TIPPR_SECRET_WEBSOCKET"])
    example = SRC + "/activity/example.ini"
    if os.path.exists(example):
        with open(example) as f:
            text = f.read()
        text = text.replace("[app:main]", "[app:main]\nmetrics.enabled = false", 1)
        text = re.sub(r"(?m)^redis\.url = .*$",
                      "redis.url = " + env("TIPPR_REDIS_URL", "redis://redis:6379/0"),
                      text)
        with open(SRC + "/activity/tippr.ini", "w") as f:
            f.write(text)


###############################################################################
# Roles
###############################################################################

def paster_run(*args):
    return [VENV + "/bin/paster", "--plugin=r2", "run", INI] + list(args)


def wait_for(name, host, port, timeout=600):
    deadline = time.time() + timeout
    while True:
        try:
            with socket.create_connection((host, int(port)), timeout=5):
                return
        except OSError:
            if time.time() > deadline:
                sys.exit("tippr: %s (%s:%s) didn't come up" % (name, host, port))
            log("waiting for %s (%s:%s)" % (name, host, port))
            time.sleep(5)


def split_hostport(value, default_port):
    host, _, port = value.partition(":")
    return host, port or default_port


def wait_for_services():
    wait_for("PostgreSQL", env("TIPPR_DB_HOST", "postgres"),
             env("TIPPR_DB_PORT", "5432"))
    for host in env("TIPPR_CASSANDRA_HOSTS", "cassandra").split(","):
        wait_for("Cassandra", host.strip().split(":")[0], 9042)
    wait_for("ZooKeeper", *split_hostport(env("TIPPR_ZOOKEEPER", "zookeeper:2181"), 2181))
    wait_for("RabbitMQ", *split_hostport(env("TIPPR_AMQP_HOST", "rabbitmq:5672"), 5672))
    wait_for("memcached", *split_hostport(env("TIPPR_MEMCACHED", "memcached:11211"), 11211))


def setup(values):
    """One-shot setup; safe to run again (each step skips what exists)."""
    wait_for_services()
    log("loading r2's SQL functions into PostgreSQL")
    import psycopg2
    conn = psycopg2.connect(host=env("TIPPR_DB_HOST", "postgres"),
                            port=env("TIPPR_DB_PORT", "5432"),
                            dbname=env("TIPPR_DB_NAME", "tippr"),
                            user=env("TIPPR_DB_USER", "tippr"),
                            password=require("TIPPR_DB_PASSWORD"))
    with conn, conn.cursor() as cur:
        with open(SRC + "/tippr/install/postgres_functions.sql") as f:
            cur.execute(f.read())
    conn.close()

    log("creating the Cassandra keyspace")
    from cassandra.cluster import Cluster
    hosts = [h.strip().split(":")[0]
             for h in env("TIPPR_CASSANDRA_HOSTS", "cassandra").split(",")]
    replication = env("TIPPR_CASSANDRA_REPLICATION", "1")
    for attempt in range(30):
        try:
            cluster = Cluster(hosts)
            session = cluster.connect()
            break
        except Exception as e:  # Cassandra accepts connections before CQL
            log("Cassandra isn't ready yet (%s)" % e)
            time.sleep(10)
    else:
        sys.exit("tippr: couldn't connect to Cassandra")
    session.execute(
        "CREATE KEYSPACE IF NOT EXISTS tippr WITH replication = "
        "{'class': 'SimpleStrategy', 'replication_factor': '%s'}" % replication)
    session.execute("CREATE TABLE IF NOT EXISTS tippr.permacache "
                    "(key text PRIMARY KEY, columns map<text, blob>)")
    cluster.shutdown()

    child_env = dict(os.environ, TIPPR_ADMIN_PASSWORD=values["TIPPR_ADMIN_PASSWORD"],
                     TIPPR_ADMIN_USER=env("TIPPR_ADMIN_USER", "tippr"))
    for script in ("create_default_user.py", "init_policy_wiki_pages.py",
                   "create_default_awards.py",
                   "create_default_vaults.py"):
        log("running " + script)
        subprocess.run(paster_run(SRC + "/tippr/scripts/" + script),
                       cwd=R2, env=child_env, check=True)
    log("building the search index")
    subprocess.run(paster_run("-c", "from pylons import app_globals as g; "
                              "g.search.rebuild_index()"), cwd=R2, check=False)
    log("setup finished. Log in as %s; the password is TIPPR_ADMIN_PASSWORD "
        "in %s/secrets.env" % (child_env["TIPPR_ADMIN_USER"], CONFIG_DIR))


def web():
    workers = env("TIPPR_WEB_WORKERS") or str(min(os.cpu_count() or 2, 8))
    os.execv(VENV + "/bin/gunicorn", [
        "gunicorn", "--paste", INI, "--bind", "0.0.0.0:8001",
        "--workers", workers, "--timeout", "60", "--graceful-timeout", "30",
        "--forwarded-allow-ips", "*"])


def systemd_exec(unit, instance=""):
    """A systemd unit's ExecStart, with the installer's placeholders filled
    in, as an argument list."""
    with open(os.path.join(SYSTEMD, unit)) as f:
        text = f.read()
    match = re.search(r"(?m)^ExecStart=(.*)$", text)
    command = match.group(1)
    for placeholder, value in (("@TIPPR_VENV@", VENV), ("@TIPPR_SRC@", SRC),
                               ("@TIPPR_ROOT@", R2), ("@TIPPR_INI@", INI),
                               ("${TIPPR_INI}", INI), ("%i", instance)):
        command = command.replace(placeholder, value)
    # the unit's own Environment=NAME=VALUE settings (e.g. ${type})
    for name, value in re.findall(r"(?m)^Environment=(\w+)=(.*)$", text):
        command = command.replace("${%s}" % name, value)
    return shlex.split(command)


def consumer_counts():
    counts = dict(DEFAULT_CONSUMERS)
    for item in env("TIPPR_CONSUMERS").split(","):
        queue, sep, count = item.strip().partition("=")
        if sep and count.strip().isdigit():
            counts[queue.strip()] = int(count)
    return counts


class Supervisor:
    """Runs a set of commands, restarting any that exit, until stopped."""

    def __init__(self):
        self.children = {}
        self.stopping = False
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

    def stop(self, *args):
        self.stopping = True
        for proc in self.children.values():
            if proc.poll() is None:
                proc.terminate()

    def start(self, name, argv):
        log("starting " + name)
        self.children[name] = subprocess.Popen(argv, cwd=R2)
        self.children[name].argv = argv

    def run(self, extra=None):
        while not self.stopping:
            for name, proc in list(self.children.items()):
                if proc.poll() is not None and not self.stopping:
                    log("%s exited with %s; restarting in 5s"
                        % (name, proc.returncode))
                    time.sleep(5)
                    self.start(name, proc.argv)
            if extra:
                extra()
            time.sleep(1)
        for proc in self.children.values():
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()


def consumers():
    sup = Supervisor()
    for queue, count in sorted(consumer_counts().items()):
        unit = "tippr-consumer-%s@.service" % queue
        if count <= 0 or not os.path.exists(os.path.join(SYSTEMD, unit)):
            continue
        for i in range(1, count + 1):
            sup.start("%s@%d" % (queue, i), systemd_exec(unit, str(i)))
    sup.run()


def next_run(calendar, now):
    """The next time a systemd OnCalendar expression (the forms tippr's
    timers use) fires after now."""
    calendar = calendar.strip()
    if calendar == "hourly":
        return now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    if calendar == "daily":
        return (now.replace(hour=0, minute=0, second=0, microsecond=0)
                + datetime.timedelta(days=1))
    match = re.fullmatch(r"\*:(\d+)(?:/(\d+))?", calendar)
    if match:
        start = int(match.group(1))
        step = match.group(2)
        if step is None:
            t = now.replace(minute=start, second=0, microsecond=0)
            return t if t > now else t + datetime.timedelta(hours=1)

        step = int(step)
        t = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        while (t.minute - start) % step:
            t += datetime.timedelta(minutes=1)
        return t
    match = re.fullmatch(r"\*-\*-\* (\d\d):(\d\d)(?::(\d\d))?", calendar)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3)) if match.group(3) is not None else 0
        t = now.replace(hour=hour, minute=minute, second=second,
                        microsecond=0)
        return t if t > now else t + datetime.timedelta(days=1)
    raise ValueError("unsupported OnCalendar %r" % calendar)


def jobs():
    names = [j.strip() for j in env("TIPPR_JOBS").split(",") if j.strip()] \
        or list(DEFAULT_JOBS)
    schedule = []
    for name in names:
        base, _, instance = name.partition("@")
        timer = (base + "@.timer") if instance else (name + ".timer")
        service = (base + "@.service") if instance else (name + ".service")
        with open(os.path.join(SYSTEMD, timer)) as f:
            calendar = re.search(r"(?m)^OnCalendar=(.*)$", f.read()).group(1)
        argv = systemd_exec(service, instance)
        schedule.append({"name": name, "calendar": calendar, "argv": argv,
                         "next": next_run(calendar, datetime.datetime.now()),
                         "proc": None})
        log("%s: %s" % (name, calendar))
    stopping = []

    def stop(*args):
        stopping.append(True)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        now = datetime.datetime.now()
        for job in schedule:
            if job["next"] <= now:
                running = job["proc"] is not None and job["proc"].poll() is None
                if running:
                    log("%s is still running; skipping this run" % job["name"])
                else:
                    job["proc"] = subprocess.Popen(job["argv"], cwd=R2)
                job["next"] = next_run(job["calendar"], now)
        time.sleep(1)
    for job in schedule:
        if job["proc"] is not None and job["proc"].poll() is None:
            job["proc"].terminate()


def baseplate_serve(service, port):
    ini = "%s/%s/tippr.ini" % (SRC, service)
    os.makedirs(os.environ.get("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus"),
                exist_ok=True)
    os.chdir(os.path.dirname(ini))
    os.execv(VENV + "/bin/baseplate-serve",
             ["baseplate-serve", "--bind", "0.0.0.0:%d" % port, ini])


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "web"
    args = sys.argv[2:]
    if role in ("-h", "--help", "help"):
        print(__doc__)
        return
    values = write_config()
    if role == "config":
        print("wrote %s and %s/docker.update" % (INI, CONFIG_DIR))
    elif role == "setup":
        setup(values)
    elif role == "web":
        web()
    elif role == "consumers":
        consumers()
    elif role == "jobs":
        jobs()
    elif role == "websockets":
        baseplate_serve("websockets", 9001)
    elif role == "activity":
        baseplate_serve("activity", 9002)
    elif role == "geoip":
        os.execv(VENV + "/bin/gunicorn", [
            "gunicorn", "--chdir", SRC + "/tippr/scripts", "--bind",
            "0.0.0.0:5000", "--workers", "1", "--limit-request-line", "8190",
            "geoip_service:application"])
    elif role == "run":
        os.chdir(R2)
        os.execv(VENV + "/bin/paster", paster_run(*args))
    elif role == "shell":
        os.chdir(R2)
        os.execv(VENV + "/bin/paster", [VENV + "/bin/paster", "shell", INI])
    else:
        sys.exit("tippr: unknown role %r (try: help)" % role)


if __name__ == "__main__":
    main()
