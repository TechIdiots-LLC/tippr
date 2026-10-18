# Tippr Roadmap

What is planned, in what order, and the decisions behind it. For how to run
tippr today, see [INSTALL_tippr.md](INSTALL_tippr.md) and
[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).

## Done

- **Rename cleanup.** Fixed what the reddit → tippr / subreddit → vault
  rebrand broke: symlinks and templates, half-finished renames
  (creddits → coins, `.sr-*` CSS classes, `/r/` → `/v/`), and Python 3
  porting bugs.
- **systemd.** Upstart is gone. Jobs run from systemd timers, and queue
  consumers start with `tippr.target` through `tippr-consumers.service`.
- **Installer.** The installer completes on Ubuntu 24.04, including under
  WSL2. The mcrouter source build is opt-in (`TIPPR_BUILD_MCROUTER=1`).
- **Backups and server moves.** `tippr-backup` and /admin/backups export
  and restore PostgreSQL, Cassandra, ZooKeeper, media and the signing
  secrets. Another server can import a backup over HTTPS with a transfer
  key ([BACKUP.md](BACKUP.md)).
- **Docker image and releases.** `docker/` builds one image for every app
  role (web, consumers, jobs, websockets, activity, geoip) with a compose
  file for the whole stack. Version tags publish the image to Docker Hub
  and a GitHub release with a compose bundle and an installer tarball, all
  smoke-tested first ([RELEASING.md](RELEASING.md)).
- **Proxmox template.** Releases include an all-in-one LXC template that
  sets itself up for its domain on first boot ([PROXMOX.md](PROXMOX.md)).
  Scheduled jobs take a ZooKeeper lock (`scripts/run-locked`), so several
  app servers can share a site.
- **Admin pages** for the site's name, description, contact address and
  logo (`/admin/site`), email (`/admin/email`), Google AdSense
  (`/admin/ads`) and recent errors (`/admin/errors`).

## Next: single-VM production setup

The first supported deployment is **one Ubuntu 24.04 VM** running everything,
installed with `install-tippr.sh`.

- **Passwords:** generate random passwords for PostgreSQL, RabbitMQ, ZooKeeper
  and the default admin account, stored in a root-only file. A value passed to
  the installer (for example `TIPPR_DB_PASSWORD=...`) takes precedence.
- **App server:** run the app under gunicorn instead of
  `paster serve --reload`.
- **Production settings:** `debug = false`, captcha and rate limiting on,
  admin TOTP required.
- **Site settings:** set the domain, site name and page title
  (`short_description`) from installer options.
- **TLS:** a Cloudflare Origin Certificate or Let's Encrypt for real
  domains, a self-signed certificate for `.local` ones. Redirect `http://`
  to `https://`.
