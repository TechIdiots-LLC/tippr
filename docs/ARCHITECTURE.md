# How tippr fits together

This is an overview of the pieces of a tippr site, where its data lives,
and how a request reaches the app. For installing, see
[INSTALL_tippr.md](INSTALL_tippr.md); for plans, see
[ROADMAP.md](ROADMAP.md).

tippr is a fork of reddit's r2 codebase, ported to Python 3.12. The
installer puts everything on one Ubuntu 24.04 server, or splits it into a
backend and any number of frontends (see
[Splitting it up](#splitting-it-up)).

## Request flow

```
browser
  │ HTTPS :443 (or, behind an external proxy, HTTP :80 from it)
  ▼
nginx ──── TLS; real client IPs from trusted proxies only
  ├── websocket upgrades .. tippr-websockets, 127.0.0.1:9001 (live updates)
  ├── /media/ ............. files in /srv/www/media, or the S3 bucket
  │                         (TIPPR_MEDIA_STORAGE=s3, STORAGE.md)
  ├── /pixel/, /click ..... tracking pixel and click redirector
  └── everything else ..... gunicorn, 127.0.0.1:8001 (r2, the web app)
```

Standalone, nginx also listens on port 80, where it redirects to HTTPS and
answers Let's Encrypt's challenges. Behind a proxy that does TLS itself
(`TIPPR_EXTERNAL_PROXY`, e.g. HAProxy on OPNsense or pfSense), nginx serves plain HTTP
on port 80 and takes client addresses from that proxy's `X-Forwarded-For`.

## The web app (r2)

- **r2** (`r2/r2`) is the application: controllers, models, Mako
  templates, static files.
- It runs under **gunicorn** (`tippr-paster.service`) with `run.ini`;
  `tippr-serve` runs it in the foreground with reloading, for development.
- r2 was written for Pylons. The `pylons/` package in this repo is a small
  replacement for the Pylons API, built on WebOb (requests and responses)
  and Routes (URLs), and is r2's own web framework now. Paste, which r2
  still uses for a few pieces of middleware, is being phased out
  ([ROADMAP.md](ROADMAP.md)); the jobs, queue processors and `tippr-run`
  load the app with `r2.commands` (`python -m r2.commands`), not `paster`.
- Configuration is the ini, generated with `make ini` from:
  - `example.ini`, the defaults;
  - `development.update`, the site's settings;
  - `development.secrets`, the passwords and signing secrets the installer
    generates from `/etc/tippr/secrets.env`.

  Settings saved on admin pages (site details, email, ads, payments, live
  config) are kept in
  ZooKeeper and override the ini without a restart
  (`r2/lib/site_settings.py`).
- **Python packages** are pinned in `install/requirements.txt`, which the
  installer and the Docker image install exactly (`--no-deps`). Packages a
  release stops using are listed in `install/requirements-retired.txt`,
  and the installer removes them, so a server updated from /admin/servers
  doesn't keep them. After installing, `scripts/check_requirements.py r2`
  checks every package r2 needs is there at a version it accepts.
  Nothing tippr runs needs setuptools' `pkg_resources`, so setuptools is
  current.

## Data stores

| Store | Holds | Rebuildable? |
|---|---|---|
| **PostgreSQL** (database `tippr`) | "things" and their relations: accounts, posts, comments, vaults, messages, subscriptions, moderators; the hardcache; gold purchases, payments, sold ads' bids, feeds, support tickets; members' finished data exports (`privacy_export_files`, kept 8 days), scale tips (`scale_tips`), the admin actions on each account (`/admin/users`) | no: back it up |
| **Cassandra** (keyspace `tippr`) | votes, saved and hidden items, wiki pages and revisions, mod logs, OAuth tokens, permacache, listing caches; the addresses each account is used from (account activity, kept 100 days). Each table is `key text, columns map<text, blob>` through `r2/lib/db/cassandra_compat.py` | no: back it up |
| **ZooKeeper** | saved site settings (`/tippr/settings/*`), IP throttles, the jobs' locks, update requests from /admin/servers (`/tippr/update`), backup requests and state on a split site (`/tippr/backups`); live config and secrets when `liveconfig_source` / `secrets_source` are `zookeeper` | no: back it up |
| **Media** (`/srv/www/media`, or an S3 bucket) | uploaded images and thumbnails ([STORAGE.md](STORAGE.md); a split site needs the bucket) | no: back it up |
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
  - do account deletion and members' data exports (kept in PostgreSQL, so
    any server can hand one out).

  Some of them poll their queue instead of subscribing, so RabbitMQ can
  show them as having no consumer.
- **Scheduled jobs** are systemd timers (`tippr-job-*.timer`): rising, time
  listings, popular and trending vaults, vault names, broken things,
  hardcache cleanup, trylater, the email queue, feeds (posting new items),
  gold expiry (which skips permanent gold), subscriber counts, vault
  similarity (Explore), the X-Year Club trophies, sitemaps, server
  reports for /admin/servers, and sold ads (promos and their metrics).
  The jobs and queue consumers load the app with `python -m r2.commands`;
  `tippr-run` and `tippr-shell` do the same for scripts and a prompt.
- **Services**: `tippr-websockets` (live updates), `tippr-activity` (who's
  here counts) and geoip on gunicorn. Ads are counted by the web app
  (r2.lib.ad_traffic, with its /click for sponsored posts).
- **Backups**: `tippr-backup.path` starts `tippr-backup.service` for
  requests made on /admin/backups. On a split site, `tippr-backup-relay.timer`
  on the backend passes a frontend's requests to it and its backups and
  progress back, through ZooKeeper ([SERVERS.md](SERVERS.md)).

`tippr.target` covers the web app, consumers, jobs and services. Use
`tippr-start`, `tippr-stop` and `tippr-restart` for all of them at once.

## Admin pages

With admin mode on (`/adminon`, which requires TOTP in production):

| Page | For |
|---|---|
| `/admin/site` | site name, description, contact address and logo |
| `/admin/config` | the live settings: staff, thresholds, messages |
| `/admin/users` | find and manage accounts: timeouts, suspensions, content, email, two-factor, staff permission, internal status, and gold (give or take months, make it permanent, remove it), each in the account's admin log |
| `/admin/vaults` | find and manage vaults |
| `/admin/feeds` | the feeds that post into vaults: search, filter by vault, bot or status, sort, and edit (including the vault a feed posts to) |
| `/admin/servers` | each server's role, load and services, and updates ([SERVERS.md](SERVERS.md)) |
| `/admin/payments` | payment providers for gold and ads ([gold-payments.md](gold-payments.md)) |
| `/admin/logins` | "sign in with Google / Facebook / GitHub / Discord" (linked sign-ins) |
| `/admin/support` | the support queue (messages to the admins) |
| `/admin/apps`, `/admin/domains` | API apps, banned domains |
| `/admin/antispam` | the captcha (built-in, Turnstile, hCaptcha, reCAPTCHA) and CleanTalk |
| `/admin/errors` | recent unhandled errors with tracebacks |
| `/admin/email` | outgoing email (SMTP or Gmail) |
| `/admin/ads` | Google AdSense ([INSTALL_tippr.md](INSTALL_tippr.md#google-adsense)) |
| `/admin/backups` | export, import, restore, transfer keys ([BACKUP.md](BACKUP.md)) |
| `/admin/awards`, `/admin/coins` | trophies, and Give Gold (months members can gift); gold itself is on `/admin/users` (`/admin/gold` goes there) |
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
- **Feeds:** RSS and Atom feeds posting into vaults (`r2/lib/feeds.py`,
  [CONTENT.md](CONTENT.md#feeds)).
- **Listings:** the front page and multis merge each vault's hot list
  (`r2/lib/normalized_hot.py`), which mixes vaults; /v/all ranks every
  post together, so its hot list is spread (`spread_vaults`): no two posts
  in a row from one vault while another vault's post is close behind.
- **Scales:** members tip a post toward what kind of post it is, on six
  scales (human-made or AI-generated, quick overview or deep dive, and so
  on), seeing a scale's tally once they've tipped it, or all of them by
  giving up tipping that post ("see the results"); the poster, the vault's
  moderators and admins see them all (`r2/lib/scales.py`,
  [CONTENT.md](CONTENT.md#scales-and-reports)).
- **Reports:** the reasons follow the content policy
  (`r2/models/rules.py`, `SITEWIDE_RULES`), kept in English on the report
  and shown in the reader's language; a vault's own rules come first.
- **Payments:** gold and sold ads through PayPal, Stripe, Coinbase or BitPay
  (`r2/lib/payments/`, [gold-payments.md](gold-payments.md)).
- **Reading features** (preferences): night mode, infinite scroll, keyboard
  navigation, expanding images, filters, user tags, new-comment counts and
  an account switcher (`public/static/js/enhancements.js`).

## Accounts and security

- **Two-factor sign-in:** authenticator apps, passkeys and recovery codes
  (`r2/lib/two_factor.py`, `r2/lib/passkeys.py`). Preferences unlock once
  with a code, like admin mode: the security page and the password and
  email page always, every preferences page if the member chooses, and
  they stay unlocked while in use ([ADMIN_FEATURES.md](ADMIN_FEATURES.md)).
- **Account activity** (`/account-activity`): the addresses an account is
  used from, recorded at login and at most hourly while logged in
  (`r2/models/ip.py`), kept 100 days; private network addresses aren't
  kept. Admins see the same list on `/admin/users`.
- **Gold:** an expiry date that purchases and gifts move, and that the
  daily job checks; or permanent gold, given by an admin on `/admin/users`
  (`Account.gold_permanent`), which nothing takes away but an admin.

## Splitting it up

The installer's `TIPPR_ROLE` splits a site over servers
([SERVERS.md](SERVERS.md)):

| Role | Runs | How many |
|---|---|---|
| `all` (the default) | everything | one |
| `backend` | PostgreSQL, Cassandra, RabbitMQ, ZooKeeper, OpenSearch, memcached, the activity service, the queue consumers, the scheduled jobs, backups | one |
| `frontend` | nginx, the web app, live comments, geoip | one or more, behind a load balancer |

Frontends keep nothing of their own; they share the backend's stores, and
media has to be in a bucket. The backend writes `/etc/tippr/cluster.env`
(its address, the passwords and signing secrets), which each frontend is
installed from. Each scheduled job takes a ZooKeeper lock first
(`scripts/run-locked`), so it runs on one server at a time. The backend is
one server for now; how its stores would scale or be made redundant is in
[SERVERS.md](SERVERS.md#more-backends-later).

To move a site to new servers, export from the old one (`--offline`), and
import and restore on the new backend ([BACKUP.md](BACKUP.md)).
