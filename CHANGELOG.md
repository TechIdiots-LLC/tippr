# Changelog

## master
### ✨ Features and improvements
- _...Add new stuff here..._

### 🐞 Bug fixes
- _...Add new stuff here..._

## 0.28.0
### ✨ Features and improvements

### 🐞 Bug fixes

## 0.27.0
### ✨ Features and improvements
- **Comes back by itself after a reboot:** the web app, queue consumers and scheduled jobs wait for PostgreSQL,
  Cassandra, ZooKeeper, RabbitMQ, memcached and OpenSearch to answer before starting (`scripts/wait-for-stores`;
  the backend's on a frontend). They used to start at once, fail while Cassandra was still coming up, and after five
  quick failures systemd stopped trying, so the site stayed down until someone restarted it. A service that fails
  anyway is now restarted every 5 seconds, without a limit.
- **Alerts when a server's tippr stops working:** every 5 minutes each server runs the smoke check, and when it starts
  failing (and every 6 hours while it does, and when it recovers) says what failed to a webhook (Discord, Slack,
  ntfy or any URL taking JSON) and/or a command such as `mail`: the installer's `TIPPR_ALERT_WEBHOOK` and
  `TIPPR_ALERT_COMMAND`. `tippr-stop` stops it too, so maintenance doesn't page anyone.
- **The account switcher is for gold members and admins:** it's in preferences' gold options, greyed out for everyone
  else with a link to gold, and their saved choice is kept for when they get it. Any account in the switcher counts,
  so switching to an alt without gold doesn't leave you stuck on it. Adding an account that has two-factor asks for
  that account's code (or passkey) on the sign-in's code page, and the switcher offers "sign in with Google" and the
  other sign-ins on /admin/logins, for accounts that linked one.
- **Daily backups, and a copy off the server:** a backup every night (the newest 7 kept), on every install unless
  `TIPPR_BACKUP_SCHEDULE=off`. With `TIPPR_BACKUP_S3_BUCKET` each is also uploaded to that S3 bucket (Garage, MinIO,
  AWS...), under a folder of its own (`TIPPR_BACKUP_S3_PREFIX`, the domain by default), keeping the newest 30, with
  its own key if you like. `tippr-backup list --remote`, `fetch` and `upload` work with the bucket; `fetch` checks
  every file before you restore it. A failed backup sets off an alert. Backups used to be made only by hand.
- **Two-factor is asked for in one place:** once signed in, the code (or passkey) is entered on one "confirm it's
  you" page, and it then counts for 15 minutes across preferences. Deleting your account and turning two-factor off
  no longer have a code box: they need a confirmation from the last 5 minutes, and link to the page when it's older
  (the API still takes `otp`).
- **Admin mode asks for your two-factor code, not your password again:** "turn admin on" takes a code or a passkey
  each time (or nothing on a computer you chose to remember), like preferences' unlock.
- **The browser test on every push:** members logging in, posting, replying, voting, tipping scales, moderating and
  writing to the admins, in real browsers at desktop and phone width, light and night, with every page checked for
  errors and unreadable text, used to run only before a release; CI runs it on every push and pull request too
  (`ci-docker.yml`, screenshots kept as an artifact). Its admin step follows "confirm it's you".
- **Sign in with Apple:** Apple is offered next to Google, Facebook, GitHub and Discord on /admin/logins. It takes
  the Services ID, team ID, key ID and the key's .p8 text; tippr signs its own client secret from them and checks
  Apple's signed answer against Apple's published keys. Apple shares only who signed in, not a name or email.

### 🐞 Bug fixes
- **Top and controversial listings could stop updating for good after a crash:** a run of their job that was killed
  (a reboot, or running out of memory) left its temporary files behind, and every later run refused to start while
  they were there. The job uses a lock that ends with the process instead, and clears what a killed run left.
- **Signed API requests failed:** a request carrying a signature header (the v1 mobile API's request signing,
  `/api/v1/login` and `/api/v1/register`) gave an error under Python 3, and a signed body could never match, since its
  bytes were signed as text (`b'...'`). Both are signed as sent again.
- **A multi's or filter's vault list said "x" instead of "remove"** once the page's script took it over, and lost the
  vault names on its items. They match the page as it loads.
- **"Remember this computer" can be ticked before using a passkey:** the box sat below the passkey button, and a
  passkey sends the form as soon as it's used, so there was no chance to tick it. It's now above the button, on the
  sign-in code page and when turning admin mode on.

## 0.26.0
### ✨ Features and improvements
- **Paste is no longer used:** the error pages, static files and per-request objects (`c`, `g`, `request`) it
  provided are tippr's own now (`r2/config/middleware.py`, `pylons/`); PasteDeploy, which reads the ini, stays.
  Updating a server, from /admin/servers or with the installer, uninstalls Paste.
- **About 30 fewer Python packages:** baseplate no longer needs formenergy-observability, which brought in Dagster (a
  data pipeline framework) and capped `packaging` below 25; the two tracing helpers it used are in baseplate now.
  Updating a server uninstalls them, and `packaging` is current (26.3).
- **Current Python packages:** OpenTelemetry 1.45 (was 1.28), protobuf 7, Pillow 13, wrapt 2, grpcio 1.85, pytest 9,
  and python-json-logger 4 and pyrate-limiter 4 through tippr's baseplate (which now needs Python 3.10 or newer);
  the rest are at their newest too. python-dateutil stays at 2.9, as botocore needs. importlib_metadata and zipp,
  which nothing needs any more, are uninstalled on update, and so is Whoosh, a search library nothing used.
- **A check that a server's tippr is up:** `scripts/smoke_check.sh` checks the services the server runs, a few pages
  (the front page, login, the API, an error page, a POST) and the web app's log, and says what failed. The
  installer's CI runs it after installing, so an install that finishes with a broken site fails.
- **Package updates from Dependabot:** weekly pull requests for newer Python packages and GitHub Actions, with
  packages that move together (OpenTelemetry, boto3 and botocore, grpcio and protobuf) in one. CI installs the exact
  pins as a release would and tests them, and patch updates that pass are merged automatically, once master's
  ruleset requires the checks (`.github/workflows/dependabot-automerge.yml`).

### 🐞 Bug fixes
- **Domain listings (/domain/example.com) redirected to a broken address:** every one went to
  `/domain/b'example.com'/` instead of listing the domain's posts. They list them again, and an international domain
  name still goes to its `xn--` form.
- **Uploading an app's icon (/prefs/apps) gave an error:** the resized icon was written as text, which Python 3
  refuses, so no app could have an icon. It's saved as a PNG again.
- **"Exclude custom vaults" (/me/f/all) gave "you broke tippr" to gold members:** its sidebar asked for the
  filtered vaults by their name from before vaults were renamed. It lists them again, to add to or remove.
- **Filtering a vault out of /all didn't take effect for a minute, and could show someone else's filter:** the
  spread-out /v/all hot list was cached by the page's address, which is /me/f/all for every member. It's cached by
  the vaults left out now.
- **Top and controversial listings never updated when tippr runs as a user other than `tippr`:** the database
  password file named the Linux user instead of the database's, so the job that computes them couldn't connect and
  failed every 15 minutes. Updating rewrites the file.

## 0.25.0
### ✨ Features and improvements
- **One panel at a time under a post or comment:** share, scales and report opened one under another; opening one
  now closes the others there (clicking the same link again still closes its own).
- **Gold on /admin/users, including permanent gold:** an account's page shows its gold (until a date, permanent, or
  none) and lets an admin give or take months (up to 120 at once), make it permanent, or remove it (with a reason,
  after ticking to confirm), each recorded under the account's admin actions. Permanent gold doesn't run out: the
  daily expiry job and refunds leave it, and members' profiles and `/api/me` show it with no end date. The old
  `/admin/gold` form, which only added or took months, now goes to /admin/users.

### 🐞 Bug fixes
- **The API documentation by OAuth scope (/dev/api/oauth) gave an error:** endpoints any OAuth client may use are
  listed under "any" scope, which Python 3 couldn't sort with the scope names. It lists them first, as "any", again.

## 0.24.0
### ✨ Features and improvements
- **Current setuptools, without pkg_resources:** setuptools 81 deprecated `pkg_resources` and later versions remove it,
  and tippr was held below 81 by what still imported it: tippr's baseplate (now `importlib.metadata`), OpenTelemetry's
  instrumentation before 0.49 (now 1.28.2 / 0.49b2, which needs protobuf 5), the test setup's PasteScript import, and
  Pyramid 2.1, which only the activity service's HTTP gateway uses and tippr never runs (it's an optional extra of the
  activity service now). The installer's package check uses `importlib.metadata` (`scripts/check_requirements.py`),
  and the pins in the installer, Docker image, builds and CI are gone. Packages a release no longer uses are listed
  in `install/requirements-retired.txt`, and the installer, and so an update from /admin/servers, removes them: this
  one removes PasteScript, Pyramid and what came with it.
- **Account activity lists where your account is used from:** it only recorded logins, and a login cookie lasts for
  months, so the page was usually empty. Visits are recorded too now, at most once an hour for each address, kept 100
  days as before. A visit from a private network address (a home or office network reaching the site directly) isn't
  kept, and the page now says so instead of showing an empty table; an empty list says when visits will appear. The
  privacy policy's information list names this (account activity, 100 days, seen by you and the site's
  administrators, private addresses not kept), and the "accessing tippr from" line names no site.
