# Admin Features — How to access and what they provide

This document describes the admin features exposed by the local `r2` instance, where to find the handlers, and how to access them for testing.

## Quick: enable admin mode
- Turn on admin mode in your browser/session: GET `/adminon` (controller `forms`, action `adminon`). With two-factor sign-in (production requires it: set it up under preferences → security first) it sends you to "confirm it's you" (`/two_factor/confirm`) unless you entered a code in the last 15 minutes or chose "remember this computer" there; then it's one button. Without two-factor (`disable_require_admin_otp`), your password.
- Turn off admin mode: GET `/adminoff`.

Note: many admin endpoints require elevated flags (`VAdmin`, `VEmployee`) — enabling admin mode typically sets the session cookie used by the validators.

## Members' two-factor sign-in
- Any member can turn on two-factor sign-in under preferences → security, with one or more methods: authenticator apps and passkeys (up to 10 of each), plus ten one-use recovery codes. Adding or removing a method needs a code from one they already have (the password for the first; removing the last also needs the password). Wherever a code is asked for, "use a passkey" works instead. Passkeys work only on the site's own https address (the WebAuthn relying party is `https_endpoint`'s host), so moving the site to a new domain means members add their passkeys again. It then locks preferences → security and the password and email page until a code is entered on "confirm it's you" (`r2.lib.pages.TwoFactorConfirm`, the one place a code is asked for once signed in, also for admin mode), which unlocks their forms (changing the password or email address, linking or unlinking a sign-in, the two-factor methods); and, if the member chooses, asks at login (with "don't ask again on this device for 30 days"), locks every preferences page the same way, and asks when submitting a post. Turning it off and deleting the account need a code entered in the last 5 minutes (`two_factor.fresh`; the form links to "confirm it's you" when it's older, and the API takes the code as `otp`). A code counts for 15 minutes in that session, and opening a preferences page keeps it counting (but doesn't make it fresh); OAuth apps are never asked. Code: `r2/lib/two_factor.py`, `r2/lib/passkeys.py`, `public/static/js/passkey.js`.
- `require_two_factor_staff` on `/admin/config` (off by default) makes moderators, employees and admins turn it on before their tools work (they see a notice until then).
- Someone locked out without their phone or recovery codes: reset their two-factor on `/admin/users`.

