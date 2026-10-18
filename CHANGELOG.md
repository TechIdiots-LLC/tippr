# Changelog

## master
### ✨ Features and improvements
- _...Add new stuff here..._

### 🐞 Bug fixes
- _...Add new stuff here..._

## 0.2.0
### ✨ Features and improvements
- **Releases**: each version is published as a Docker image (Docker Hub), a Docker Compose bundle, an installer
  tarball and a Proxmox LXC template, all built and tested by the release workflow. See docs/RELEASING.md.
- **Docker Compose**: the whole site in containers, one per role (web, consumers, jobs, websockets, activity,
  GeoIP), with PostgreSQL, Cassandra, ZooKeeper, RabbitMQ, memcached, OpenSearch and Redis, behind Caddy with
  automatic HTTPS. See docker/README.md.
- **Proxmox template**: create a container with the site's domain as its hostname and start it; the first boot sets
  the site up with its own passwords, secrets and certificate. See docs/PROXMOX.md.
- **Backups and moving servers**: /admin/backups and `tippr-backup` export the whole site (database, Cassandra,
  saved settings, media, signing secrets), copy a backup from another server over HTTPS with a transfer key, and
  restore it. See docs/BACKUP.md.
- **Admin pages**: the site's name, description, contact address and logo (/admin/site), outgoing email
  (/admin/email), Google AdSense with your own IDs (/admin/ads) and recent errors (/admin/errors).
- **Search** with OpenSearch, including typo tolerance and the vault:, author:, site: and nsfw: filters.
- **AI content labels**: every post is marked human-made, AI-assisted or AI-generated; vaults can limit them and
  users can hide them.
- **Comments**: a formatting toolbar, previews and :shortcode: emoji.
- **A welcoming default community**: starter vaults leaning toward technology, science, making things and fun,
  including LGBTQ+; the content policy names the identities its hate rules protect.
- **A new look**: the teal theme, Noto Sans and the tippr bot.
- **Spam protection** (/admin/antispam): choose the captcha — tippr's own, Cloudflare Turnstile, hCaptcha or Google
  reCAPTCHA — now also on the sign-up form, and use CleanTalk to check sign-ups, posts, comments and messages from new
  accounts without a challenge (spam is hidden in the moderators' spam queue).
- **nginx only**: the installer no longer runs haproxy in front of nginx; nginx routes websockets, media and the app
  itself. `TIPPR_EXTERNAL_PROXY` runs it behind another proxy that does TLS (e.g. HAProxy on pfSense), with real
  client addresses from that proxy.
- **Several app servers can share a site**: scheduled jobs take a ZooKeeper lock, so each runs on one server at a
  time.

### 🐞 Bug fixes
- **Signing up and changing passwords failed** (a Python 3 bytes/text mix-up in password hashing).
- Python 3 fixes across the codebase: image uploads, the hardcache, route arguments, generators, multi-vault
  listings (/v/mod), canonical links and more.