- **/v/all mixes vaults:** it ranks every post together, so a feed's run of new posts in one vault filled it (the
  front page and multis mix vaults already). Its hot listing now never puts two posts from the same vault next to
  each other while another vault's post is within 30 places.
- **/admin/feeds can be searched, filtered and sorted:** a search box (titles, addresses, vaults, bots and title
  prefixes), menus of the vaults and bots the feeds use, and a status filter (active, paused, with errors, never
  checked, each with its count), and every column heading sorts by it (again for the other way round). It shows when
  each feed was added, newest first until another sort is chosen. The view is in the page's address, so it can be
  bookmarked and stays after a save. "Add a feed" is over the list now, and a feed's edit form opens the width of the
  table under it, with every setting, including the vault it posts to (new items go to the new vault; posts already
  made stay where they are). Long addresses and error messages wrap, so the table fits the page.

### 🐞 Bug fixes

## 0.23.0
### ✨ Features and improvements
- **Scales describe what kind of post it is, and are easier to read:**
  - Six scales, all shown at once (no "more scales"): human-made ↔ AI-generated, quick overview ↔ deep dive,
    practical ↔ thought piece, data-driven ↔ personal experience, matter-of-fact ↔ passionate and niche ↔ broad. Each
    is two ends of one difference, not a verdict: votes say whether a post is good, so helpful ↔ unhelpful is gone, as
    are beginner-friendly ↔ in-depth, practical ↔ just for fun and well-sourced ↔ opinion. Tips on human-made ↔ AI and
    the tone scale carry over; tips on the retired scales are kept (and in members' data exports) but not shown.
  - Each side shows its count beside its label, in the colour it has on the bar, with "75% deep dive · 4 tips" under
    it. With fewer than three tips there's no bar (one tip filled it with one colour): "1 tip so far: human-made".
  - A vault's moderators, and admins in admin mode, see every scale's tallies without tipping.
  - "See the results" shows a member every tally of a post without tipping, after asking: it ends their tipping on
    that post (tips they made before stay and count, and they can't tip or change one after). It's in their data
    export.
- **A check for media storage:** `tippr-run scripts/check_media_storage.py` saves a test file the way uploads are
  saved, checks it's in the bucket (with S3 storage) and not on the disk, fetches it from `/media/` through nginx, and
  deletes it: the last step of moving media to a bucket (docs/STORAGE.md).
- **The jobs and queue processors run without `paster`:** they, `tippr-run` and `tippr-shell` load the app with
  `python -m r2.commands`, and `tippr-serve` (development) runs gunicorn with reloading, so PasteScript is no longer
  installed. It's the first step in phasing out Paste (docs/ROADMAP.md); Pyramid, which tippr never used, is gone from
  r2's requirements. Commands written as `paster --plugin=r2 run INI ...` become `tippr-run ...`, or
  `python -m r2.commands INI ...` from the app's folder.

### 🐞 Bug fixes
- **Deleting media in a bucket failed:** the bucket list from the ini (`s3_media_buckets`) was read back as the text
  `('tippr-media',)`, so working out which bucket a media address belongs to gave the bucket name `('tippr-media'` and
  S3 refused it. Uploads and serving weren't affected; deleting or hiding media (and the new storage check's clean-up)
  work again.
- **`systemctl --failed` listed OpenSearch's Performance Analyzer:** the OpenSearch package turns on its metrics agent,
  which tippr doesn't use and which fails to start, so a server always had a failed unit. The installer turns it off
  (on every install, as a package upgrade turns it on again); search itself was never affected.

## 0.22.0
### ✨ Features and improvements
- **A site can be split over several servers:** the installer's `TIPPR_ROLE` makes a server the **backend**
  (PostgreSQL, Cassandra, RabbitMQ, ZooKeeper, OpenSearch, memcached, the "here now" counts, the queue processors
  and the scheduled jobs) or a **frontend** (the pages and live comments), any number of which, on any servers,
  share one backend behind a load balancer. `all`, one server doing everything, stays the default. The backend
  opens its services to the frontends' address range and writes `/etc/tippr/cluster.env`, the passwords, signing
  secrets and shared settings a frontend installs from; the Proxmox template makes either from `firstboot.env`.
  Media has to be in object storage. `/admin/servers` shows each server's role and leaves out the services it
  doesn't run, and updating a backend checks its app and database rather than its (absent) pages. See
  docs/SERVERS.md.
- **Members' data exports are kept in PostgreSQL:** rather than on the disk of the server whose queue processor
  made them, so on a split site any frontend gives a member theirs, and old ones are cleared (the files on disk
  never were). Exports made before still download.
- **`/admin/backups` works on a split site:** on a frontend its requests go through ZooKeeper to the backend's
  tippr-backup, and it shows the backend's backups and progress, passed both ways every 10 seconds by
  `tippr-backup-relay.timer` on the backend. Another server copying a split site's backups with a transfer key
  can't go through a frontend (the files are on the backend), so the page says to copy the folder instead.
- **Preferences unlock once, like admin mode:** with two-factor on, preferences ask for the code (or a passkey) when
  you open them, rather than on each form: the security page and the password and email page always, and every
  preferences page (options, privacy, friends, blocked, apps) when you choose "also ask for a code before opening
  any of your preferences" on the security page, which replaces asking on each save. Once unlocked their forms need
  no code, and they stay unlocked while you use them, locking again 15 minutes after you last open one; a form saved
  after that says to reload the page and unlock them again. Turning two-factor off and deleting your account still
  ask for a code then.
- **New report reasons, following the content policy:** spam or vote manipulation, harassment or threats, hateful
  content, someone's personal information, sexual content involving minors, other illegal content, impersonation,
  malware, phishing or scams, breaking the site's rules (named for the site, rather than "breaking tippr"), and
  other. A vault with its own rules lists those first and the site's in a menu, as before. Each reason is kept in
  English on the report and shown to moderators in their own language; reports made before keep their wording.
  Reporting from a vault's rules page no longer fails.

### 🐞 Bug fixes
- **The report form was hard to read in night mode:** its box stayed light yellow under night mode's light text. It
  now uses night mode's dark notice colours, as does the list of reasons on a reported post.
- **A post or comment a moderator had reported broke the page for its moderators:** the reports queue and the
  vault's listings gave an error while showing who reported it and why. They show the moderators' reports again.
- **Deleting an account on /admin/users gave "forbidden":** the form's "delete for good" checkbox is named `confirm`,
  which inside the form's own submit handler hid the browser's `confirm()`, so its "are you sure?" threw an error
  and the browser sent the form as a plain page instead, which the site refused. It asks and deletes again. The
  other admin forms that ask first (forgetting a server, updating, flushing the cache, payments) use the same
  safer call, and the two that put translated text straight into their script (deleting an account, forgetting a
  server) no longer break on a translation with an apostrophe.

## 0.21.0
### ✨ Features and improvements
- **A browser test in the release workflow:** after the smoke test, four ordinary members (not admins) use the site
  in Chrome: one posts through the submit form, the others reply to each other down a thread, and they all vote on
  the post and the comments, changing and undoing votes, with the arrows and scores checked. A fifth account,
  moderator of the test vault only, handles a member's report from the queue, removes and approves a comment,
  distinguishes its own, locks and unlocks the thread, and bans and unbans a member, each checked as the moderator,
  the members and logged-out visitors see it, and in the moderation log. And support requests: two members write to
  the admins from the contact page; an admin turns on admin mode with a two-factor code, takes one, notes and replies,
  and gives an employee one category, who sees only that; the member gets the answer from the admin team, without the
  admin's name or the staff note, and their reply reaches the ticket. Every page is checked
  for JavaScript errors, failed requests, sideways scrolling on a phone and unreadable text, and saved as a
  screenshot at desktop and phone width in both themes (the run's `screenshots-VERSION` artifact). See
  docs/RELEASING.md.
- **NSFW posts stay off the front page and /v/all unless a member asks for them:** being over 18 used to put
  every NSFW post in those listings, which also took the ads off those pages. A new preference, "show NSFW posts on
  the front page and /v/all" (off by default, and only for members who said they're over 18), brings them back;
  NSFW vaults and their posts are shown in the vault itself as before.
- **Markdown follows CommonMark now, in place of reddit's snudown:** posts, comments, messages, sidebars and the
  wiki use markdown-it-py, the standard most sites follow, with GitHub's tables, ~~strikethrough~~ and bare links,
  and tippr's own super^script, ^(several words), >!spoilers!< and :emoji:. New: task lists (`- [ ]` / `- [x]`
  show as ☐ / ☑), `[words](example.com)` links without `https://`, and /v/vault links, which snudown never made
  (it linked reddit's /r/ instead). A picture's address, `![words](address)`, is a link to it outside the wiki,
  not leftover syntax. Differences: a heading needs a space after its `#`s (`#1` stays as typed), and the wiki no
  longer takes raw HTML tables (markdown tables do the same). Output is still checked against the same list of
  safe tags, raw HTML is still never used, and long or odd text renders quickly. Installs no longer build snudown
  or need gperf; linkify-it-py is new.
- **Formatting buttons and help for the new markdown:** the toolbar over text boxes adds heading, code block,
  numbered list, task list and table buttons (code on several lines now becomes a ``` block). The "formatting help"
  table under the box shows every option, including strikethrough, superscript, headings, task lists, code blocks
  and tables, and reads properly in night mode; /help/formatting is rewritten to match.
- **Scales: tip a post toward what it's like.** Up and down votes rank posts; a post's new "scales" link (beside
  "share") opens scales to tip instead: helpful ↔ unhelpful, human-made ↔ probably AI and beginner-friendly ↔
  in-depth, and behind "more scales", practical ↔ just for fun, well-sourced ↔ opinion and calm ↔ heated (open
  already when you've tipped one of those). Each member tips each scale once, and can change sides or take the tip
  back. A scale's tally (how many tipped
  each way, and a bar of the split) shows once you've tipped it, so the first tips don't steer everyone else, and
  the poster sees all of theirs. Scales are opinions, not reports: they don't rank posts, don't go to moderators,
  and "probably AI" sits beside the poster's own AI label without changing it; the panel points to "report" for
  posts that break a rule. Posters, logged-out visitors (asked to log in), members in a timeout, and removed,
  archived or sponsored posts can't be tipped. Tips are kept in PostgreSQL (`scale_tips`) and are in a member's
  data export.
- **Updating from /admin/servers shows its progress:** while an update runs, the page keeps itself up to date every
  few seconds instead of needing reloads. Each server's card says what it's doing and for how long, with its log's
  latest lines open, and the updater now refreshes those every 10 seconds while the backup and the installer run
  (before, the page heard nothing from it until a step finished). While the site is down for the install, the page
  says so and keeps checking, then catches up when it's back; it stops once every server has finished. Servers
  that haven't started yet say they're waiting. (The updater that runs an update is the one already installed, so
  the progress reports start with the update after this one.)
- **/traffic/adverts counts ads:** it read tables reddit filled from its ad servers' logs, which nothing filled
  here. The site counts them itself now: a sponsored post when it's shown in a listing (by post, and by campaign
  and vault for its traffic page) and when it's clicked, and each AdSense unit it puts on a page (sidebar, in-feed,
  or Auto ads pages). What Google filled the units with, and their clicks and earnings, stay in the AdSense
  account. Bots aren't counted.

### 🐞 Bug fixes
- **/admin/servers ran words together, and an update's log was one long paragraph:** the page's space compression
  joined lines without a space ("The newest release is0.20.2", a server's name and id, "3.54(1, 5 and 15 minutes")
  and took the line breaks out of the log; both read properly now.
- **/traffic/languages and the "top vaults" table were empty:** they listed last month, the newest reddit's batch
  traffic pipeline had finished; tippr counts as pages are viewed, so they list this month, and say so.
- **The sitemap left out the front page:** it listed vaults from the most subscribed down, so the first page it
  gave search engines was the default /v/tippr ("Tippr Meta"), which Google then showed for a search for the site's
  name. The front page is the sitemap's first entry now, followed by the vault directory (/vaults) and the help
  pages and policies.
- **Clicking a sponsored post failed:** its link goes through /click, served by reddit's separate click tracker,
  which was never ported to Python 3 (every click was an error) and which Docker installs didn't have at all. /click
  is part of the site now: it checks the link's signature, counts the click and sends the browser on. Updating
  removes the old click server (`gunicorn-click`).
- **Updating could leave the queues and jobs stopped:** the installer installs the pinned Python packages, but pip
  kept a package already installed under the same name and version even when it came from elsewhere, and an older
  formenergy-observability from PyPI then conflicted with the pinned `packaging`: the pages worked, but paster refused
  to start the consumers and jobs. The packages pinned to a URL (the baseplate and formenergy-observability forks) are
  now always reinstalled, and the installer checks that the packages fit together, as paster does, failing the install
  (so an update rolls back) if they don't.
- **Clicking "reply" on a comment threw a JavaScript error** ("e is not defined", from reddit's code): the reply
  box still opened, but the comment's hidden replies weren't shown with it, and the error was reported on every
  reply.
- **Search showed NSFW posts to everyone, and pages with NSFW posts had ads:** search results included them for
  people who hadn't said they're over 18, logged out too (hiding them was reddit's safe_search experiment, never
  on); they're shown only to people who have now, as listings already did. And a page that shows any NSFW post
  (the front page, /v/all, other listings, profiles, search) has no AdSense ads, which Google doesn't allow next to
  adult content: before, only an NSFW vault's own pages and NSFW posts' pages dropped them.
- **Every page loaded a tracking pixel nothing used, and on Docker it was missing:** reddit counted pageviews from
  the pixel's log, which nothing reads now that tippr counts them as it serves them, and Caddy had no route for it,
  so every page had a 404. Pages no longer load it (`tracker_url` is blank), and Caddy answers the remaining pixels
  (sponsored links, embeds) as the installer's nginx does.
- **A vault's NSFW setting was hard to find:** it's labelled "NSFW: viewers must be 18 or older" on the vault form
  now, instead of "viewers must be over eighteen years old" (and the /v/all option gains its missing "in").
- **The support pages said "254 milliseconds ago":** they say "just now" for the last minute, as the rest of the
  site does.
- **Search results showed the wrong descriptions:** a vault's page described the whole site (its link previews
  already used the vault's own description), and a post's showed its markdown (`* item`, `[link](https://...)`).
  A vault's page now has its own description, and a post's or comment's reads as plain text.
- **A comment a moderator removed stayed in front of logged-out visitors for up to 2 minutes:** they get a thread's
  comments from a short cache, which removing, approving, distinguishing or editing a comment didn't clear (it
  follows the comment count). Those now change the thread's cache key, so the next view is built afresh.
- **Removed posts and comments were hard to read for moderators:** their salmon background left the grey tagline and
  buttons at 1.4:1. They're a pale red with a red edge now.
- **The unread message count was unreadable in night mode:** night mode's link colour turned it teal on its orange
  badge; it's white again.

## 0.20.0
### ✨ Features and improvements
- **Upgrades are much quicker:** about 1½ minutes of downtime instead of 6½ on a test install. A release's installer
  tarball already holds its built Cython modules, translations and static files, but upgrades threw them away and
  built them again; now each build is fingerprinted (`scripts/build-fingerprint`: its inputs' contents, not file
  dates) and skipped while its inputs are unchanged, by the release or by an earlier run. The translations a release
  carries become a git checkout in place instead of being moved aside and cloned again (which also stops an
  `i18n.old-<date>` folder being left on each update), r2 is reinstalled only when its packaging or Cython modules
  change, and RabbitMQ restarts only when its settings do.
- **Every install runs the Python packages the release was tested with:** the installer installs
  `install/requirements.txt` (moved from `docker/`), the pinned list the Docker image uses, in one go, instead of
  about 40 packages in groups at whatever versions were newest that day (and baseplate and formenergy-observability
  from their branches' tips). `TIPPR_BASEPLATE_PIP_URL` and `TIPPR_FORMENERGY_OBSERVABILITY_PIP_URL` still install
  another on top, but are empty by default. The old `psycopg2-binary` is replaced by the pinned `psycopg2`.
- **An account's status, from its /admin/users page:** its staff permission (none, employee, sponsor or admin: the
  same employees list as /admin/config, with its checks, so no one removes their own admin permission), and whether
  it's one of the site's own accounts (a test account, a bot). The system user, AutoModerator and feed bots count as
  the site's own by themselves. The status column on /admin/users shows sponsors and employees too, and labels the
  site's own accounts, which don't take an Early Member place.
- **The consent banner asks about "optional analytics cookies"** instead of naming Google Analytics; the privacy
  policy it links to says what they are. "Optional" makes clear that declining doesn't turn off the cookies the site
  needs. The preference says the same.
- **A clearer "Translating" help page** (/help/translate): how to fix a translation as numbered steps, the file to
  edit on its own line, links to Poedit and Lokalize, and what to put in an issue as a list. The trophies help page
  lists Early Member among the awards the site gives.
- **Updates say the site is down for "a few minutes"** (on /admin/servers and in the updater) instead of 5–10.

### 🐞 Bug fixes
- **/admin/servers showed the event collector queues in red** with no processor, as if stopped. They're for an
  analytics event collector service, and without one (`events_collector_url`) the site queues nothing there and runs
  no processor for them on purpose: they now say "off (no event collector)".
- **The trophy case was unreadable in the dark theme:** award names were always black (and descriptions dark grey);
  they follow the theme's text colors now.
- **The admin mode page on a remembered computer looked unfinished:** "forget this computer" was a grey button with
  its explanation wrapping beside it, and the heading still asked for a one-time code. It's now a link under the
  main button with the explanation below it, and the heading asks for the password only.
- **Docker: a container could fail to start alongside the others** ("No such file or directory:
  /config/docker.update.tmp"): every container writes the shared config in /config as it starts, through one
  temporary file name, so one could rename it away while another was still writing it. Each now uses a temporary
  file of its own, created private.

## 0.19.0
### ✨ Features and improvements
- **Live comments keep the thread's comment count up to date:** the "N comments" link and the "all N comments"
  heading count the comments that arrive while the page is open.
- **"N here now" on threads:** next to a thread's comment heading, how many people have had it open in the last 15
  minutes, logged in or not, updated every minute while it's on screen (small numbers are fuzzed, shown with a "~").
  It uses the activity service, like a vault's "users here now".
- **Google Analytics events:** with a measurement ID on /admin/site, signing in and up, sharing, gold checkout,
  voting, commenting, posting, joining a vault and searching are sent to GA4 as events, under GA4's recommended
  names where there is one (`login`, `sign_up`, `share`, `begin_checkout`, `join_group`, `search`). No usernames,
  titles or ids are sent. reddit's event calls had gone through the Universal Analytics API, so they sent nothing.
- **Asking for consent before Google Analytics:** "visitors' consent" on /admin/site, "ask first" by default. A
  banner asks each visitor, and nothing from Google loads until they allow it. The answer is kept in a cookie and,
  for members, with their account, so it applies on every device they sign in on; they can change it under
  preferences → privacy options.
- **The privacy policy describes the analytics:** the site's own counting (traffic totals, "here now"), Google
  Analytics only with consent, and how to change the choice. It had said the site ignores Do Not Track, which it
  doesn't for Google Analytics.
- **reddit's EMR traffic pipeline is gone:** the hourly job that sent web server logs through Amazon EMR and Pig
  (`r2/lib/traffic`, `emr_helpers.py`, `scripts/traffic`, `tippr-job-hourly_traffic`) and its `TRAFFIC_*` and
  `emr_*` settings. tippr counts its own traffic as pages are served (the traffic pages), with Google Analytics as an
  option on /admin/site; neither changes.
- **The site gives the Early Member award:** to its first 100 members (`early_member_count` on /admin/config; 0
  turns it off), when they sign up. The site's own accounts (the system user, AutoModerator, feed bots) don't take a
  place; a deleted or banned member keeps theirs without the award, so the first 100 stay the first 100. Existing
  members get theirs when the starter awards script runs (on update), and the daily `tippr-job-year_clubs` catches
  up anyone missed, including the members a raised count now includes. Admins can still give it by hand.
- **An internal status for accounts:** on an account's /admin/users page, admins can give it a short label
  ("trusted", "watch", ...; the labels already in use are suggested) and a note for the other admins. Only admins
  see them. /admin/users shows each account's label in a new column (the note on hover), lists the labels in use with
  how many accounts have each, and lists the accounts with one. Changes are logged under the account's admin
  actions.
- **Forget all remembered devices** (preferences → security, with two-factor on): every browser that skips the code
  ("don't ask on this device" at login, "remember this computer" for admin mode and confirmations), this one too,
  is asked for a code again next time, for a lost device or a shared computer. Nobody is logged out. The section also
  says whether this device is remembered.

### 🐞 Bug fixes
- **Turning admin mode on from a remembered computer** still offered "use a passkey" beside the greyed-out code field
  (and, with passkeys only, asked for one on submit, though no code was needed). The form now says the computer is
  remembered, with no code field, and has a "forget this computer" button to ask for a code again next time.
- **A vault's "users here now" was always ~0:** tippr's client for the activity service was a placeholder that sent
  nothing, recording no visits and answering every count with 0. It's the real generated Thrift client now, so the
  sidebar counts the logged-in members who've visited in the last 15 minutes.
- **The activity and websockets services could stop answering:** `baseplate-serve` always sends traces to an
  OpenTelemetry collector at localhost:4317, and with none there its retries froze those servers, so requests to
  the activity service timed out. Tracing export is off for them (`OTEL_SDK_DISABLED=true`; set it to `false` in
  `/etc/default/tippr` once a collector runs).

## 0.18.0
### ✨ Features and improvements
- **Busy threads can get their own comment queue:** `fastlane_links` (now described on /admin/config) sends new
  comments on the listed threads to `commentstree_fastlane_q`, so a flood of comments there doesn't slow down comment
  trees elsewhere. The installer and Docker run its consumer.
- **Admin pages have a margin:** like the preferences pages, their content no longer runs against the page's edge
  (less of one on phones), and their tables' cells have room around them.
- **Data export requests on /admin/privacy** (in the admin tools menu as "data exports"): members' requests that are
  waiting, processing or failed, with the stuck ones marked, to send again or cancel, and a form to start an export
  for a member. The old privacy dashboard was never loaded (its address gave "page not found") and wrote values
  into the page unescaped.
- **The footer links to /buttons again**, under tippr gold, for sites that want a submit or vote button.
- **Live comments:** new comments appear on a thread while people have it open, under their parent and briefly
  highlighted, without reloading. Admins turn it on for the site (`live_comments` on /admin/config); then each
  vault's moderators choose in their vault's settings, and each member in their preferences. Two more settings say
  what new vaults and new accounts start with (logged-out visitors get the new-account choice). Each comment is
  fetched for the person viewing, so blocked users, score thresholds and collapsing work as usual. It uses the
  websockets service; the installer's nginx now passes `/websocket/` through to it (Docker's Caddy already did).
- **Sitemaps for big sites:** a "sitemap" choice under search engines on /admin/site. "Recent posts" is the sitemap
  as it was (public vaults and the 10,000 newest posts). "Every post" has the new daily `tippr-job-sitemaps` list
  every public vault and post, in as many 50,000-address sitemaps as that takes, and the page shows when it last
  ran. reddit's S3 sitemap code, which needed its EMR data pipeline and SQS, is gone with its consumer and settings.
- **Unused settings are gone from example.ini:** about-page, gold server, self-serve ad wiki pages, adzerk,
  liveupdate, Cloudflare API URL, error reporter and notification email settings, and two feature flags nothing
  checked, all left from reddit.
- **Ready for Python 3.13:** nothing uses the `cgi`, `crypt` or `lib2to3` modules it removed any more. Uploads
  are recognised without `cgi`, HTTP basic sign-in (the `http` auth provider) checks passwords the way the login
  form does (it had also been handing bcrypt text, which failed), and the installer no longer runs lib2to3 over the
  translations, which have been Python 3 all along.
- **`scripts/upload_static_files_to_s3.py` works again,** with boto3 (it needed the old boto, which isn't
  installed). The shim that faked old boto's bundled `six` for it is gone, as is a reddit-era preview image
  backfill.
- **Zendesk is gone:** reddit's ZenDesk ticket provider, which nothing on the site used (the support queue is
  tippr's own), and the modmail-to-email relay that only worked with replies from ZenDesk agents
  (`/api/zendeskreply`, `modmail_email_q` and its consumer). Their settings (`zendesk_*`, `ticket_*`,
  `modmail_forwarding_email`, `modmail_account_map`, `modmail_*_email`) and the `modmail_email_secret` the installer
  made are gone from the ini.

### 🐞 Bug fixes
- **The fast lane and the sharded queues had no consumers:** listing a thread in `fastlane_links`, or turning on a
  `shard_*_queues` setting, sent items to queues nothing read, so those comment trees and listings stopped updating.
  Each now has consumer units (`tippr-consumer-<queue>_shard_q@1` to `@10`, which the installer starts when the
  setting is on), and an optional queue is used only while its consumer runs; otherwise items stay on the main
  queue. Domain shards were picked with Python's `hash()`, which differs from process to process, so one domain
  could land on any shard; they use a stable hash now.
- **Reading a Cassandra row backwards from a column returned the wrong columns:** `get()` with `column_reversed`
  and a start column kept the columns after the start instead of before it (so "the goal in effect on a date"
  found the newest goal instead), took `""` as a bound rather than none, and returned an empty row where pycassa
  raises not found. It now slices the way `multiget()` already did.
- **A recovery code or passkey check could be used twice at once:** several sign-ins sent together with one recovery
  code all got in, and a stale copy of the account could put back codes used meanwhile. Codes are now taken under a
  lock from a fresh copy, and the passkey check a form gets is good for one request only. A passkey's credential id
  is unique now too (added to existing databases), so a made-up registration can't reuse another account's.
- **A data export request whose queue item was lost blocked new ones for good:** asking again now sends a request
  that's been waiting over half an hour once more.
- **"Newest first" from Cassandra wasn't:** column names are stored as text, and Cassandra returns them in text
  order, which isn't time order for time UUIDs (admin notes, privacy requests, the mod log's paging) or number
  order for numbers. Each column family now orders, bounds and returns its column names by its comparator, as
  pycassa did, so reads newest first, paging and "the latest N" are right; the sorting each model did on its own
  to make up for it is gone. Stored data is unchanged.
- **The interactive buttons on /buttons loaded from reddit's servers:** the button scripts other sites paste in
  wrote an iframe from redditstatic.com, which talked to fixed tippr.net addresses and showed reddit's logo. They
  now load from the site that serves them, show its icon and name, and read the `tippr_url`, `tippr_title` and
  other options the page tells people to set (they read `reddit_*` names before). The snippets on the page use the
  site's full address, so they work pasted elsewhere.
- **Tests ran different code from the site:** sorts, sgm, wrapped (page rendering), the utils helpers and comment
  tree helpers each had a pure-Python copy next to the Cython module the site runs, and they'd drifted (the
  rendering copy was a cut-down version, and "best" scores differed in the last decimals). The copies are gone:
  everything, tests included, uses the compiled modules, now built as Python 3 and 1.3 to 7 times faster than the
  copies were. Building tippr without Cython stops with that message instead of quietly leaving them out. The
  "best" sort's scores use full precision, and the hot sort's epoch is UTC as postgres's is, so the two always agree.
- **Internet Explorer support is gone:** the IE 8 script bundle and its jQuery 1.11, the IE traffic charts bundle
  (excanvas), html5shiv, the ES5, JSON and CustomEvent polyfills, IE conditional comments, IE-only stylesheet rules
  and gradient filters, and IE workarounds in the scripts. Every browser still in use has what they stood in for;
  pages load a little less.
- **/admin/servers showed working queues as having no processors:** the comment tree and listing queues' processors
  poll, which RabbitMQ doesn't count, so they were flagged with 0. They show "polling" while they run now.
- **Day- and week-long rate limits depended on the server's timezone:** their counters were named with strftime's
  `%s`, which reads the time as local time (and isn't available everywhere), so on a server not set to UTC they
  were shifted by its offset. They use the time in seconds directly now.
- **/_test_vars was open to anyone:** the test client's setup address answered every visitor and kept a copy of
  that request's state each time, never freed, so it could be used to fill the server's memory. Only the test
  client (tests and `tippr-run` scripts) gets it now. The middleware's patches to Paste and WebOb, which newer
  versions made unneeded (or which never took effect), are gone.
- **A form sent with no body, a bad length or too big an upload crashed the worker:** the "length required", "bad
  request" and "too big" replies were text where the server needs bytes, so the visitor got an error page from the
  server instead. They're sent properly now.
- **Settings saved on /admin/site and /admin/config didn't reach scripts, consumers or jobs:** only web processes
  applied them (on their first request), so `tippr-run` scripts, the queue consumers and the timed jobs went by the
  ini alone.

## 0.17.0
### ✨ Features and improvements
- **Sign in with a passkey alone:** the login forms' username field offers the site's passkeys in the browser's
  autofill, and choosing one signs in with no password or code; browsers that can't offer them there get a "sign in
  with a passkey" button. The passkey must check the person (fingerprint, face or PIN), which makes it both factors.
  Staff (admins and employees) still sign in with their password and then a code or passkey, and admin mode asks for
  both as before. Passkeys made earlier work when the device kept them for signing in (most do).
- **Preferences, security asks for one code:** instead of a code field on every form there, one code (or a passkey)
  unlocks the page for 15 minutes; signing in with a code or a passkey unlocks it too. Turning two-factor off still
  needs the password and a code typed then.
- **Passkeys first, and a plan for a lost device:** adding a method offers a passkey (recommended: a fake login page
  can't use one) or an authenticator app side by side, each explained. New recovery codes are shown at the top with
  what to do with them, an account with one method is told to add a second, and signing in with a recovery code
  lands on the page to replace the lost phone or key.
- **Passkeys named by where they're saved** ("iCloud Keychain", "Google Password Manager", "Windows Hello"), with the
  FIDO Alliance's wording: "create a passkey", "delete", what a passkey is and where it's kept, and failure messages
  that say what to do next.
- **Helping translate goes to the translations project:** /help/translate (the "volunteer to translate" link next to
  the language choice) sends people to tippr-i18n on GitHub, to send a pull request or open an issue about a
  mistake, instead of messaging the site's admins, who can't change the translations themselves.

### 🐞 Bug fixes
- **Authenticator app secrets were stored as they are:** a copy of the database could make two-factor codes for
  every account with an app. They're now encrypted with a key from the site's `SECRET` (which backups carry), each
  bound to its account; secrets kept before are encrypted the next time they're read.
- **A wrong code when adding an authenticator app said "wrong password":** it now says the code didn't work and to
  check that the phone sets its time automatically, as the login code page does too.
- **A passkey the site refused (too many, say) said nothing:** the reason is shown now.
- **An account with only passkeys was asked for a code:** two-factor prompts now lead with "use a passkey" when the
  account has no authenticator app, with "use a recovery code instead" as the fallback; with an app, the code box
  stays and the button reads "or use a passkey".
- **Script text showed translators' unfinished guesses:** the strings built for the page scripts included fuzzy
  catalog entries (which the pages themselves never show), so the passkey button read "make update". They're left
  out now.
- **Save buttons stuck on "submitting…":** a form without an `id` sent an empty one, and the server's answer
  (clearing the status, "saved", the errors) is aimed at that id, so it changed nothing on the page. Such a form gets
  an id of its own when it's sent now, so its status and errors show (preferences, security's "also ask for a code",
  the privacy page and others).
- **Saving the explore page's settings failed** with an error (`'UrlPushable' object is not callable`): it built
  its redirect with Pylons' `url()`, which the compatibility layer doesn't provide. It goes back to /explore now.
- **The traffic pages' layout:** the charts are an even grid (two across, one on a phone) instead of rows that
  wrapped differently, "activity by day" gets the page's full width below the other tables (scrolling sideways in
  its own box if need be) instead of running under the sidebar, and the tables' stripes no longer show as white
  bars in night mode.

## 0.16.0
### ✨ Features and improvements
- **Feed posts are mixed on /v/all:** a feed check posted each feed's new items back to back, so /v/all showed a
  block of one feed, then the next. Each run now fetches every due feed first and posts their items one vault, and
  one feed, at a time. An item whose link is already in the vault, or whose title was posted there in the same run
  (two feeds with the same story), isn't posted again.
- **OpenSearch gets longer to start** (`TIPPR_OPENSEARCH_START_TIMEOUT`, 10 minutes by default) as its data grows,
  and the installer restarts it only when its settings changed or it isn't running.
- **Translations update with every install and upgrade:** the installer (also run by first boot and server
  updates) now brings an existing `i18n` checkout up to the latest translations instead of only cloning a missing
  one. A copy that isn't a git checkout is moved aside (`i18n.old-<date>`) and cloned again; if GitHub can't be
  reached, the existing translations are kept. A catalog that fails to compile no longer stops the languages
  after it from compiling.
- **Update the servers from /admin/servers:** choose a release and each server updates itself within a minute, one
  at a time, as in the Proxmox upgrade steps. Each server downloads the release's installer from GitHub, checks it
  against the release's checksums, and makes a site backup first if asked. It then keeps the old code, re-runs the
  installer and checks the site answers. If it doesn't, the old version goes back. Each server's card shows how it's
  going.
  - The web app only asks, through ZooKeeper. A root-owned updater (`tippr-update.timer`) does the work, and
    downloads only from the repository in root's `/etc/tippr/updates.conf`.
  - For installs with `tippr-firstboot` (Proxmox containers). `TIPPR_WEB_UPDATES=0` turns it off.

### 🐞 Bug fixes
- **Requests could see another request's user:** the Pylons compatibility layer kept request state (the user,
  the request, the response) shared by all threads, and paster serves requests from a pool of threads, so under load
  one request could briefly see another's `c.user`. It's kept per thread now.
