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
| `TIPPR_OPENSEARCH_HEAP` | `1g` | OpenSearch's Java heap |
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
   - `/admin/feeds`: the feeds that post into vaults. A new site has
     none; `FEEDS_ADD=1 tippr-run $TIPPR_HOME/src/tippr/scripts/import_feeds.py` adds
     the starter feeds for the starter vaults ([CONTENT.md](CONTENT.md)).
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
- `gunicorn-click.service`, `gunicorn-geoip.service`: click tracking and
  geoip.
- `tippr-consumers.service` starts the `tippr-consumer-<queue>@<n>.service`
  queue processors. The number per queue comes from the files in
  `$TIPPR_HOME/consumer-count.d`; apply a change with
  `systemctl reload tippr-consumers`.
- `tippr-job-*.timer`: scheduled maintenance jobs. List them with
  `systemctl list-timers 'tippr-job-*'`. Among them: `tippr-job-feeds`
  (posts new feed items), `tippr-job-email` (sends queued email),
  `tippr-job-update_gold_users` (ends gold when it runs out),
  `tippr-job-vault_similarity` (Explore's recommendations) and
  `tippr-job-year_clubs` (the X-Year Club trophies).

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
| `/var/lib/tippr/backups` | backups |

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
5. In the EU, UK and Switzerland, Google requires a consent message. Create
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
