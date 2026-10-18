# Changelog

## master
### ✨ Features and improvements
- _...Add new stuff here..._
- **Support queue** (`/admin/support`, first stage, admins only): "message the admins" now goes to a private admin
  vault (`admin_message_acct = /v/siteadmins`, created by the installer), and each conversation becomes a ticket with
  a category (from the contact page's `[privacy]`, `[appeal]`, ... subject tags), a status (new, open, waiting on the
  member, closed), an assignee and a history. Staff reply from the queue as the admin team; members see
  /v/siteadmins, not the staff member's name. Members in timeout can reach the admins again (that only ever worked
  when `admin_message_acct` was a vault).
- **Gold is ad-free by default**: AdSense, promoted posts and the sponsor box are hidden for gold members unless they
  untick "hide ads" in their gold options (it used to be off until they found it).
- **Hide multivaults**: a "hide" link on the side panel's multivaults section, and a preference to bring it back.
- **The promoted tab** only appears when something is being promoted there (or for sponsors).

### 🐞 Bug fixes
- _...Add new stuff here..._
- **Deleting a multivault** did nothing (the delete failed on the Cassandra compatibility layer, which didn't accept
  pycassa's consistency level arguments). The same affected promoted-post metrics and the wiki's image count, which
  also failed for pages without images.
- **Gold support** messages (expiry notices, payment and subscription problems, gift code errors) named
  `goldsupport_email`, empty by default, so they read "write to us at ." They link to a new gold section of the
  contact page instead, which offers a message to the admins and shows the address when one is set.
- **/explore** failed with an error (Python 2 division), as could `median()`, gold gift codes and the Solr provider.
- **The gilded tab** had no side panel.
- **Sample multis** in the side panel (`/user/tippr/m/hello` and `world`) led to "page not found"; only samples that
  exist and are public are shown, and the defaults are empty.
- **The promoted tab** showed reddit's "This is a placeholder ad." page, and the real listing then failed on a
  memcached key with spaces (the front page's name).
- **Newsletter**: the newsletter bar, the sign-up form's "get the best of tippr emailed to you" checkbox and
  /newsletter only appear when a newsletter is set up (`newsletter_api_key` and `newsletter_list_id`); without one
  they offered something that didn't exist. A link on the email settings page that subscribed people to reddit's own
  advertising mailing list is gone.

## 0.5.0
### ✨ Features and improvements
- **/admin/config**: change the live config (the admin and employee list, captcha and vault-creation thresholds,
  sidebar and welcome messages, and the rest of `[live_config]`) without editing the ini. Values are checked against
  each setting's type, apply right away on every web process, can be undone back to the ini's value, and every change
  is logged with who made it. You can't remove your own admin permission there.
- **More on /admin/site**: the front page's title and a title format for every other page (`{title} | {site}`),
  Google and Bing verification tags, a favicon, a share image for link previews of the front page and vaults, a
  dismissible announcement banner, and a switch to close sign-ups. All apply right away, without editing the ini.
- **Sitemaps**: `/sitemap.xml` is served by the site itself (public vaults and the newest posts, cached for an hour)
  and listed in robots.txt. reddit's version only uploaded to S3.
- **Sharing**: the share menu adds Bluesky, Mastodon (asks for your server once and remembers it), X and LinkedIn,
  plus the device's own share sheet where the browser has one, and a copy button for the link. Facebook now uses its
  plain share link, which needs no Facebook app (the old dialog failed without `facebook_app_id`), and Threads uses
  threads.com.

### 🐞 Bug fixes
- **Policies and contact details were tippr.net's**: every install's user agreement, privacy and content policies and
  moderator guidelines named TechIdiots LLC, tippr.net, Massachusetts law and six @tippr.net addresses, and the privacy
  pages, export emails and rate-limit page pointed at more. The policies are now templates filled in from /admin/site
  (site name, domain, and new **operator** and **governing law** fields), and everything that told people where to
  write links to a section of the contact page instead, which offers a pre-filled message to the admins (privacy,
  copyright and legal, appeals, serious content reports, moderator help, rate limits) and the contact address when one
  is set. The sample config no longer points share, feedback and ads mail at tippr.net or a stranger's Gmail address.
  Existing policy pages aren't changed; rebuild them with
  `sudo env FORCE_POLICY_IMPORT=1 tippr-run /home/tippr/src/tippr/scripts/init_policy_wiki_pages.py`.
- **Link previews** said "tippr" whatever the site's name, and vault and post previews showed `â€¢` instead of `•`.
- **robots.txt** still used reddit's `/r/` paths, and its `Disallow: /*.xml` would have hidden the sitemap.

## 0.4.0
### ✨ Features and improvements

### 🐞 Bug fixes
- **Proxmox first boot**: systemd applies unit presets on a container's first start (the template has no machine ID),
  which enabled and started every tippr unit before `tippr-firstboot` ran. Their jobs recreated ZooKeeper nodes with the
  template's password, and the first boot failed with `NoAuthError`. The template now ships a preset that keeps them
  off, and `tippr-firstboot` stops any that are running before it resets ZooKeeper.
- **Installer under `pct exec`**: it put its helpers in /usr/local/bin and then couldn't find them, since `pct exec`
  runs commands with a PATH that leaves that out. The installer and `tippr-firstboot` now set their own PATH.
- **Static build**: `tippr.less` sometimes failed to build with "variable @color-white is undefined" (or
  `@tp-link-hex`), depending on disk timing. `variables.less` was imported twice, and LESS 1.4 races the two copies
  and can drop the colours or theme with them. It's now imported once.
- **Captcha services in the sign-up popup**: with Turnstile, hCaptcha or reCAPTCHA chosen, the widget's `<script>`
  tag ended the popup's template early, so half the sign-up form and the whole log-in form appeared at the bottom of
  every page. The service's script now loads once per page and draws each widget when its form is shown.
- **Logging out from an admin page** went to "page not found" (admin pages 404 for everyone else); it now goes to the
  front page.

## 0.3.0
### ✨ Features and improvements
- **nginx only**: the installer no longer runs haproxy in front of nginx; nginx routes websockets, media and the app
  itself. `TIPPR_EXTERNAL_PROXY` runs it behind another proxy that does TLS (e.g. HAProxy on OPNsense or pfSense), with real
  client addresses from that proxy.

### 🐞 Bug fixes

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
- **Several app servers can share a site**: scheduled jobs take a ZooKeeper lock, so each runs on one server at a
  time.

### 🐞 Bug fixes
- **Signing up and changing passwords failed** (a Python 3 bytes/text mix-up in password hashing).
- Python 3 fixes across the codebase: image uploads, the hardcache, route arguments, generators, multi-vault
  listings (/v/mod), canonical links and more.

