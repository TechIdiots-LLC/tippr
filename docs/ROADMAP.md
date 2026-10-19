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
- **Single-VM production setup.** One Ubuntu 24.04 VM (or Proxmox LXC)
  running everything, installed with `install-tippr.sh`: random passwords
  in a root-only `secrets.env` (values passed to the installer win), the
  app under gunicorn, production settings (`debug = false`, captcha and
  rate limits, TOTP required for admin mode), the domain and site name from
  installer options, TLS (Let's Encrypt, a Cloudflare Origin Certificate,
  or self-signed for `.local`), Cloudflare's real client IPs in nginx, and
  OpenSearch ([SEARCH.md](SEARCH.md)).
- **Shims removed.** `BeautifulSoup.py`, `baseplate/`, `pycassa/`,
  `weberror/`, `Captcha/`, `cassandra.disabled/` and `l2cs.py` are gone
  (r2 uses bs4, the real baseplate 2.x and `r2.lib.db.cassandra_compat`),
  as are the installer's venv patches. Left: `pylons/`, which is
  effectively r2's web framework now (moving to Pyramid or similar is its
  own project).
- **Admin pages:** the site's name, description, images, SEO and Google
  Analytics (`/admin/site`), live config (`/admin/config`), email, Google
  AdSense, spam protection, backups, recent errors, API apps, feed bots,
  banned domains, accounts (`/admin/users`), vaults (`/admin/vaults`) and
  the support queue with per-category staff ([ADMIN_FEATURES.md](ADMIN_FEATURES.md)).
- **Traffic stats** counted by the site itself (`/traffic`, each vault's
  traffic page), help pages (`/help`), and the normal site working on
  phones (the separate mobile interface is no longer promoted).
- **Optional S3-compatible media storage** (Garage, MinIO, Amazon S3 …;
  [STORAGE.md](STORAGE.md)).
- **GitLab CI/CD** alongside the GitHub workflows ([RELEASING.md](RELEASING.md)).

## Next

1. **Self-serve ads.** Make advertiser-bought ads work without reddit's
   private services: ad images stored on the server when there's no
   bucket, inventory from the site's own traffic counts, and impressions
   and clicks counted by the site.
2. **Payments** for gold and ads; see [Payments and gold](#payments-and-gold).

## Then

1. **Per-role Proxmox templates.** App and edge templates (configured on
   first boot to point at separate data store containers), next to the
   all-in-one template, and an installer role setting (`TIPPR_ROLE`) for
   data store containers.
2. **More two-factor options** (for everyone; admin mode already requires
   two-factor): passkeys (WebAuthn) as a second factor besides an
   authenticator app, and recovery codes for someone who loses their
   device. Today the only way back in is an admin resetting it on
   /admin/users.
3. **Explore: logging in with another account.** Members link a Google,
   Microsoft or Facebook account in their preferences and can then log in
   with it instead of their password (OpenID Connect / OAuth). Questions to
   settle first: signing up with one (choosing a username, the captcha),
   how it combines with two-factor, and unlinking. Instagram no longer
   offers logins to other sites; Meta's is Facebook Login.
4. **Policy pages that follow the site settings.** The user agreement,
   privacy and content policies and help pages are filled in from
   `docs/policies/` and `docs/help/` with the site's name, domain,
   operator, contact address and governing law when
   `scripts/init_policy_wiki_pages.py` runs. Re-fill them automatically
   when those settings change on /admin/site (and after an upgrade brings
   new versions), except pages an admin has edited by hand, which get a
   note instead of being overwritten.

## Payments and gold

The site sells its own things (gold and ads) and nothing else. It **never
holds members' money or pays it out**: no tipping between members, no
balances, and no karma cash-out or revenue sharing. Holding or passing on
other people's money is what money transmitters and banks do, with the
licensing, compliance and tax reporting that comes with it, which isn't
worth it for a site this size.

- **Gold is the paid tier:** an ad-free, VIP experience (gold-only
  features and vaults, as now).
- **Gifting gold is how members reward each other.** Anyone can buy gold
  for another member, or gild a post or comment they like (both are
  already in the code), so members can get gold for free when people value
  what they write. The money goes to the site; the recipient gets gold.
- **Payment providers,** shared by gold and ads: PayPal first, then
  BitPay or Coinbase Commerce for cryptocurrency. The gold and ad checkout
  code is reddit's (PayPal IPN and Stripe, set up for reddit's accounts)
  and gets one payment layer with a provider per service.

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
  submit form and search box (it still uses the old name search);
- possibly comment search.

## Cloudflare

Cloudflare's Free plan works in front of tippr:

- **Real client IPs (done):** nginx accepts `CF-Connecting-IP` only from
  Cloudflare's published IP ranges (`real_ip` module). Without this, rate
  limits, spam checks and IP bans see Cloudflare addresses. r2's bundled
  Cloudflare provider expects a reddit-specific `CF-CIP-Tag` header and does
  not work on a standard account.
- **Page caching (to do):** r2 already marks logged-in responses `private`. Plan:
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
