# tippr with Docker Compose

This runs a whole tippr site with Docker Compose:

- the tippr image, in one container per role;
- the data stores it needs;
- Caddy in front for HTTPS.

Allow 4 CPU cores and 8 GB of RAM (Cassandra and OpenSearch take most of
it).

## Starting

1. Copy `.env.example` to `.env` and fill it in. You need at least:
   - `TIPPR_DOMAIN`;
   - `TIPPR_DB_PASSWORD` and `TIPPR_AMQP_PASSWORD` (use
     `openssl rand -hex 24` for each);
   - `TIPPR_TLS`: your email address for a Let's Encrypt certificate, or
     `internal` for a self-signed one.
2. Point the domain at this server. For a test site, add a hosts entry such
   as `127.0.0.1 tippr.test` instead.
3. Start it:

   ```bash
   docker compose up -d
   docker compose logs -f setup     # first start: wait for "setup finished"
   ```

4. Log in as `tippr` (or `TIPPR_ADMIN_USER`). The password is
   `TIPPR_ADMIN_PASSWORD` in the config volume's `secrets.env`:

   ```bash
   docker compose exec web grep ADMIN_PASSWORD /config/secrets.env
   ```

Then set up the rest on the admin pages (`/adminon`, then `/admin/site`,
`/admin/email` and so on). See the main documentation's INSTALL guide.

## Containers

| Service | What it runs |
|---|---|
| `setup` | Runs once on each start, then exits: database functions, the Cassandra keyspace, the admin account, starter vaults, policy pages and the search index. It skips what already exists. |
| `web` | the web app (gunicorn) |
| `consumers` | the queue consumers; `TIPPR_CONSUMERS` changes how many run per queue |
| `jobs` | the scheduled jobs, on the same schedules as the installer's systemd timers |
| `websockets`, `activity` | live updates and the "here now" counts |
| `geoip` | country lookups for visitors' addresses (from Ubuntu's GeoIP database) |
| `caddy` | HTTPS, media files, routing |
| `postgres`, `cassandra`, `zookeeper`, `rabbitmq`, `memcached`, `opensearch`, `redis` | the data stores |

To run more web or consumer containers:

```bash
docker compose up -d --scale web=2 --scale consumers=2
```

## Configuration

- **`.env`:** the domain, passwords, image version and sizes. Change it,
  then run `docker compose up -d` to apply. Changing `TIPPR_DB_PASSWORD`
  or `TIPPR_AMQP_PASSWORD` after the first start isn't enough on its own:
  the PostgreSQL and RabbitMQ containers only use them when their volumes
  are created. Change the password in the database (or broker) first.
- **`/config` volume:**
  - `secrets.env` holds the signing secrets and admin password. It is made
    on the first start and shared by every container; keep it with your
    backups.
  - `tippr.update` is optional: any other ini settings, in the same form
    as the installer's `development.update`. Restart the app containers to
    apply it.
- **Admin pages:** settings saved there (site name and logo, email, ads)
  are kept in ZooKeeper and apply at once.

Commands with the app loaded:

```bash
docker compose exec web tippr run -c 'print("hello")'   # like tippr-run
docker compose run --rm web shell                      # like tippr-shell
```

## Upgrading

Set `TIPPR_VERSION` in `.env` to the new release, then:

```bash
docker compose pull
docker compose up -d
```

## Backups

All data is in Docker volumes:

- `postgres`, `cassandra`, `zookeeper-data`, `media` and `config` hold the
  site;
- `opensearch` can be rebuilt;
- `rabbitmq` holds only queued work.

To back up, stop the stack and copy the volumes (for example
`docker run --rm -v tippr_postgres:/v -v $PWD:/b alpine tar czf /b/postgres.tgz -C /v .`).
Or run `pg_dump` from the `postgres` container while it's running.
`tippr-backup` and /admin/backups are for installer-based servers; they
don't run in this setup yet.

## Behind Cloudflare or another proxy

Caddy passes on the client address it sees. Behind Cloudflare, add
Cloudflare's IP ranges to Caddy's `trusted_proxies` in the `Caddyfile`, so
rate limits and bans see real visitors.