## Common admin endpoints
- `/admin/` — admin landing (controller=`awards`).
- `/admin/awards` — manage awards (list/edit awards).
- `/admin/awards/:awardcn/:action` — award actions (`give` or `winners`).
- `/admin/coins` — give a user Give Gold: prepaid months of gold they can gift to others (handler: `AdminToolController.GET_coins`).
- `/admin/gold` — redirects to `/admin/users` (or the account given as `?recipient=`), where gold is given now.
- `/admin/site` — the site's name, description, contact address and header logo. Saved values apply at once on every web process; blank ones fall back to the ini. Also shows how to change the domain (re-run the installer with `TIPPR_DOMAIN`), and the sitemap choice: recent posts (made when asked for), or every post, built each day by `tippr-job-sitemaps` in as many 50,000-address sitemaps as it takes (`r2/lib/sitemaps`).
- `/admin/antispam` — spam protection: the captcha for untrusted users (tippr's image captcha, Cloudflare Turnstile, hCaptcha, Google reCAPTCHA or none; on posting, messages, new vaults and, optionally, sign-up) and CleanTalk, which checks sign-ups and untrusted users' posts, comments and messages without a challenge. Spam sign-ups are refused; spam content is hidden in the moderators' spam queue. Saving checks the CleanTalk key.
- `/admin/errors` — recent unhandled errors, grouped by error and code location, with counts and the last traceback (kept in the hardcache; full logs in `journalctl -u tippr-paster`).
- `/admin/email` — outgoing email settings: SMTP or Gmail, and a test message ([EMAIL.md](EMAIL.md)).
- `/admin/ads` — Google AdSense settings ([INSTALL_tippr.md](INSTALL_tippr.md#google-adsense)).
- `/admin/payments` — the payment providers for gold and sold ads (PayPal, Stripe, Coinbase, BitPay): turn them on, enter their API keys and test them, see their webhook addresses, and look up or refund the latest payments ([gold-payments.md](gold-payments.md)).
- `/admin/logins` — sign-in providers: turn on "sign in with" Google, Facebook, GitHub, Discord or Apple with the site's own OAuth app (client ID and secret), and see the redirect address to register with the provider. Members link an account under preferences → security, or by logging in with their password the first time they sign in with it (or make a new account with it, while sign-ups are open); it only ever signs in to an account that linked it, and members who chose to be asked for their two-factor code at login are asked here too.
- `/admin/backups` — export, import and restore the site, and transfer keys for moving servers ([BACKUP.md](BACKUP.md)).
- `/admin/servers` — every server's last report (each sends one a minute, `tippr-job-server_status`): version, load, memory, disks and services, with warnings for one not heard from, short of disk or memory, busy, running a different version or sharing a name; and the RabbitMQ queues (what's waiting, and whether anything processes it). Only the latest report per server is kept; one gone for 7 days drops off, or "forget" it. Code: `r2/lib/server_status.py`, `scripts/server_status.py`. It also shows the newest release on GitHub and which servers run an older one, and can update them to a release, one server at a time ([PROXMOX.md](PROXMOX.md#updating-from-adminservers); `r2/lib/releases.py`, `r2/lib/server_update.py`, `scripts/tippr_update.py`).
- `/traffic` (staff) — pageviews and unique visitors, plus activity: new visitors, sign-ups, logins (and failed ones), posts, comments, votes, reports, moderator actions by type, messages and modmail, for 24 hours, 7 days, 30 days and by day. A vault's `/about/traffic` shows its own for its moderators (posts, comments and votes only, to everyone, if the vault makes its traffic public). Activity is counted from the site's event calls as they happen (`r2/lib/activity_counter.py`); only the counts are kept, hourly for 31 days and daily indefinitely.
- `/admin/vaults` — find any vault (and the newest and banned ones); on a vault's page, make it a front page default or featured, add or remove moderators without an invitation, and ban it (how a vault is removed: everyone but the admins sees a "banned" page; unbanning restores it). Each action is logged there. Admins can create vaults whatever their karma and account age; the `create_vault_*` limits on `/admin/config` are for everyone else.
- `/admin/privacy` — members' data export requests that are waiting, processing or failed, to send again or cancel, and a form to start an export for a member ([PRIVACY_FEATURES.md](PRIVACY_FEATURES.md)).
- `/admin/config` — the live settings (staff list, captcha and vault-creation thresholds, sidebar, welcome bar and announcement messages, API app rules, requiring two-factor sign-in for moderators and staff, live comments (new comments appear on open threads, in the vaults whose moderators turn it on in their settings; `r2/lib/live_comments.py`) and more), saved with one button and applied without a restart; every change is logged. Its caching panel shows how memcached and the nginx caches are doing, and can empty memcached.
- `/admin/users` — every account, newest first a page at a time, or search by name, email or IP; an account's page shows its status, IPs, related accounts and support tickets, and lets admins put it in a timeout or suspend it, and give or take months of gold (up to 120 at once), make an account's gold permanent (it never expires: the daily expiry job and refunds leave it, `Account.gold_permanent`), or remove it. Every action is recorded in the account's admin log (`r2/lib/user_admin.py`).
- `/admin/feeds` — the RSS and Atom feeds that post into vaults, with their bot accounts, intervals and last errors, newest first; search them, filter by vault, bot or status (active, paused, with errors, never checked), sort by any column (reports: the reports on its posts, by reason; votes: the votes and comments on its posts, and the share with either, added up hourly by `tippr-job-feed_stats`), and edit one in place, including the vault it posts to; delete one with its posts, all of them or the ones nobody voted on or commented on (`post_cleanup.remove_feed`). The view is in the address (`?q=`, `vault=`, `bot=`, `status=`, `sort=`, `order=`, `r2/lib/feed_view.py`) ([CONTENT.md](CONTENT.md#feeds)).
- `/admin/cleanup` — cleaning up posts nobody took an interest in: older than a rule's age, with no comments and no votes besides the author's, and not stickied, gilded, promoted, reported or removed by a moderator. Feed bots' posts and members' posts have rules of their own (days old, each off until turned on), and `tippr-job-cleanup_posts` runs the ones that are on each night, at most the page's posts-a-day cap. A search finds the posts that qualify now (feed bots' or members', older than so many days, in a vault, by a bot) to clean up the ones ticked, each checked again first; recent runs are listed. A cleaned-up post is deleted as its author would delete it, and its thumbnail and preview image are deleted when no other live post uses them (they're named after their content, so posts with the same image share one). A feed doesn't post the same item again (`r2/lib/post_cleanup.py`).
- `/admin/apps` — registered API apps: approve, suspend or delete them (new apps can need approval, `apps_require_approval` on /admin/config).
- `/admin/domains` — banned domains: links to them can't be posted.
- `/admin/support` — the support queue: messages to the admins (the contact page) become tickets with a category, status and assignee; `/admin/support/staff` grants employees categories to read or answer.
- `/traffic` and related routes — promoted link and traffic analytics (sitewide, language, advert traffic pages). Requires `VEmployee()`.
- `/about/log` — moderation/audit log pages.
- `/health` — JSON versions and service info.
- `/health/caches` — memcache health check.
- `/health/ads` — ad subsystem health.

## Admin notes (per system)
- UI: admin notes sidebar rendered via `AdminNotesSidebar` (used on profile and admin pages).
- Model: `AdminNotesBySystem` ([r2/r2/models/admin_notes.py]) provides:
  - `add(system_name, subject, note, author)` — add a note.
  - `in_display_order(system_name, subject)` — list notes for `user`, `vault`, `domain`, or `ip`.

## Admin templates (common)
Files under `r2/r2/templates/` used by admin pages include:
- `admincoins.html`
- `adminawards.html`
- `adminawardgive.html`
- `adminawardwinners.html`
- `adminerrorlog.html`
- `adminbar.html`
- `admininterstitial.html`
- `adminnotessidebar.html`

## Where to look in the codebase
- Controller endpoints: `r2/r2/controllers/admin.py` and other controllers (see `r2/r2/config/routing.py` for mappings).
- Admin page helpers and sidebars: `r2/r2/lib/pages/admin_pages.py` and `r2/r2/lib/pages/pages.py` (admin page classes such as `AdminPage`, `AdminNotesSidebar`, `AdminCoins`, `AdminGold`).
- Admin notes model: `r2/r2/models/admin_notes.py`.
- Templates: `r2/r2/templates/*` (listed above).

## Logging & statistics accessible to admins
- Traffic/analytics: `/traffic` (promoted link traffic), `/traffic/languages/:langcode`, `/traffic/adverts/:code`, sitewide reports served by `r2/r2/lib/pages/trafficpages.py` and `FrontController` handlers.
- Health endpoints: `/health`, `/health/caches`, `/health/ads` (`r2/r2/controllers/health.py`).
- Error logging: errors go through the error controller and are logged via `log.write_error_summary` and `g.log.error` (`r2/r2/controllers/error.py`). An admin error log UI uses `adminerrorlog.html`.
- Moderation/audit logs: `/about/log` (moderation log pages rendered by front controller).

## Troubleshooting tips (admin/testing)
- If an admin page returns HTML with fragment placeholders like `<$>h...html</$>`:
  - Those are `CacheStub` placeholders emitted by the fragment cache/wrapper (`r2/r2/lib/wrapped.py` / `wrapped.pyx`).
  - Check `g.rendercache.get_multi(...)` (app globals) and your memcached/mcrouter configuration; missing keys or cache misses leave placeholders in the output.
  - To debug: enable a temporary dev `NullCache` or add logging around `g.rendercache.get_multi` to record requested stub keys and hits/misses.

## Quick test steps
1. Start the app locally and your memcached (if you want real fragment caching).
2. In a browser or curl, enable admin: `GET /adminon`.
3. Open an admin page, e.g.: `GET /admin/site` or `GET /admin/users`.
4. Check `/health` and `/health/caches` for quick system checks.

## Next improvements
- Document any plugin-provided admin pages (plugins may add `/admin/*` routes).
- Add a debug helper page that lists rendercache stub keys and recent misses for local development.

---
Updated: October 19, 2026