- **An empty rising page said the vault had nothing in it:** rising is often empty in a vault that has posts, so it
  now shows the plain "nothing here" message, as gilded does. The "Nothing in /v/… yet" welcome is for hot and new.

## 0.15.0
### ✨ Features and improvements
- **/admin/servers shows when an update is out:** the newest release on GitHub (`release_repo`, checked hourly),
  whether each server runs an older one, and a link to the release notes. Pre-releases are mentioned, not counted.
- **Sign up with Google, GitHub and the rest:** signing in with an outside account nobody linked now also offers
  to make a new account for it: a username (suggested from that account's name), a password and an optional email.
  The sign-up form's checks all apply (sign-ups open, the captcha, the spam check, rate limits), and the new account
  is linked straight away.
- **Empty memcached** from /admin/config's caching panel, for when pages show something out of date. It asks first,
  since the site is slower while the caches fill again, and rate limits and half-done sign-ins start over. Nothing is
  lost: everything kept there is a copy.
- **Sign in with GitHub or Discord:** /admin/logins offers both next to Google and Facebook, with the site's own OAuth
  app from each. Members link them under preferences → security, as with the others. Neither shares an email address
  with the site: the linked account shows its GitHub or Discord username.
- **Feed flags:** a feed on /admin/feeds can mark every post it makes NSFW and give them an AI label (human-made,
  AI-assisted or AI-generated). A label the vault doesn't accept is refused when the feed is saved. Lists for
  `scripts/import_feeds.py` take `nsfw` and `ai:human` / `ai:assisted` / `ai:generated` on a feed's line.
- **Activity on the traffic pages:** /traffic (staff) shows what people did, for the last 24 hours, 7 days and 30
  days and by day: new visitors, sign-ups and logins (and failed ones), password resets, posts, comments, upvotes and
  downvotes, reports, moderator actions (also by type), messages and modmail. A vault's /about/traffic shows its own
  posts, comments, votes, reports, moderator actions and modmail to its moderators; with public traffic on, everyone
  else sees only posts, comments and votes. Counted as things happen, without keeping who did them.
- **AutoModerator help page** (/help/automoderator): where a vault's rules go, what they can check (title, body,
  links, domains, reports, the author's karma and account age…), what they can do (remove, filter for review,
  report, approve, flair, NSFW, lock, sticky, reply, message), placeholders and examples. The rules page on a
  vault's wiki links to it instead of reddit's documentation.
