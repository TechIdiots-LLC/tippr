# How tippr fits together

This is an overview of the pieces of a tippr site, where its data lives,
and how a request reaches the app. For installing, see
[INSTALL_tippr.md](INSTALL_tippr.md); for plans, see
[ROADMAP.md](ROADMAP.md).

tippr is a fork of reddit's r2 codebase, ported to Python 3.12. The
installer puts everything on one Ubuntu 24.04 server, but each data store
can move to its own server or container later (see
[Splitting it up](#splitting-it-up)).

## Request flow

```
browser
  │ HTTPS :443 (or, behind an external proxy, HTTP :80 from it)
  ▼
nginx ──── TLS; real client IPs from trusted proxies only
  ├── websocket upgrades .. tippr-websockets, 127.0.0.1:9001 (live updates)
  ├── /media/ ............. files in /srv/www/media
  ├── /pixel/, /click ..... tracking pixel and click redirector
  └── everything else ..... gunicorn, 127.0.0.1:8001 (r2, the web app)
```

Standalone, nginx also listens on port 80, where it redirects to HTTPS and
answers Let's Encrypt's challenges. Behind a proxy that does TLS itself
(`TIPPR_EXTERNAL_PROXY`, e.g. HAProxy on pfSense), nginx serves plain HTTP
on port 80 and takes client addresses from that proxy's `X-Forwarded-For`.

## The web app (r2)

- **r2** (`r2/r2`) is the application: controllers, models, Mako
  templates, static files.
- It runs under **gunicorn** (`tippr-paster.service`) with `run.ini`.
- r2 was written for Pylons. The `pylons/` package in this repo is a small
  reimplementation of the Pylons API on WebOb and Paste, and is effectively
  r2's web framework now. Moving to Pyramid is a planned project.
- Configuration is the ini, generated with `make ini` from:
  - `example.ini`, the defaults;
  - `development.update`, the site's settings;
  - `development.secrets`, the passwords and signing secrets the installer
    generates from `/etc/tippr/secrets.env`.

  Settings saved on admin pages (site details, email, ads) are kept in
  ZooKeeper and override the ini without a restart
  (`r2/lib/site_settings.py`).

## Data stores

| Store | Holds | Rebuildable? |
|---|---|---|
| **PostgreSQL** (database `tippr`) | "things" and their relations: accounts, posts, comments, vaults, messages, subscriptions, moderators; the hardcache | no: back it up |
| **Cassandra** (keyspace `tippr`) | votes, saved and hidden items, wiki pages and revisions, mod logs, OAuth tokens, permacache, listing caches. Each table is `key text, columns map<text, blob>` through `r2/lib/db/cassandra_compat.py` | no: back it up |
| **ZooKeeper** | saved site settings (`/tippr/settings/*`), IP throttles; live config and secrets when `liveconfig_source` / `secrets_source` are `zookeeper` | no: back it up |
| **Media files** (`/srv/www/media`) | uploaded images and thumbnails (filesystem media provider) | no: back it up |
| **OpenSearch** | the post and vault search indexes | yes: `g.search.rebuild_index()` |
| **memcached** | caches, locks, rendered fragments, rate limits | yes: just a cache |
| **RabbitMQ** | queued background work | transient |

[BACKUP.md](BACKUP.md) exports and restores the stores that can't be
rebuilt.

## Background work

- **Queue consumers.** `tippr-consumers.service` starts one or more
  `tippr-consumer-<queue>@N.service` per queue. The counts live in
  `$TIPPR_HOME/consumer-count.d`. The consumers:
  - process votes;
  - place new comments into comment trees;
  - update listings by vault, author and domain;
  - index posts for search (`search_q`, reading `cloudsearch_changes`);
  - fetch thumbnails (scraper);
  - send notifications (butler);
  - do account deletion and privacy exports.

  Some of them poll their queue instead of subscribing, so RabbitMQ can
  show them as having no consumer.
- **Scheduled jobs** are systemd timers (`tippr-job-*.timer`): rising, time
  listings, popular and trending vaults, broken things, hardcache cleanup,
  trylater and the email queue.
- **Services**: `tippr-websockets` (live updates), `tippr-activity` (who's
  here counts), click/pixel trackers and geoip on gunicorn.
- **Backups**: `tippr-backup.path` starts `tippr-backup.service` for
  requests made on /admin/backups.

`tippr.target` covers the web app, consumers, jobs and services. Use
`tippr-start`, `tippr-stop` and `tippr-restart` for all of them at once.

## Admin pages

With admin mode on (`/adminon`, which requires TOTP in production):

| Page | For |
|---|---|
| `/admin/site` | site name, description, contact address and logo |
| `/admin/antispam` | the captcha (built-in, Turnstile, hCaptcha, reCAPTCHA) and CleanTalk |
| `/admin/errors` | recent unhandled errors with tracebacks |
| `/admin/email` | outgoing email (SMTP or Gmail) |
| `/admin/ads` | Google AdSense ([INSTALL_tippr.md](INSTALL_tippr.md#google-adsense)) |
| `/admin/backups` | export, import, restore, transfer keys ([BACKUP.md](BACKUP.md)) |
| `/admin/awards`, `/admin/coins`, `/admin/gold` | trophies, coins and gold |
| `/admin/privacy` | data export and deletion requests |

See [ADMIN_FEATURES.md](ADMIN_FEATURES.md).

## Content features

- **Search:** OpenSearch through `r2/lib/providers/search/opensearch.py`
  ([SEARCH.md](SEARCH.md)). The Solr provider is still present. The AWS
  CloudSearch provider is gone.
- **AI content labels:** human-made, AI-assisted or AI-generated per post,
  with per-vault policies and a per-user filter ([CONTENT.md](CONTENT.md)).
- **Starter vaults** and front page defaults
  (`scripts/create_default_vaults.py`, [CONTENT.md](CONTENT.md)).
- **Comments:** a formatting toolbar, previews and `:shortcode:` emoji.

## Splitting it up

The single VM can be split by role:

| Role | Runs |
|---|---|
| db | PostgreSQL |
| cassandra | Cassandra |
| search | OpenSearch |
| cache-queue | memcached, RabbitMQ, ZooKeeper |
| app (1..n) | r2, queue consumers, timers |
| edge | a load balancer (nginx, HAProxy) in front of the app nodes' nginx |

To move a site to that layout:

1. Install the new machines.
2. Point the app server's ini at them.
3. Export from the old VM with `--offline`, and import and restore on the
   new app server ([BACKUP.md](BACKUP.md)).

Restore writes to wherever the new ini points. Every app node has the
same timers. Each job takes a ZooKeeper lock first (`scripts/run-locked`),
so it runs on one node at a time. With several memcached servers, mcrouter
becomes worthwhile ([ROADMAP.md](ROADMAP.md)).
