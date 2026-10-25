# A site on several servers

By default one server (or one Proxmox container) runs the whole site. The
installer can also split it in two:

| role | runs | how many |
|---|---|---|
| **backend** | PostgreSQL, Cassandra, RabbitMQ, ZooKeeper, OpenSearch, memcached, the activity service ("here now" counts), the queue processors and the scheduled jobs | one |
| **frontend** | nginx, the web app, live comments (websockets), geoip | one or more, on any servers |

Frontends keep nothing of their own, so you can add one, rebuild one or
take one away without losing anything; a load balancer (e.g. HAProxy on
OPNsense) spreads visitors over them. Every frontend uses the backend's
databases, queue and cache.

The role is the installer setting `TIPPR_ROLE` (`all`, the default,
`backend` or `frontend`). Like the other settings it's remembered, so
updates keep each server's role.

## Before you start

- **Media in object storage.** Thumbnails are made on the backend and
  served by the frontends, so media can't live on one server's disk. Set
  up S3-compatible storage (Garage, MinIO or Amazon S3) as in
  [STORAGE.md](STORAGE.md) and give the backend the `TIPPR_MEDIA_STORAGE=s3`
  settings; the frontends get them from the backend. The installer refuses
  a split without it.
- **A private network** between the servers, and a firewall. The backend
  takes the frontends' connections on ports 5432 (PostgreSQL), 9042
  (Cassandra), 5672 (RabbitMQ), 2181 (ZooKeeper), 9200 (OpenSearch), 11211
  (memcached) and 9002 (activity). Cassandra, OpenSearch, memcached and the
  activity service have **no password**: only the frontends may reach those
  ports. Use the Proxmox firewall on the backend container (allow those
  ports from the frontends' range, drop the rest), or `TIPPR_FIREWALL=1`,
  which sets up ufw with the same rules.

## The backend

Install (or first-boot a container) with:

```bash
TIPPR_ROLE=backend
TIPPR_BACKEND_LISTEN=172.16.1.20       # its address the frontends reach it on
TIPPR_FRONTEND_ALLOW=172.16.1.0/24     # the frontends' address range
TIPPR_MEDIA_STORAGE=s3                 # and the other TIPPR_S3_* settings
```

On Proxmox, put these in the container's `/etc/tippr/firstboot.env` before
its first start ([PROXMOX.md](PROXMOX.md)); on another server, pass them to
`install-tippr.sh`. The backend serves no pages: its own nginx and web app
are off.

It writes **`/etc/tippr/cluster.env`**: its address, the database, queue
and ZooKeeper passwords, the signing secrets (logins and signed links have
to check on every frontend) and the settings every server must agree on
(domain, media storage, AutoModerator). It's as sensitive as the secrets
file: root's, mode 600.

## The frontends

For each frontend:

1. Copy the backend's `/etc/tippr/cluster.env` to the same path on the
   frontend (root's, mode 600). On Proxmox, before its first start:

   ```bash
   umask 077
   pct exec 220 -- cat /etc/tippr/cluster.env > /root/cluster.env   # backend
   pct mount 221
   install -m 600 /root/cluster.env /var/lib/lxc/221/rootfs/etc/tippr/cluster.env
   pct unmount 221
   rm /root/cluster.env
   ```

2. Install (or first-boot it) with:

   ```bash
   TIPPR_ROLE=frontend
   TIPPR_EXTERNAL_PROXY=172.16.1.1   # the load balancer, if it does TLS
   ```

   The domain, the backend's address and everything shared come from
   `cluster.env`.

3. Add it to the load balancer.

Install the backend first: the frontends need its databases, and the
backend makes the tables, the search index, the admin account and the
starter content. The admin login is in the backend's
`/root/tippr-first-login.txt`.

When a password or setting in `cluster.env` changes on the backend (e.g.
re-running its installer with a new one), copy the file to the frontends
again and re-run their installer.

## Updates

`/admin/servers` lists every server with its role and updates them one at
a time, as for one server. A frontend checks its pages came back; the
backend, which has none, that the app reaches its database. The order
isn't fixed, so read a release's notes for anything that needs the backend
first.

## Backups and data exports

- **`/admin/backups`** works from any frontend: its requests go through
  ZooKeeper to the backend, where tippr-backup makes the backups, and the
  list and progress come back the same way (`tippr-backup-relay.timer` on
  the backend passes them every 10 seconds). The backups are on the
  backend's disk (`backup_dir`). One thing doesn't work across servers:
  **another server copying a split site's backups** with a transfer key,
  since the frontend it would ask doesn't have the files. Copy the backup
  folder from the backend with scp or rsync instead ([BACKUP.md](BACKUP.md)).
- **Members' data exports** (`/prefs/privacy`) are kept in PostgreSQL, so
  any frontend gives a member the export the backend made.

## More backends later

Frontends scale by adding more. The backend is one server for now; its
parts scale their own ways when needed: Cassandra, ZooKeeper and
OpenSearch as 3-node clusters, RabbitMQ as a cluster, PostgreSQL with
replicas (the app can read from them), memcached with more servers. Those
are separate steps, one service at a time, on servers on different Proxmox
hosts, since a cluster on one host doesn't survive that host failing.
