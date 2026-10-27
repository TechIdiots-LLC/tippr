# Backups, moving servers and restoring

tippr can export the whole site to a folder, copy a backup from another
tippr server, and restore one. Use it for regular backups, and to move a
site: for example from the single VM the installer sets up to separate
database, Cassandra and app servers or containers.

Everything can be done from **/admin/backups** (admin mode on) or with the
`tippr-backup` command as root.

## What a backup holds

A backup is a folder, `tippr-backup-YYYYMMDD-HHMMSS`, in `backup_dir`
(default `/var/lib/tippr/backups`):

| File | Contents |
|---|---|
| `manifest.json` | what's in the backup, where it came from, progress while it runs, and a SHA-256 for every file |
| `postgres/<db>.dump` | `pg_dump` of each PostgreSQL database (custom format): accounts, posts, comments, vaults, messages |
| `cassandra/schema.json`, `cassandra/<table>.jsonl.gz` | every table in the `tippr` keyspace and every row: votes, saved and hidden posts, wiki pages, mod logs, OAuth tokens, listing caches |
| `zookeeper.json` | the ZooKeeper tree: settings saved on admin pages (email, ads), IP throttles, and live config and secrets when they're kept there |
| `media.tar.gz` | uploaded media (with `media_provider = filesystem`) |
| `secrets.json` | the signing secrets (`[secrets]` and `tracking_secret`), so logins, cookies and signed links keep working after a move |
| `development.update` | the site's own settings, for reference; restore doesn't apply it |

Not included, because they're rebuilt or temporary:

- the **search index**: restore rebuilds it from the database;
- **memcached**: restore empties it;
- **RabbitMQ** queues: an offline export waits for them to empty first;
- this server's **transfer key** (see below).

Backups hold password hashes, email addresses and secrets. They belong to
the tippr user, with mode 0600/0700. Keep copies somewhere private.

## Exporting

From /admin/backups, choose **export now**. From the command line:

```bash
sudo tippr-backup export             # site stays up
sudo tippr-backup export --offline   # consistent copy
sudo tippr-backup list
```

`--offline` (the "take the site offline" box) is for moving servers. It
stops the web app, waits for the queue consumers to finish queued work,
then stops the rest of tippr, exports, and starts tippr again. Without it
the site stays up, and changes made during the export may be only partly
included. That's fine for routine backups.

`backup_dir` in the ini can point at another disk or a mounted share.

Exports run in `tippr-backup.service`, as root. The web app can't do the
work itself, so /admin/backups writes a request file into
`/var/lib/tippr/backup-queue`, and `tippr-backup.path` starts the service.
The page shows progress and the last request's log.

## Daily backups and the off-site copy

Every night at about 03:30, `tippr-backup-daily.timer` makes a backup (on
the one server, or the backend of a split site), with the site up, and
keeps the newest 7 of these in `backup_dir`. Backups made on
/admin/backups are never removed by it. A night the server was off is made
up when it's back. If one fails, the smoke check reports it, and
tippr-monitor sends an alert.

A backup on the server it backs up is lost with that server, so copy them
somewhere else: give the installer an S3 bucket, and each daily backup is
uploaded there too, as one file, keeping the newest 30.

```bash
sudo TIPPR_BACKUP_S3_BUCKET=tippr-backups ./install-tippr.sh
```

| Setting | Default | |
|---|---|---|
| `TIPPR_BACKUP_SCHEDULE` | `daily` | `off` stops the daily backups |
| `TIPPR_BACKUP_KEEP` | `7` | daily backups kept on the server |
| `TIPPR_BACKUP_S3_BUCKET` | (none) | the bucket for the copies |
| `TIPPR_BACKUP_S3_PREFIX` | the domain | the folder in it, so several sites can share one bucket |
| `TIPPR_BACKUP_S3_KEEP` | `30` | copies kept in the bucket |
| `TIPPR_BACKUP_S3_ENDPOINT`, `_REGION`, `_KEY_ID`, `_SECRET` | the media storage's (`TIPPR_S3_*`) | another S3 service or key |

They're remembered like the installer's other settings; `off` clears one.
In the ini they're `backup_keep` and `backup_s3_*`.

The bucket holds the database, members' emails and the signing secrets:
keep it private, and give it a key of its own. With Garage, for example:

```bash
garage bucket create tippr-backups
garage key create tippr-backups
garage bucket allow --read --write tippr-backups --key tippr-backups
```