- **Cloudflare (Free plan):** see [Cloudflare](#cloudflare) below.
- **Search:** OpenSearch, installed by default (done; see
  [SEARCH.md](SEARCH.md) and [Search](#search)).
- **Shims:** `BeautifulSoup.py`, `baseplate/`, `pycassa/`, `weberror/`,
  `Captcha/`, `cassandra.disabled/` and `l2cs.py` are gone (r2 uses bs4,
  the real baseplate 2.x and `r2.lib.db.cassandra_compat`; the AWS
  CloudSearch provider that needed `l2cs.py` was replaced by OpenSearch),
  as are the installer's venv patches. Left: `pylons/`, which is
  effectively r2's web framework now (moving to Pyramid or similar is its
  own project).

## Then

1. **Per-role Proxmox templates.** App and edge templates (configured on
   first boot to point at separate data store containers), next to the
   all-in-one template, and an installer role setting (`TIPPR_ROLE`) for
   data store containers.
2. **Admin security.** Require TOTP for admin mode, add WebAuthn passkeys,
   and use recovery codes instead of email as the fallback.
3. **Admin config page.** Edit the live config stored in ZooKeeper from
   `/admin/config`, with type checking and an audit log.

## Payments and tipping

Decided order:

1. **Bitcoin for gold and coins (next payments work).** Accept Bitcoin
   (Lightning and on-chain) through a self-hosted
   [BTCPay Server](https://btcpayserver.org/), alongside the existing payment
   providers. The site is simply accepting a payment method.
2. **Direct user-to-user tips (after 1).** Users add a Lightning address to
   their profile. A tip button requests an invoice from the recipient's
   wallet, and the tipper pays it from their own wallet. tippr shows the tip
   and its receipt on the post or comment but **never holds the funds**,
   which avoids becoming a money transmitter.
3. **On hold: karma cash-out / revenue sharing.** Paying users out of a pool
   based on votes needs more thought before any work starts:
   - Holding pooled funds raises money-transmission, financial-product and
     tax-reporting questions that need legal advice.
   - Paying for votes invites vote buying, bot rings and sockpuppets.
     Steemit/Hive is the precedent to study.
   - Safer variants to consider: pay out from site revenue rather than a
     pool users pay into, base payouts on tips received rather than raw
     karma, and add caps, delays and fraud review.

## Search

[OpenSearch](https://opensearch.org/) (Apache 2.0) replaces CloudSearch and
Solr. It runs as a single node with a 1 GB heap, from the apt repository or
the Docker image. Done:

- the `opensearch` provider (index mappings, indexer, query builder);
- relevance: title weighted above body and URL, vote and age boosts, typo
  tolerance, vault names matched by prefix;
- the existing `vault:`, `author:`, `site:`, `nsfw:` and `self:` query
  syntax;
- installer support and `g.search.rebuild_index()`.

Still to do:

- use `g.search.suggest_vaults()` for the vault-name autocomplete in the
  submit form and search box;
- possibly comment search.

## Cloudflare

Cloudflare's Free plan works in front of tippr:

- **Real client IPs:** nginx accepts `CF-Connecting-IP` only from
  Cloudflare's published IP ranges (`real_ip` module). Without this, rate
  limits, spam checks and IP bans see Cloudflare addresses. r2's bundled
  Cloudflare provider expects a reddit-specific `CF-CIP-Tag` header and does
  not work on a standard account.
- **Page caching:** r2 already marks logged-in responses `private`. Plan:
  send `Cache-Control: public, s-maxage=60, max-age=0` on logged-out HTML,
  and add a Cache Rule that makes HTML eligible for cache and respects the
  origin's Cache-Control. The Free plan's 2-hour minimum applies to Edge TTL
  overrides; confirm with the `cf-cache-status` / `age` headers that a short
  origin `s-maxage` is honoured.
- **Fallback:** an nginx `proxy_cache` on the VM can cache logged-out pages
  for 30–60 seconds, with or without Cloudflare.
- **TLS:** use SSL mode Full (strict) with an Origin Certificate.

## Deployment layouts

### Now: single VM

Run everything on one Ubuntu 24.04 VM (or Proxmox LXC) with the installer.
Allow 4–6 cores and 8–12 GB RAM. Proxmox snapshots and backups cover the
whole site.

### Later: Proxmox containers by role

| Container | Components | Notes |
|---|---|---|
| db | PostgreSQL | Primary data; own backups and disk. Read replicas supported by r2 |
| cassandra | Cassandra | Memory hungry; holds votes, listings, wiki. Clusters natively |
| search | OpenSearch | Can be rebuilt from the database. Clusters natively |
| cache-queue | memcached, RabbitMQ, ZooKeeper | Small; shared by all app nodes |
| app (1..n) | r2, queue consumers, timers | Stateless; add more to scale |
| edge | HAProxy or nginx | TLS, Cloudflare real IP, page cache, load balancing (app nodes run with `TIPPR_EXTERNAL_PROXY`) |

Cassandra and OpenSearch need `vm.max_map_count` raised on the Proxmox
host. Proxmox recommends running Docker in a VM rather than in LXC.

### Later: nodes joining a cluster

Goal: stand up another VM, point it at the cluster, and have it start
contributing.

- **Installer roles:** `TIPPR_ROLE=all` (default), `app`, `data`, plus a
  join setting pointing at ZooKeeper, which already holds most live config
  and secrets.
- **App and consumer nodes** need no extra coordination: RabbitMQ shares
  queue work across consumers, and the edge balances web traffic.
- **Scheduled jobs** must run on one node at a time. Take a ZooKeeper lock
  (kazoo) before each job so any node can run the timers safely.
- **Data tier:** Cassandra, OpenSearch and RabbitMQ join by seed addresses.
  PostgreSQL stays a single primary with replicas; automatic failover
  (Patroni or similar) is a separate project.
- **Caching:** more memcached nodes means more servers in the cache lists.
  At that point mcrouter (routing and failover across memcached servers) is
  worth running, preferably as a prebuilt container image rather than a
  source build.

## Open questions

- What to call users in site text: the code still has a few "redditor"
  strings, and the translation catalogs say "tipprors".