- **/admin/servers:** every server's version, load, memory, disks and services, reported by each once a minute
  (`tippr-job-server_status`, a small script that doesn't load the app), with warnings for one that went quiet, is
  short of disk or memory, is busy, has a service down or runs a different version from the others; plus the
  RabbitMQ queues and whether anything is processing them. Servers are told apart by machine id and named by
  `TIPPR_SERVER_NAME` (default: the host name). Only the latest report is kept; one gone for 7 days drops off.
- **How the caches are doing, on /admin/config:** each memcached the site uses (memory used of its size, items,
  how many lookups find something, and evictions, with a hint to give it more memory when it's full), whether
  nginx keeps logged-out pages and for how long, and who serves the static files.
- **The page cache time is a live setting** (`logged_out_page_cache_seconds` on /admin/config): lower it to show
  changes sooner, or set 0 to stop caching logged-out pages at once, without re-running the installer (whose
  `TIPPR_PAGE_CACHE_SECONDS` is the starting value).
- **nginx caches logged-out pages** (`TIPPR_PAGE_CACHE_SECONDS`, 30 by default, 0 off): the ones the app marks
  cacheable are built at most once every 30 seconds instead of for every visitor, the old copy is served while a
  new one is built or if the app is down, and logged-in visitors and apps always go to the app.
- **Logged-out pages can be cached** by nginx or a CDN in front of the site: they're marked cacheable for
  `logged_out_page_cache_seconds` (30 by default; 0 off) when nothing on them is for that visitor only. Logged-in
  visitors, pages that set cookies and errors never are. The login popup's captcha is fetched by the browser on
  those pages instead of being part of them, and a new visitor's tracking cookie (`loid`) waits for a page that
  isn't cached.
- **memcached settings in the installer:** it had Ubuntu's 64 MB; `TIPPR_MEMCACHED_MB` sets it (`auto`, the default,
  is a quarter of the RAM, 64 to 1024 MB). For several frontends, `TIPPR_MEMCACHED_SERVER` points the site at a
  shared cache server, which `TIPPR_MEMCACHED_LISTEN` and `TIPPR_MEMCACHED_ALLOW` (the frontends' address range, let
  through the firewall) set up; memcached has no password, so it's refused without a range.
- **nginx serves the static files** (CSS, JS, images) in production, from `/srv/www/static`, instead of the app:
  files whose name has a content hash are kept by browsers (and a CDN) for a year, others for a day, and they're
  gzipped. Each install adds the new build's files and keeps the old ones for 60 days, so with several frontends
  upgraded one at a time, pages from one not yet upgraded still find theirs.
- **Passkeys for two-factor sign-in:** add passkeys (your phone, computer or a security key, unlocked with a
  fingerprint, face or PIN) on preferences → security, alongside or instead of authenticator apps; several of each.
  Anywhere a two-factor code is asked for (the login code page, changing your password or email, admin mode,
  deleting your account…), "use a passkey" works instead of typing one. Adding or removing a passkey needs a code
  from a method you have, as for apps. Needs the `webauthn` Python package (installed by the installer and in the
  Docker image).
- **Several two-factor methods:** preferences → security lists your authenticator apps, each with a name, when it
  was added and last used, and a remove button; add more (up to 10). Adding or removing one needs a code typed then
  from a method you have (the password for the first one; removing the last one, which turns two-factor off,
  needs the password too). A code from any of them works everywhere. An existing setup becomes the first method
  the first time it's used.
- **CleanTalk learns from moderators** (/admin/antispam, "tell CleanTalk what moderators decide", on by default):
  for posts, comments and messages CleanTalk checked, the spam button (or removing a user's posts as spam on
  /admin/users) reports them to CleanTalk as spam, and approving something CleanTalk flagged reports its mistake.
  Removing without spam sends nothing. It's sent in the background, so moderating doesn't wait on CleanTalk.
- **In-article ad units** for the in-feed ad (/admin/ads): enter `in-article` as the layout key. AdSense lets an
  in-article unit's colours be set, so it's the way to have night mode ads that match the dark pages.

### 🐞 Bug fixes
- **Explore was empty on a small site:** recommendations come from many members' subscriptions, no discovery vaults
  are set by default, and rising skipped the vaults you're in. With no discovery vaults set, explore now picks
  popular vaults you haven't joined, and when nothing is rising elsewhere it shows what's rising in your own vaults.
- **Rising missed most voted-on posts:** it looked only at the newest 2,000 posts of the last 12–24 hours, and feed
  bots can post more than that. It now finds posts by their votes and comments, over the last 3 days
  (`rising_period`). Older posts still sink below newer ones.
- **nginx could serve an old logged-out page indefinitely:** while it built a new copy, nginx served the old one. When
  the new one couldn't be cached, the old copy was never replaced. nginx now builds the new copy first (one request
  at a time), and the installer empties the page cache when it writes the setting.
