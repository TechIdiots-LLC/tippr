# Installing tippr

`install-tippr.sh` sets up a complete tippr site on one Ubuntu 24.04
server, VM or WSL2 instance: the app, every data store it needs, TLS, and
systemd units. For how the pieces fit together, see
[ARCHITECTURE.md](ARCHITECTURE.md).

Give the installer a server of its own. It installs and configures
system-wide services: PostgreSQL, Cassandra, ZooKeeper, RabbitMQ,
memcached, OpenSearch and nginx. Allow 4–6 cores and 8–12 GB of
RAM.

## Running it

As root, from a checkout of this repository:

```bash
useradd -m -s /bin/bash tippr
TIPPR_USER=tippr TIPPR_DOMAIN=example.com ./install-tippr.sh
```

Re-running it is safe. It keeps the generated passwords and secrets, keeps
existing data, and regenerates the config and systemd units.

### Production or development

`TIPPR_ENVIRONMENT` (default `auto`) picks the mode. `auto` uses
development for `.local`, `.localhost` and `.test` domains and production
for everything else.

| | production | development |
|---|---|---|
| debug pages, template reloading | off | on |
| captcha, rate limits | on | off |
| admin mode needs TOTP | yes | no |
| gunicorn `--reload` | no | yes |

### Options

Set these as environment variables when running the installer:

| Variable | Default | |
|---|---|---|
| `TIPPR_USER` | `$SUDO_USER` | user tippr runs as |
| `TIPPR_DOMAIN` | `tippr.local` | the site's domain; must contain a dot |
| `TIPPR_ENVIRONMENT` | `auto` | `production`, `development` or `auto` (above) |
| `TIPPR_SITE_NAME`, `TIPPR_SITE_DESCRIPTION`, `TIPPR_CONTACT_EMAIL` | | site name, front page title and description, contact address |
| `TIPPR_WEB_WORKERS` | CPU count, at most 8 | gunicorn workers |
| `TIPPR_SEARCH` | `opensearch` | `none` skips OpenSearch ([SEARCH.md](SEARCH.md)) |
| `TIPPR_STARTER_FEEDS` | `auto` | starter feeds for the starter vaults: `auto` adds them on a new site and keeps the site's choice after that, `1` on, `0` off; upgrades add only feeds new to the list ([CONTENT.md](CONTENT.md#feeds)) |
| `TIPPR_PAGE_CACHE_SECONDS` | `30` | how long nginx keeps a page for logged-out visitors ([below](#caching)); `0` off |
| `TIPPR_SERVER_NAME` | the host name | this server's name on /admin/servers (servers are also told apart by machine id) |
| `TIPPR_WEB_UPDATES` | `1` | `1` lets an admin update this server to a new release from /admin/servers (`tippr-update.timer`, as root; only installs with `tippr-firstboot`, a Proxmox container's), `0` turns it off ([PROXMOX.md](PROXMOX.md#updating-from-adminservers)) |
| `TIPPR_RELEASE_REPO` | `TechIdiots-LLC/tippr` | the GitHub repository releases and updates come from (owner/name) |
| `TIPPR_MEMCACHED_MB` | `auto` | memcached's memory: `auto` is a quarter of the RAM, 64 to 1024 MB |
| `TIPPR_MEMCACHED_SERVER` | `127.0.0.1:11211` | the memcached the site uses; with several frontends, a shared one ([below](#several-servers)) |
| `TIPPR_MEMCACHED_LISTEN`, `TIPPR_MEMCACHED_ALLOW` | `127.0.0.1` | on a shared cache server: its private address, and the frontends' range (let through the firewall) |
| `TIPPR_OPENSEARCH_HEAP` | `1g` | OpenSearch's Java heap |
| `TIPPR_OPENSEARCH_START_TIMEOUT` | `10min` | How long systemd waits for OpenSearch to start (it grows with the index) |
| `TIPPR_TLS_CERT`, `TIPPR_TLS_KEY` | | certificate and key to use, e.g. a Cloudflare Origin Certificate |
| `TIPPR_LETSENCRYPT_EMAIL` | | get a Let's Encrypt certificate (the domain must point here) |
| `TIPPR_BEHIND_CLOUDFLARE` | `0` | `1`: take client IPs from `CF-Connecting-IP`, from Cloudflare's ranges only |
| `TIPPR_EXTERNAL_PROXY` | | behind another proxy that does TLS (e.g. HAProxy on OPNsense or pfSense): its address(es), e.g. `192.168.1.1`. nginx then serves plain HTTP on port 80 and trusts `X-Forwarded-For` from those addresses only ([below](#behind-another-proxy)) |
| `TIPPR_FIREWALL`, `TIPPR_SSH_PORT` | `0`, `22` | `1`: ufw allowing only SSH, HTTP and HTTPS |
| `TIPPR_DB_PASSWORD`, ... | generated | override a generated password |
| `TIPPR_MEDIA_STORAGE` | disk | `s3`: keep uploads in an S3-compatible bucket ([STORAGE.md](STORAGE.md)) |
| `TIPPR_PLUGINS` | `about gold` | reddit-style plugins, used only if their checkout is in `$TIPPR_HOME/src` (none is by default; tippr's own features don't need them) |
| `TIPPR_BUILD_MCROUTER` | `0` | `1`: build mcrouter from source (20+ minutes; not used by default) |
| `TIPPR_BRANCH`, `TIPPR_COPY_LOCAL` | | install a branch, or copy a local checkout instead of cloning |
| `TIPPR_YES` | | `1`: don't ask before starting (also skipped when there's no terminal) |

Without a certificate option, the installer makes a self-signed
certificate. That suits `.local` test sites.

### Passwords and secrets

The installer generates passwords for PostgreSQL, RabbitMQ, ZooKeeper and
the admin account, plus the site's signing secrets. It keeps them in
`/etc/tippr/secrets.env`, readable by root only, and writes them into
`r2/development.secrets`. The admin account is `tippr` (or
`TIPPR_ADMIN_USER`), and its password is in `secrets.env` as
`TIPPR_ADMIN_PASSWORD`.

## After installing

To check the services are up and the site answers (after an update too):

```bash
sudo /home/tippr/src/tippr/scripts/smoke_check.sh   # TIPPR_HOME/src/tippr
```

It checks each service this server runs, a few pages (the front page,
login, the API, an error page) and the web app's log, and says what
failed. Every server also runs it every 5 minutes
(`tippr-monitor.timer`) and can tell you when it starts failing, every 6
hours while it does, and when it's working again: give the installer
`TIPPR_ALERT_WEBHOOK` (a Discord or Slack webhook, an ntfy topic, or any URL
taking JSON) and/or `TIPPR_ALERT_COMMAND` (a command such as `mail`; see
`install.cfg`). Without them, failures are only in `journalctl -u
tippr-monitor`.

Then:

1. **DNS.** Point the domain at the server. For a test site, add a hosts
   entry on your computer, e.g. `192.168.1.50 tippr.local`.
2. **Log in** as the admin account. In production, set up two-factor
   authentication under preferences → security; admin mode needs it.
3. **Admin mode:** `/adminon`. Then:
   - `/admin/site`: the site's name, description, contact address and
     logo.
   - `/admin/antispam`: spam protection. tippr's image captcha is on by
     default; a modern captcha (Cloudflare Turnstile, hCaptcha or
     reCAPTCHA) and CleanTalk need keys from those services.
   - `/admin/email`: outgoing email ([EMAIL.md](EMAIL.md)). Without it,
     verification and password-reset emails aren't sent.
   - `/admin/ads`: Google AdSense, if you want ads ([below](#google-adsense)).
   - `/admin/payments`: PayPal, Stripe, Coinbase or BitPay, to sell gold
     and ads ([gold-payments.md](gold-payments.md)).
   - `/admin/feeds`: the feeds that post into vaults. The installer adds
     the starter feeds for the starter vaults on a new site
     (`TIPPR_STARTER_FEEDS`, [CONTENT.md](CONTENT.md#feeds)).
   - `/admin/logins`: "sign in with" Google, Facebook, GitHub, Discord or Apple, with your own
     OAuth app from each (optional).
   - `/admin/config`: the live settings (who's staff, captcha and vault
     creation thresholds, sidebar and welcome messages).
   - `/admin/backups`: backups ([BACKUP.md](BACKUP.md)).
4. **Starter vaults** and front page defaults are created by
   `scripts/create_default_vaults.py`, which the installer runs
   ([CONTENT.md](CONTENT.md)).

## What gets installed

### systemd units

`tippr.target` is the whole stack. Every unit below is part of it, so
`tippr-start`, `tippr-stop` and `tippr-restart` (or `systemctl ...
tippr.target`) cover them all.

- `tippr-paster.service`: the web app (gunicorn on 127.0.0.1:8001).
- `tippr-websockets.service`, `tippr-activity.service`: live updates and
  activity counts.
- `gunicorn-geoip.service`: geoip. (Clicks on sponsored posts go through
  the web app's `/click`.)
- `tippr-consumers.service` starts the `tippr-consumer-<queue>@<n>.service`
  queue processors. The number per queue comes from the files in
  `$TIPPR_HOME/consumer-count.d`; apply a change with
  `systemctl reload tippr-consumers`.
- `tippr-job-*.timer`: scheduled maintenance jobs. List them with
  `systemctl list-timers 'tippr-job-*'`. Among them: `tippr-job-feeds`
  (posts new feed items), `tippr-job-email` (sends queued email),
  `tippr-job-update_gold_users` (ends gold when it runs out),
  `tippr-job-vault_similarity` (Explore's recommendations),
  `tippr-job-year_clubs` (the X-Year Club trophies) and
  `tippr-job-cleanup_posts` (the post cleanup's rules from /admin/cleanup).

Not part of `tippr.target`:

- `tippr-backup.path` and `tippr-backup.service` run requests from
  /admin/backups ([BACKUP.md](BACKUP.md)).

Packaged services: `postgresql`, `cassandra`, `zookeeper`,
`rabbitmq-server`, `memcached`, `opensearch`, `nginx` (and
`redis-server`, which r2 doesn't currently use).

### Web front end

- **nginx** (`/etc/nginx/sites-available/tippr`, with
  `snippets/tippr-locations.conf` and `conf.d/tippr-*.conf`) is the only
  web server. It terminates TLS on port 443 and redirects port 80 to it,
  routes websocket upgrades to the websockets service, serves media
  (`/srv/www/media`) and the tracking pixel, and passes everything else to
  the app, shielding gunicorn from slow clients. (Earlier installs also ran
  haproxy; re-running the installer turns it off.)

### Behind another proxy

If something else in front does TLS, such as HAProxy on OPNsense or pfSense, a cloud
load balancer or another nginx, set `TIPPR_EXTERNAL_PROXY` to its
address(es), separated by spaces or commas:

```bash
TIPPR_EXTERNAL_PROXY=192.168.1.1 TIPPR_USER=tippr TIPPR_DOMAIN=example.com ./install-tippr.sh
```

For a high-availability pair (CARP on OPNsense or pfSense, keepalived), list
both nodes' own addresses on this server's network as well as the shared
virtual IP: the proxy usually connects from the active node's own address,
not the VIP. For example, `TIPPR_EXTERNAL_PROXY="172.16.1.2 172.16.1.3 172.16.1.1"`.
Avoid trusting a whole subnet, since any machine on it could then claim
any client address.

nginx then serves plain HTTP on port 80, with no certificate here, and
takes each visitor's address from `X-Forwarded-For`, but only on
connections from those addresses. With Cloudflare in front of that proxy,
add `TIPPR_BEHIND_CLOUDFLARE=1` too. On the proxy:

- send everything for the domain to this server's port 80, and redirect
  plain HTTP to HTTPS there;
- add `X-Forwarded-For` (HAProxy: `option forwardfor`); requests count as
  HTTPS unless the proxy sends `X-Forwarded-Proto: http`;
- allow long-lived connections for websockets (HAProxy:
  `timeout tunnel 1h`);
- optionally, health-check `GET /health`.

Don't expose port 80 directly to the internet in this mode: anyone
reaching it would get plain HTTP.

### Commands in /usr/local/bin

| Command | |
|---|---|
| `tippr-start`, `tippr-stop`, `tippr-restart [unit]` | the whole stack, or one unit |
| `tippr-run script.py` / `tippr-run -c '...'` | run Python with the app loaded |
| `tippr-shell` | an interactive shell with the app loaded |
| `tippr-flush` | empty memcached |
| `tippr-backup` | export, import and restore ([BACKUP.md](BACKUP.md)) |
| `tippr-serve` | run the app in the foreground with reloading (development) |

### Files

| Path | |
|---|---|
| `$TIPPR_HOME/src/tippr` | the code |
| `$TIPPR_HOME/venv` | the Python virtualenv |
| `r2/development.update` | the site's settings; run `make ini` in `r2/` after editing |
| `r2/development.secrets` | generated by the installer; don't edit |
| `r2/run.ini` | the config the app runs with (generated) |
| `/etc/tippr/secrets.env` | generated passwords and secrets (root only) |
| `/etc/tippr/tls` | TLS certificate and key |
| `/etc/default/tippr` | environment for the systemd units |
| `/srv/www/media` | uploaded media |
| `/srv/www/static` | the CSS, JS and images nginx serves (production) |
| `/var/cache/nginx/tippr-pages` | logged-out pages nginx keeps a while |
| `/var/lib/tippr/backups` | backups |

## Caching

- **Inside the app** (unchanged from reddit): posts, comments, listings
  and the rendered pieces of pages are kept in memcached and reused for
  everyone. Size it with `TIPPR_MEMCACHED_MB`.
- **Static files**: in production nginx serves `/static/` from
  `/srv/www/static`. Files whose name carries a content hash
  (`tippr.cDFoRR5NTrs.css`) are cached by browsers and CDNs for a year,
  others for a day.
- **Logged-out pages**: the app marks a logged-out page cacheable for
  `logged_out_page_cache_seconds` (30) when nothing on it is for that
  visitor only, and nginx serves it again until then
  (`TIPPR_PAGE_CACHE_SECONDS`). Logged-in visitors, pages that set
  cookies and errors always come from the app. A CDN in front (for
  example Cloudflare, with `TIPPR_BEHIND_CLOUDFLARE=1`) can do the same:
  cache `/static/` and, for requests without the `tippr_session` cookie,
  HTML as the `Cache-Control: public, s-maxage=…` header says.

## Several servers

Run the installer on each, with the same settings and data store
addresses. For caching:

- **One memcached for all the frontends.** The caches are cleared when
  things change, and two-factor sign-ins, passkey checks and rate limits
  are kept there, so every frontend must use the same one. On the cache
  server: `TIPPR_MEMCACHED_LISTEN=<its private address>` and
  `TIPPR_MEMCACHED_ALLOW=<the frontends' range>` (memcached has no
  password: never expose it beyond a private network). On each frontend:
  `TIPPR_MEMCACHED_SERVER=<cache server>:11211`. Beyond one cache server,
  mcrouter (`TIPPR_BUILD_MCROUTER=1`) spreads keys over several.
- **Static files** stay on each frontend; upgrades add the new build's
  files and keep the old ones, so upgrading frontends one at a time works.
- **Logged-out pages**: each frontend's nginx keeps its own copies; a CDN
  or a caching proxy in front of all of them shares one copy instead.
- **/admin/servers** shows every server (each reports itself once a
  minute): version, load, memory, disks and services, flagging ones that
  went quiet, are short of space or memory, or run a different version.
  Give each a name with `TIPPR_SERVER_NAME`.

## Google AdSense

tippr can show Google AdSense ads from your own AdSense account. No IDs
are built in, and ads are off until you set them up.

1. In AdSense, add your site and note your publisher ID (`pub-…`).
2. For tippr's own slots, create two ad units: a display unit for the
   sidebar and an in-feed (or display) unit for post listings. Phones see
   only the listing unit, because the sidebar is hidden on narrow screens.
   Alternatively, use Google's Auto ads and skip the units.
3. On **/admin/ads**, enable ads, enter the publisher ID, choose the
   placement, enter the ad unit IDs (and the in-feed unit's layout key),
   and save. Changes apply immediately. Use **test mode** while setting up.
   The in-feed ad repeats every "posts between in-feed ads" posts, on
   pages infinite scroll adds too.
4. `/ads.txt` is served automatically once a publisher ID is saved.
5. **Night mode** (optional): ads are drawn by Google and can't be restyled
   by the site, so on night mode's dark pages they keep their AdSense
   colours. Create units with dark colours in AdSense (an in-feed unit's
   colours are chosen when you create it) and enter them under "night mode
   ad units"; members with night mode on get those.
6. In the EU, UK and Switzerland, Google requires a consent message. Create
   one in AdSense under **Privacy & messaging**. Also mention advertising
   cookies in your privacy policy.

Ads are never shown:

- in NSFW or quarantined vaults, on NSFW posts, or in listings that include
  NSFW posts;
- in vaults whose moderators turned ads off;
- to gold members who chose to hide ads.

The same settings can go in the ini (`use_adsense`, `adsense_id`,
`adsense_mode`, `adsense_sidebar_slot`, `adsense_listing_slot`,
`adsense_listing_layout_key`, `adsense_listing_position`,
`adsense_test_mode`; see `example.ini`). Settings saved on /admin/ads
override the ini. `disable_ads = true` turns all ads off regardless.

## Troubleshooting

- **Logs:** `journalctl -u tippr-paster -f` for the web app;
  `journalctl -u 'tippr-consumer-*' -f` for the consumers.
- **Status:** `systemctl list-units 'tippr*'` and `systemctl --failed`.
- **Locale errors** creating the PostgreSQL database:
  `localedef -i en_US -f UTF-8 en_US.UTF-8`.
- **Cookies don't stick:** the domain needs a dot. Browsers don't keep
  cookies for `localhost` or a bare `tippr`.