and give that key's ID and secret as `TIPPR_BACKUP_S3_KEY_ID` and
`TIPPR_BACKUP_S3_SECRET` (the media key then can't reach the backups, nor
this one the media).

From the command line:

```bash
sudo tippr-backup list --remote          # what's in the bucket
sudo tippr-backup upload NAME            # copy one made by hand there too
sudo tippr-backup fetch NAME             # download one into backup_dir
sudo tippr-backup restore /var/lib/tippr/backups/NAME
```

`fetch` checks every file against the backup's manifest (size and SHA-256)
and removes the download if one doesn't match. On a new server after
losing the old one: install tippr with the same `TIPPR_BACKUP_S3_*`
settings, then `fetch` and `restore` the newest.

## Moving to a new server

1. **Install tippr on the new server** with the installer, as usual. For a
   split layout, give the new app server an ini whose database, Cassandra,
   ZooKeeper, memcached and RabbitMQ settings point at the new machines.
   Restore writes wherever that ini says.
2. **Copy a backup to the new server**, either way:
   - **Import over HTTPS.** On the old server, open /admin/backups and make a
     **transfer key**. On the new server's /admin/backups, under **import
     from another server**, enter the old server's address and the key.
     Tick **have it make a new backup first** and **offline** to get a
     fresh, consistent copy. Or from the command line on the new server:

     ```bash
     sudo tippr-backup import https://old.example.com --key tpk_... --fresh --offline
     ```

   - **Copy by hand.** As root, rsync or scp the backup folder into
     `backup_dir` on the new server.
3. **Restore** from the new server's /admin/backups (type the site's
   domain to confirm), or:

   ```bash
   sudo tippr-backup restore /var/lib/tippr/backups/tippr-backup-YYYYMMDD-HHMMSS
   ```

   An import can restore as soon as it finishes: tick **restore it here**,
   or pass `--restore` to `tippr-backup import`.
4. **Check the site**, then point DNS (or Cloudflare) at the new server, and
   revoke the transfer key on the old one.

### What restore does

1. Stops tippr (`tippr.target`).
2. Replaces each PostgreSQL database with `pg_restore --clean`.
3. Empties and refills every Cassandra table. If the keyspace is missing it
   is created from the backup; an existing keyspace keeps this server's
   replication settings.
4. Writes the ZooKeeper nodes.
5. Unpacks media into `media_fs_root`.
6. Installs the backup's signing secrets. It updates
   `/etc/tippr/secrets.env` and `development.secrets`, then regenerates the
   ini. Signing secrets the installer doesn't manage (payment or API keys
   you added by hand) are listed in the output for you to copy.
7. Empties memcached, starts tippr, and rebuilds the search index.

This server's own passwords (PostgreSQL, RabbitMQ, ZooKeeper) are kept.
Everything else on the site is replaced, including accounts: afterwards you
log in with an account from the backup.

If a step fails, tippr is left stopped, because its data is only partly
restored. Fix the problem and run the restore again (it starts over), or
start tippr with `tippr-start`.

The site's name, description, contact address and logo come with the
backup; change them on **/admin/site** if the new site should differ. The
domain is this server's own: to use a new one, re-run the installer with
`TIPPR_DOMAIN=new.example.com`.

## Transfer keys

A transfer key lets another tippr server list this server's backups, copy
them, and ask for new ones. That is all it can do.

- Make one on /admin/backups. It's shown once and expires after 7 days.
  Making a new one replaces the old one, and **revoke** removes it.
- Only a hash is stored (site settings group `backups`). Backups never
  include it, so restoring a backup elsewhere doesn't let anyone into that
  server.
- The other server sends it as `Authorization: Bearer <key>` over HTTPS to
  `/backup_transfer/...`. Files move in 16 MB pieces, one short request
  each, and are checked against the manifest's SHA-256. An interrupted
  import resumes where it stopped.
- For a test site with a self-signed certificate, tick **don't check its
  TLS certificate** (or pass `--insecure`).

## Limits

- Expiry times on Cassandra rows are not kept. Cassandra 4.1 can't read the
  TTL of individual map entries. Rows that would have expired, mostly old
  tokens and cached listings, stay until they're replaced or cleaned up.
- An export without `--offline` is not a point-in-time copy across all the
  data stores.
- `pg_restore` must be the same PostgreSQL version as `pg_dump` or newer.
  The installer's PostgreSQL client is fine for a server it installed.
- Media kept in S3 (`media_provider = s3`) isn't copied. It stays in the
  bucket.