- **Error pages could be kept by the logged-out page cache:** an error page is rendered as a request of its own,
  so it was marked cacheable, and nginx served the error again for that address.
- **JSON listings failed for posts with preview images** (/new.json, /hot.json, a vault's .json…): the image
  resizers didn't take the format the API asks for, so the listing failed with an error. imgix now also gets the
  format.
- **The two-factor code page after signing in was kept by the logged-out page cache:** for up to the cache time,
  another visitor opening /logins/otp could get the page with someone else's half-done sign-in on it. They would
  still have needed that person's code. The sign-in pages are never cached now.
- **Analytics events piled up with nowhere to go:** every login, vote, post, report, moderator action and new
  visitor made an event (with the member's id, IP address, browser and a location lookup) for reddit's analytics
  pipeline, but nothing ever sent them anywhere, so they grew in RabbitMQ without end. They're counted for the traffic
  pages now instead (only the counts are kept), go to an event collector only if one is set up
  (`events_collector_url`), and the installer empties what was queued.
- **AutoModerator never ran:** the installer gave its queue no processor (reddit's setting) and no account to act
  as, so vaults' rules (their wiki page config/automoderator) were never applied and new posts piled up in its
  queue. It runs now, as an `AutoModerator` account the installer makes with no password anyone knows
  (`TIPPR_AUTOMODERATOR_NAME`, `off` to turn it off). It won't act as a member's account of the same name.
- **A new logged-out visitor's first page** set the `loid` cookie without being marked private, so a cache in front
  of the site could have handed that cookie to others; it's marked private now.
- **Preferences pages' text sat against the edge of the page** (only the privacy tab had a margin); they all have
  one now. On phones, the two-factor methods list and the apps on /prefs/apps fit the screen.
- **Forms that send you back to the page you're on, at a section** ("…#recovery-codes") didn't reload it, so
  what they changed didn't show until you reloaded.
- **Logging out on a page only members or staff can see** (moderator tools, preferences, messages, submitting, saved
  posts, a private vault…) showed "forbidden" or the full-page login. Logging out now stays only on pages anyone
  can see (listings, posts, profiles, help, search) and goes to the front page from anywhere else.
- **Formatting buttons in night mode:** the comment and post formatting toolbar (bold, italic, link, spoiler,
  preview…) had dark text on its dark buttons. Its colours, and the emoji picker's headings, follow the theme now.

## 0.14.0
### ✨ Features and improvements
- **Starter feeds and defaults on upgrades** (`TIPPR_STARTER_FEEDS`): the installer adds the starter feeds on a new
  site (`auto`, the default; `1` turns them on for an existing site, `0` off, and the choice is remembered), and each
  install or upgrade adds the starter feeds and front page defaults new since the last run. What it offered before
  isn't offered again, so a default vault an admin took off, or a feed removed from /admin/feeds, stays that way. On
  a site from before this, vaults that already have starter feeds keep what they have, and ones without get theirs.

### 🐞 Bug fixes
- **Pages wider than the window after zooming in (or narrowing the window):** Google gives an ad a fixed width
  from the space it had when it loaded, and the content column wouldn't get narrower than that, pushing the
  sidebar and the header's right end off the screen. The column and the ad boxes now ignore the ads' own width.
- **Placeholder thumbnails on phones** (no image, text post, NSFW) were cut off: they're 70px pictures and the
  phone layout's thumbnails are 60px; they keep their 70px.
- **Doubled vote arrows on phones:** the bigger tap targets showed a strip of the neighbouring (voted) arrows from
  the image sheet beside each arrow. The arrow images keep their size, and padding makes the target.
- **The installer (and the Proxmox template's first boot) failed** in 0.13.0: three lines meant for the end of
  `install/tippr.sh` were at its top, so the starter feeds step ran before anything was set up. On a Proxmox first
  boot that created ZooKeeper nodes with the template's password, locking the site out of them (`NoAuthError`).

## 0.13.0
### ✨ Features and improvements
- **Two-factor sign-in for everyone** (it was admins only): any member can turn it on under preferences →
  security with an authenticator app. With it on, changing the password or email address and linking or unlinking
  a Google/Facebook sign-in also need a code (one code counts for 15 minutes in that session), turning it off needs
  the password and a fresh code, and logging in with a password to link an outside account asks for the code before
  linking. The security tab is shown to every member now.
- **Two-factor recovery codes:** turning two-factor on shows ten one-use recovery codes (once) that work in place of
  a code from the app, for a lost phone; preferences → security shows how many are left and makes a new set (the
  old ones stop working). Turning two-factor off removes them.
- **Two-factor at login (optional):** a member with two-factor on can have it asked for at every login, with the
  password or a linked Google/Facebook account (preferences → security, "also ask for a code"). After the password
  the site asks for the code on its own page, with "don't ask again on this device for 30 days"; scripts can send
  it as `otp` with the password, and adding an account to the account switcher asks too. Signing in with a linked
  account now asks for the code only when this is on (it always did before).
- **Two-factor when saving preferences or posting (optional):** the same "also ask for a code" choices can ask for
  it when saving preferences and when submitting a post (a code counts for 15 minutes; apps using OAuth aren't
  asked).
- **Require two-factor for moderators and staff** (`require_two_factor_staff` on /admin/config, off by default):
  moderators, employees and admins (for admin mode) need two-factor sign-in on to use their tools; until then their
  moderator powers are paused and every page shows a notice linking to preferences → security. Others see them as
  moderators as before, and members who aren't staff are unaffected.
- **Sign in with Google or Facebook**, for accounts that linked one. An admin turns providers on at the new
  **/admin/logins** with the site's own OAuth app (client ID and secret; the page shows the redirect address to
  register). Members link an account under preferences → security, or
  by logging in with their password the first time they sign in with an unlinked one; the login page and sidebar
  offer "sign in with Google". It only ever signs in to the account that linked it (nothing is matched by email, and
  no accounts are created this way), links can be removed at any time,
  and deleting an account removes them. Instagram no longer offers sign-in for other sites.
- **More starter feeds**, so the starter vaults that had none are front page defaults again: linux, selfhosted,
  privacy, mechanicalkeyboards, cozygaming, retrogaming, anime (Crunchyroll, Anime News Network, Otaku USA), fiberarts,
  aesthetics, pics and aww (29 feeds, each checked). Add them to an existing site with
  `FEEDS_ADD=1 tippr-run scripts/import_feeds.py` (before running `prune_default_vaults.py`, which would otherwise take
  those vaults off the defaults). Only the site's own tippr and asktippr aren't starter defaults now.
- **The gold and ads switches on /admin/payments** now close buying altogether: with gold off, /gold says gold isn't
  for sale and posts show no "give gold" link (except to members with gold already bought to give); with ads off,
  only sponsors can make promoted posts, and the sponsored link's help no longer invites people to advertise.
- **Night mode ad units** (/admin/ads, optional): AdSense units with dark colours, shown instead to members with night
  mode on. Google draws the ads, so the site can't restyle them itself.
- **Documentation** brought up to date: the README, installer, architecture, admin, content, privacy, help and policy
  docs describe the current site (payments, feeds, the newer admin pages, policy updates on upgrade, account deletion).

### 🐞 Bug fixes
- **Buttons that did nothing:** the gold payment page's buttons (PayPal and the rest, and paying with your gold), the
  "report" buttons, and the moderator action forms (ban, mute and the like). Their scripts looked for the page's
  `div.content`, which is now a `<main>`.
- **Ads in listings:** the in-feed ad showed once, after the Nth post, although the setting reads as how many posts
  between ads; it now repeats every N posts. Ads on pages infinite scroll adds stayed empty (their start-up script was
  dropped); they load now.
- **`tippr-run` as root** wrote files the site couldn't use afterwards (compiled templates, media); it now runs as the
  site's user, keeping the environment (`FEEDS_ADD=1` and the like).
- A few texts still named tippr.net: the sponsored link's help bubble, the friends page and the vault custom-domain
  hint now use the site's own name and domain.

## 0.12.0
### ✨ Features and improvements
- **No more "coins"**: buying gold ahead to give away later is "Give Gold", and what you've bought is just gold
  ("Give Gold: 3 months" on your profile, "use 1 of your 3 months of gold" when paying), on the gold, payment and
  gilding pages, your profile, preferences, the API app permission and /admin/coins. Addresses and the code's names
  (`/coins`, `goldtype=coins`, `Account.gold_coins`) are unchanged.
- **Front page defaults are only vaults with feeds**, so a newcomer's front page has no empty vaults: the starter
  list no longer makes linux, selfhosted, mechanicalkeyboards, privacy, cozygaming, retrogaming, anime, fiberarts,
  aesthetics, pics, aww, asktippr and tippr defaults (they have no starter feeds; the vaults are still created). On an
  existing site, `scripts/prune_default_vaults.py` takes every default without an enabled feed off the list
  (`PRUNE_DRY_RUN=1` to preview, `PRUNE_KEEP=tippr,asktippr` to keep some); a vault can be made a default again on
  /admin/vaults.
- **Payments** for gold and sold ads with your own PayPal, Stripe, Coinbase and BitPay accounts, set up on a new
  admin page, **/admin/payments**: turn on the providers you use, enter their API keys (secrets are never shown
  again), test them, and see each one's webhook address. Buyers choose on the payment page and pay on the provider's
  own page: PayPal (also Venmo, Pay Later and cards), Stripe Checkout (cards, Google Pay, Apple Pay), Coinbase
  (USDC; Coinbase Commerce, which the old Bitcoin button used, has shut down) or BitPay (Bitcoin and more). Prices
  are worked out on the server, a purchase is delivered exactly once however often the provider calls back, and
  webhooks are optional (payments complete when the buyer comes back; the site always asks the provider rather than
  trusting a webhook). The page also lists the latest payments, to look one up or refund it. See
  docs/gold-payments.md.
- **Sold ads are paid when they're submitted** (with the providers above) and refunded if the ad is rejected before
  it runs, its budget changes or the campaign is deleted; an ad that showed less than was paid for gets the unspent
  part back through the provider. The emails advertisers get no longer talk about reddit.com or card holds.
- **reddit's old payment code is removed**: PayPal hosted buttons and IPNs (`/ipn`), the Coinbase Commerce "Bitcoin"
  button (Coinbase Commerce has shut down), Google Checkout's script, and the authorize.net card form for ads (the
  `lib/authorize` package). /admin/payments replaces them. Their ini settings (`PAYPAL_BUTTONID_*`,
  `COINBASE_BUTTONID_*`, `BTC_DISCOUNT`, `goldpayment_email`, `authorizenetapi` and the `paypal_webhook`,
  `coinbase_webhook` and `authorizenet*` secrets) can be deleted. Gold subscriptions still use the Stripe card form,
  and /gold now offers them only when its keys and plans are set (`stripe_*` secrets, `STRIPE_*_GOLD_PLAN`).

### 🐞 Bug fixes
- **Thumbnails** were never made: the thumbnail finder (`tippr-consumer-scraper_q`) failed on every post under
  Python 3 (in its cache key, URL cleaning, gzip handling, and saving the result, whose keys came out as bytes). They
  are made for new posts now, and `scripts/backfill_thumbnails.py` finds them for the last few days' posts
  (`THUMB_DAYS=7` to go further back). Vaults now show thumbnails unless their moderators turn them off (the default
  was off, and with the "show thumbnails" preference at its default nobody saw any), new vaults start with the box
  ticked, and the installer serves uploaded media over https (it wrote an `http://` address, mixed content on the
  site's https pages; upgrades fix it in development.update).
- **Night mode**: the vault list's description boxes, the vault search box, the selected tab of the side menu,
  quotes, code, buttons' borders, the submit page's notice, the gold page and the AI labels stayed white or light grey.
  The stylesheets' fixed light greys are now theme colours (`--tp-subtle`, `--tp-gray`, `--tp-gray-strong`,
  `--tp-line`, `--tp-line-soft`), which night mode darkens. The "tippr gold" and "tippr gilding" banners have a
  light "tippr" in night mode.
- **Policy pages' "Last Revised" date** stayed at the date in docs/policies when the installer (or
  `force_revise_policies.py`) updated the pages; it's now the day a page's text changes, and an unchanged page keeps
  its date (and isn't revised again).
- **Policy pages kept their first version**: the installer only created missing pages, so a site never got newer
  versions of docs/policies (an older site's pages still list email addresses instead of the contact page). It now
  brings policy and help pages up to date on every install or upgrade, except a page an admin edited on the site,
  which is left alone (`FORCE_POLICY_IMPORT=1` replaces those too).
- **"Learn more" about gold** (/gold/about) led back to /gold. It's now a page listing what gold gives you: no ads,
  more front page vaults, new comments highlighted, save categories, filtering /v/all, /v/myrandom, notes on friends,
  visited links remembered, gold-only vaults, the lounge if the site has one, and the trophy.
- **Feed posts' titles** showed HTML codes ("&#8216;Trump Accounts&#8217;") when a feed escaped its titles twice, and
  sometimes HTML tags; the importer now decodes them. `scripts/fix_feed_titles.py` fixes the posts already made
  (`FIX_DRY_RUN=1` to preview).
- **/vaults/mine** said you were subscribed to nothing until you'd subscribed or unsubscribed once, though your front
  page shows the default vaults; it now lists those, and says so.
- **An advertiser's ad page** (/promoted/edit_promo/…) failed to open once the ad had any history (its log's entries
  came back from the database as text, not times).
- **Gold purchases, gifts, gift codes and claiming them** failed after payment: the gold table was written in a way
  SQLAlchemy 2 no longer supports, and months of gold were worked out as fractions under Python 3.
- **Sold ads**: campaigns' payment records could be left uncommitted, and creating a second campaign in the same
  server process failed (both from SQLAlchemy 2 keeping a transaction open); promoted posts' pages failed to show
  their buttons; and the "pay" button went to `pay.<your domain>`, which nothing serves on a self-hosted site
  (`payment_domain` is no longer used for it). The advertiser emails for payments and launches also failed to render.
- **Sold ads** (promoted posts) could show in vaults whose moderators turned ads off: the check for "show ads here"
  mixed up its and/or, so only gold members who hid ads were really left out. Now promoted posts show only where
  ads are allowed, and never to gold members who chose to hide ads.

## 0.11.0
### ✨ Features and improvements
- **/admin/config** saves every setting with one "save changes" button (kept at the bottom of the window) instead of
  a button per setting. Only the settings you changed are saved, so the ini's values don't become overrides; one
  that isn't valid says so on its row while the rest are saved.
- **Deleting your account** is on the privacy page (/prefs/privacy, now a tab in preferences) instead of a separate
  "deactivate" tab, whose old address redirects there. The form says plainly what happens and when, lets you delete
  your posts and comments too (before, it told you to delete them one by one), and asks for your two-factor code if
  you use two-factor sign-in.
- **Starter awards** (the trophies on profiles), so /admin/awards isn't empty: "Verified Email" and "tippr gold",
  which the site gives by itself (and now also to members who verified or got gold before), and Staff, Early Member,
  Bug Hunter, Translator, Helpful Member and Best Comment for admins to give, each with an icon. The installer
  creates them (`scripts/create_default_awards.py`, safe to re-run); existing awards are left alone.
- **X-Year Club trophies**, as on reddit: on their cake day members get the 1-Year Club, 2-Year Club and so on (only
  the latest), from a new daily job, `tippr-job-year_clubs` (the installer and Docker run it; the starter awards
  script gives everyone theirs the first time).
- **More starter vaults and feeds**: /v/gis (maps, geospatial data and Earth observation: NASA Earthdata and Earth
  Observatory, USGS, Copernicus, OpenStreetMap, OSGeo, QGIS, MapLibre and more), /v/ainews, /v/devops, /v/sports,
  /v/podcasts, /v/videos (YouTube channels) and /v/marketing, none of them front page defaults, and about 80 more
  feeds for the existing vaults (from feeder.co's popular feeds, each checked). Run `create_default_vaults.py`, then
  `import_feeds.py` with `FEEDS_ADD=1`, to add them to an existing site.
- **Explore** (/explore) recommends again: its "personalized" part needs to know which vaults are like which, which
  reddit worked out with its own data pipeline, so it always said "Our robots have no suggestions". A new daily job,
  `tippr-job-vault_similarity` (also run by the installer), works that out from the site's subscriptions ("people
  who subscribe to X also subscribe to Y"), which also feeds the similar-vault suggestions for multivaults. Default
  vaults are now only left out of a member's recommendations when they have no subscriptions of their own.

### 🐞 Bug fixes
- **The welcome bar** (`welcomebar_messages` on /admin/config) broke the front page for logged-out visitors when a
  message had no " / " (which splits it into a heading and a second line); one-part messages now show as just a
  heading. Saving messages with a quote missing is refused instead of making nonsense messages, and messages with
  accented letters or emoji no longer come out garbled.
- **/v/frontpage** (the vault behind the front page, whose wiki holds the policy pages) showed up in /v/random and
  the vault lists as if it were a community. It's left out now, with the site's other working vaults; on a site at
  tippr.net the vault lists also showed /v/promos, which an old reddit check skipped hiding there.
- **Releases**: a unit test now checks that the Docker jobs container can read every systemd timer, so a timer
  written in a form it doesn't know (as the 0.10.0 release's daily ad metrics timer was) fails the tests instead of
  the release.

## 0.10.0
### ✨ Features and improvements
- **Enhancements**, like the Reddit Enhancement Suite's, so members don't need a browser extension: a new
  "enhancements" section on /prefs turns on infinite scroll (the next page of a listing is added at the bottom),
  keyboard navigation (j/k, a/z, enter, c, x and more; ? lists them), show images (a button on posts that link to an
  image shows it in the listing, and they can expand by themselves, except NSFW and spoiler posts), night mode and
  "hide child comments" links. All are off until a member turns them on. The old infinite scroll prototype, which
  ran for everyone and never found the next page, is gone.
- **Filters**, like RES's filteReddit: under "filters" on /prefs, members list title keywords, domains, vaults and
  users whose posts they don't want in listings (never their own posts; a filtered vault still shows when you visit
  it). Filtering happens on the server, so it works with infinite scroll, on every device, and through the API's
  preferences.
- **User tags, user info on hover and parent comments on hover**, also from RES, in the "enhancements" section: a
  tag button by usernames to note who someone is in a colour (only you see your tags; they're kept on your account,
  so they follow you to every device and come with your data export), a card with a user's karma and account age when
  you hold the mouse over their name, and the comment a reply answers when you hold it over "parent".
- **New comment counts, visited posts and a comment navigator**, also from RES: "(3 new)" by posts you've opened
  before, with the new comments highlighted when you go back; posts you've opened faded or hidden in listings; and on
  comments pages, buttons to jump between top-level comments, the submitter's, yours, new ones or ones with links.
  What you've opened is remembered in your browser, as RES does.
- **Account switcher**, also from RES: a "switch account" menu by your name to move between your accounts without
  logging out. You add an account by logging in to it once; no passwords are kept, only the accounts' sessions, in an
  HttpOnly cookie that scripts can't read. A session stops working when that account's password changes, and
  logging out forgets the other accounts.
- **GitLab CI/CD**: `.gitlab-ci.yml` runs the unit tests and installer smoke test, and builds, tests and publishes
  releases (Docker image, compose bundle, installer tarball, Proxmox template) on a GitLab server, as the GitHub
  workflows do on GitHub, for a repository kept on GitLab and mirrored to GitHub. It also has the version bump merge
  request. See docs/RELEASING.md.

### 🐞 Bug fixes
- **Rising** was nearly always empty: it divided votes by page views that only reddit's own infrastructure counted,
  needed a second upvote within 12 hours, ignored comments, and looked at only 50 of the period's posts in no
  particular order. Now it shows the posts other people have voted on or commented on, the most activity for their
  age first, over the last day for new installs (`rising_period`).
- **Comments pages with replies** crashed ("you broke tippr") as soon as a comment had a reply: the compiled comment
  tree code still sorted top-level comments the Python 2 way.
- **Privacy settings** (/prefs/privacy, linked from the contact page) showed a line of Python instead of the page. It
  now shows, members can request and download their data export and see their requests, and admins see them in the
  /admin/privacy queue (requests were never indexed, so neither list had anything in it). Exports also include the
  member's subscriptions now, and the installer creates the folder they're written to
  (`/var/lib/tippr/privacy_exports`), which the export job couldn't create itself.
- **Subscribing and unsubscribing** didn't last: after a reload a vault was back the way it was. Accounts always
  looked as if they'd never subscribed, so pages showed the default vaults instead of your own, and each subscribe or
  unsubscribe signed you up to every default vault again.
- **Ad inventory**: /sponsor/inventory crashed, and the inventory an ad could book came from reddit's traffic
  pipeline, so it was always zero. The site now counts views of each vault's listings (and the front page's) and
  predicts each day's inventory from the last two weeks (`tippr-job-update_promo_metrics`, now on a daily timer).
