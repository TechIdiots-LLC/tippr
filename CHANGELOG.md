# Changelog

## master
### ✨ Features and improvements
- _...Add new stuff here..._
- **Media in an S3-compatible bucket** (optional): uploaded media (thumbnails, vault images and stylesheets, the
  site's images, ad images) can live in Garage, SeaweedFS, MinIO, Amazon S3 or a similar service instead of
  `/srv/www/media`, for sites with more than one frontend server or more media than one disk. Set it up with the
  installer's `TIPPR_MEDIA_STORAGE=s3` and `TIPPR_S3_*` settings; nginx still serves media at `/media/`, so links
  don't change. `scripts/migrate_media_to_s3.py` copies existing media across. Without these settings nothing
  changes. See docs/STORAGE.md, which includes setting up Garage on Proxmox.
- **More starter feeds**: `scripts/starter_feeds.txt` now has about 80 public feeds for the default vaults (news,
  business, science, technology, security, gaming, webcomics, blogs, culture, art …). `FEEDS_SYNC=1` makes
  `scripts/import_feeds.py` bring the bot's feeds in line with the list after you reorganize it: feeds no longer
  listed (or listed for another vault) are removed, and the rest are left alone so they don't post again. New starter
  vaults: /v/comics and /v/cybersecurity (front page defaults), /v/business, /v/design, /v/curated and /v/blogs (not
  defaults); re-run `scripts/create_default_vaults.py` to make them.

### 🐞 Bug fixes
- _...Add new stuff here..._
- **S3 media**: uploading the site logo, favicon or share image failed with S3 storage, and the ad image list
  failed to load; S3 uploads work without Amazon's ACLs and with other providers' addresses.
- **/admin/site images**: choosing a logo, favicon or share image now uploads it straight away (it was easy to pick
  one and press the page's save button, which only saves the text settings), with a note saying so. The Google and
  Bing verification fields refuse an AdSense publisher ID (ca-pub-…), which belongs on /admin/ads. The fields on
  /admin/site, /admin/ads and the other settings pages are no longer cramped against each other.
- **On phones**: the vault search on /vaults (and the search page's box) was squeezed into a narrow column; the
  subscribe buttons on /vaults took a wide column of their own; and the subscribed/explore/multivaults menu had moved
  into the menu drawer. It stays on the left again, collapsed to its edge, and opens over the page when tapped
  (without changing whether it's collapsed on a computer).
- **The welcome panel** showed on any empty list (an empty inbox, saved posts, top posts of the past hour …); it's now
  only on an empty front page or vault (hot, new and rising).

## 0.8.0
### ✨ Features and improvements
- **Google Analytics** (optional): paste a Google Analytics 4 measurement ID (G-…, or the whole tag) on /admin/site,
  under analytics, to add Google's tag to every page. It isn't loaded for visitors whose browser sends Do Not Track or
  Global Privacy Control, and IP addresses are anonymized. reddit's old analytics code (Universal Analytics, which
  Google shut down) and its ini settings are gone; `google_analytics_id` in the ini works as a default.
- **Traffic stats work**: the site now counts its own traffic, so /traffic (for admins) and each vault's traffic
  stats (for its moderators, or everyone if the vault allows) show real pageviews and unique visitors by hour, day and
  month, plus new subscriptions per day. reddit filled these pages from a separate data pipeline, so they were always
  empty here. Pages are counted as they're served (not bots, feeds, the API or errors) and written every 30 seconds in
  the background; a visitor is counted by a hash of their account or, logged out, their address and browser, so no
  addresses are stored. The installer now enables tippr-job-subscribers (hourly) for the subscription counts.
- **Help pages** (/help): a FAQ and pages on searching, formatting, RSS feeds, trophies, timeouts and suspensions,
  quarantined vaults, muting, the API, advertising and translating, written for any site (they're in `docs/help/` and
  use the site's name from /admin/site). The installer loads them into the site wiki like the policies; admins can
  edit them at /wiki/help/<name>. The site's help links (search help, formatting help, the API rules, "what's this?" on
  trophies, the timeout banner, quarantine notices, muting messages …) pointed at reddit's wiki, reddit's Zendesk or
  /r/ pages; they now point here, and /faq goes to /help/faq. The unused "allow my data to be used for research"
  preference is gone, and the timeout banner now says "timeout" rather than "suspended".
- **Banned domains** (/admin/domains): admins can ban a domain (and its subdomains) so its links are either refused
  at the submit form, with a reason the member sees, or accepted and removed as spam without a word, for spammers who'd
  just try another address. Each domain has an admin page (/admin/domain/<domain>, the small "d" beside a post's
  domain) with the ban, who posts it and its recent links. Domain bans were part of reddit's private plugin and did
  nothing here before.
- **Staff notes and activity in the support queue**: staff can leave notes on a ticket for each other (what they
  checked, who should take it); notes show in the conversation, marked as internal, and are never sent to the
  member. Anyone who can see a ticket can leave one, including staff who can only read it. A ticket also lists the
  member's other tickets, and its history reads as sentences ("marked it closed", "assigned it to …").
  /admin/support/activity shows who's been helping (replies, notes and closed tickets over 7 and 30 days) and the
  latest actions, for everyone or one person, in the categories you can see.
- **Starter feeds**: `scripts/import_feeds.py` adds many feeds to /admin/feeds at once from a list, and
  `scripts/starter_feeds.txt` has about 50 public news, technology, culture and art feeds for the default vaults.
  It's a dry run until `FEEDS_ADD=1`; a line can give a site's homepage instead of its feed when the page links to
  one, and vaults that don't exist yet are reported. To use it:
  `sudo env FEEDS_ADD=1 tippr-run /home/tippr/src/tippr/scripts/import_feeds.py`.
- **Support staff** (/admin/support/staff): people other than the admins can now help with the support queue, each only
  in the categories you choose, to read or to read and reply. So someone answering moderator questions doesn't see
  privacy or legal requests. They must be on the employees list (/admin/config, `name:employee`) and have two-factor
  sign-in on; they get a "support" link at the top of every page. Their replies still reach members as the admin
  team. Tickets can also be assigned to anyone who may reply in their category.
- **More tools on /admin/users/<name>**: the overview shows the address the account registered from and when it was
  last active. A quick tools menu removes all their posts and comments (or removes them as spam, or deletes them),
  requires them to verify their email again, or removes their email address. **Delete account** deletes it for good,
  keeping or deleting their posts and comments: their sessions and app tokens end, and their password, email and
  moderator roles go right away instead of after the 90 days a self-deleted account gets. Each is logged with the
  other admin actions.
- **The normal site works on phones** (first step towards dropping the separate mobile interface). Pages now size to
  the device instead of a 1024px-wide desktop page shrunk to fit. On phones (768px or narrower):
  - the vault bar and the sort tabs are rows you swipe sideways;
  - a menu button in the header opens a drawer with the account links, the sidebar (search, submit buttons, vault
    info, moderation tools) and the multivault list; logged-out visitors also get a "Log in or sign up" button;
  - posts, comments, the submit form, preferences, the inbox and search use the full width, with bigger text and
    touch targets and shallower comment indents; images, code and tables no longer run off the screen.

  On tablets the sidebar stays beside the content (before, it disappeared below 960px), and the account links no
  longer cover the sort tabs. The "switch to mobile version" banner is gone, and m./simple. addresses and `.mobile`
  pages now go to the same page on the normal site. The compact interface (`.compact`, `i.`) is still there, but
  nothing promotes it any more.

### 🐞 Bug fixes
- **Lookups with nothing to find** (an empty list of IDs) failed with an SQL error instead of finding nothing; among
  other things this broke the sponsor pages (/sponsor, /sponsor/promoted/…).
- **Subscription counts** for the traffic pages couldn't be read back (their table is keyed by text, not dates).
- **Pages that failed to load**, mostly leftovers from renaming reddit's subreddits to vaults: composing a message
  (from the inbox, or "message the moderators"), /vaults/featured, the privacy settings page for anyone who hadn't made
  a privacy request, and listings that suggest a random vault (which could break the front page). Also fixed: a vault's
  related-vaults setting, wiki edit checks for vaults that use karma, and the "too many vaults" error not showing.
- **Links**: a vault's about pages (moderators, settings, log …) gave search engines a canonical address without the
  vault, which went nowhere; the admin tools menu linked through the current vault or filter, which broke under
  /me/f/; "message the moderators" and the account deactivation page's "contact us" pointed at /r/ addresses; and the
  "exclude custom vaults" link on /v/all showed to visitors who aren't logged in, for whom it 404s. reddit's 2016 ad
  auction notice is gone from the ad pages.
- **Deleting a multivault** left you on its page, which then gave a 404; it now goes to the front page.
- **Deleting a post** failed in a vault that had never had a sticky post.
- **The welcome panel** on an empty listing was squeezed into a narrow column; it's now as wide as the listing.
- **The compact and old mobile interfaces** failed to load (leftovers from renaming reddit to vault, and Python 2 code).

## 0.7.0
### ✨ Features and improvements
- **Feed bots** (/admin/feeds): post new items from RSS or Atom feeds to vaults, e.g. a blog's articles or a project's
  releases, to give a new site something to read. Each feed has a vault, a bot account that posts it (made if it
  doesn't exist; its posts and comments show [bot] beside its name), an interval (15 minutes at least) and an optional
  title prefix. Check now, pause, edit or delete a feed from the page. A new feed posts only its newest 3 items and
  later checks at most the newest 5, so a vault isn't flooded; an item is never posted twice. The new
  tippr-job-feeds timer checks them every 15 minutes.
- **Gold now expires**: the installer enables tippr-job-update_gold_users (it was off by default), which ends gold
  when it runs out, and warns 3 days before.
- **A welcome instead of "nothing here"**: an empty front page or /v/all shows the site's name and description,
  buttons to submit a link or text post and the most subscribed vaults to explore; an empty vault invites people to
  post there.
- **CleanTalk statistics** on /admin/antispam: the CleanTalk account (as CleanTalk shows it), whether the key is valid,
  paid-until and trial status, the last check, the last 7 days' checks by outcome (allowed, spam sign-ups, spam
  posts, comments or messages, unreachable) and the average response time.
- **CleanTalk: check users for spam** (/admin/antispam): checks existing accounts' email addresses and last login
  addresses against CleanTalk's blacklists in batches (`spam_check`), remembering the results so each run carries on
  where the last stopped ("start over" checks everyone again). Flagged accounts are listed with how many sites
  reported them and when, for an admin to dismiss, suspend, or suspend and remove their content as spam.
- **Account actions on /admin/users**: put an account in a timeout (for a number of days or until lifted; it's told
  why and can still message the admins), suspend it (it can't log in; its sessions and app tokens end), lift either,
  remove its posts and comments as spam, or reset two-factor for someone locked out. Each action is logged on the
  account with who did it and why. Admin accounts are protected. These replace reddit's private admin tools.
- **/admin/users** (admins only): find accounts by username (exact, then names starting with it), email address or IP
  address, and see an account's email and verification, two-factor and gold status, the IP addresses it logged in
  from in the last 100 days with other accounts seen on them, the vaults it moderates and its support tickets. Logins
  and sign-ups now record the IP address (public addresses only, kept 100 days); before, only password resets did.
- **/admin/apps**: every API app registered on /prefs/apps, with its developers, type and redirect address. Admins can
  approve, suspend (with a reason its developers see) or delete one; a suspended app's tokens stop working at once.
  New apps can wait for approval (`apps_require_approval`, on by default), working only for their own developers
  until then, and registering one needs an account 7 days old with 10 karma and a verified email (`app_create_*`).
  All four are on /admin/config; admins are exempt.
- **Support queue** (`/admin/support`, first stage, admins only): "message the admins" now goes to a private admin
  vault (`admin_message_acct = /v/siteadmins`, created by the installer), and each conversation becomes a ticket with
  a category (from the contact page's `[privacy]`, `[appeal]`, ... subject tags), a status (new, open, waiting on the
  member, closed), an assignee and a history. Staff reply from the queue as the admin team; members see
  /v/siteadmins, not the staff member's name. Members in timeout can reach the admins again (that only ever worked
  when `admin_message_acct` was a vault).

### 🐞 Bug fixes
- **/v/random** could land on the site's working vaults (beta, takedowns, promos, advertising links, the admin
  vault). It no longer does. (NSFW vaults were already only in /v/randnsfw.)
- **Times on the admin pages** marked UTC (support history, account actions) were in the server's time zone.
- **Scheduled cleanups never ran**: the hourly `tippr-job-trylater` didn't register the app's hooks, so temporary
  vault bans and mutes never expired and deleted accounts weren't cleaned up after 90 days. Cancelling a scheduled
  item (lifting a temporary ban early) also never removed it, so it could end a newer ban later.
- **Cassandra compatibility**: batched deletes on a column family's own batch (revoking app tokens, so suspending an
  account) failed, and dates stored as milliseconds couldn't be read back.
- **Message events** failed: `events_collector_message_sample_rate` wasn't typed, so it stayed text.
- **Cassandra column ranges**: the compatibility layer treated an empty `column_start`/`column_finish` (pycassa's "no
  bound") as a bound and returned nothing, and applied bounds the wrong way round for reversed queries. Column queries
  with those defaults, such as the IP history, came back empty.
- **Authorizing an app** failed for admins and employees (reddit's `mobile_auth_allowed_clients` setting doesn't
  exist here, and `employee_approved_clients` is live config).
- **Deleting a multivault** did nothing (the delete failed on the Cassandra compatibility layer, which didn't accept
  pycassa's consistency level arguments). The same affected promoted-post metrics and the wiki's image count, which
  also failed for pages without images.

## 0.6.0
### ✨ Features and improvements
- **Gold is ad-free by default**: AdSense, promoted posts and the sponsor box are hidden for gold members unless they
  untick "hide ads" in their gold options (it used to be off until they found it).
- **Hide multivaults**: a "hide" link on the side panel's multivaults section, and a preference to bring it back.
- **The promoted tab** only appears when something is being promoted there (or for sponsors).

### 🐞 Bug fixes
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