- **Docker**: the jobs container didn't run the gold expiry, feed bot or subscriber-count jobs; it now runs the same
  timers as an installed site.
- **The front page after renaming the site** on /admin/site wasn't found by its name in some places (ad targeting
  among them) until the site restarted.
- **Ad images** (the thumbnail and mobile image of an advertiser's sponsored post) couldn't be uploaded unless the
  site had an S3 bucket for them; without one they're now uploaded to the site itself and stored like other
  thumbnails when the ad is saved.
- **Signing up on a phone**: the Turnstile, hCaptcha or reCAPTCHA box was wider than the sign-up form (on a
  computer too); it now uses the services' compact size when the form is narrow. The phone menu no longer repeats
  the sidebar's small log-in box next to its "log in or sign up" link, so there's one way in, and your name at the
  top of the menu (a link to your profile) is easier to tap.

## 0.9.0
### ✨ Features and improvements
- **Vaults for admins** (/admin/vaults): admins can now create vaults whatever their karma and account age (the
  limits on /admin/config are for everyone else). The new page finds any vault and lists the newest and banned
  ones; on a vault's page admins can make it a front page default or featured (until now only
  `scripts/create_default_vaults.py` could), add or remove moderators without an invitation, and ban it, which is
  how a vault is removed: everyone but the admins sees a "banned" page (with an optional message) until it's
  unbanned. Each action is logged on the vault's page.
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

