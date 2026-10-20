# Admin Features — How to access and what they provide

This document describes the admin features exposed by the local `r2` instance, where to find the handlers, and how to access them for testing.

## Quick: enable admin mode
- Turn on admin mode in your browser/session: GET `/adminon` (controller `forms`, action `adminon`). In production it asks for your two-factor code, so set up two-factor sign-in (preferences → security) first.
- Turn off admin mode: GET `/adminoff`.

Note: many admin endpoints require elevated flags (`VAdmin`, `VEmployee`) — enabling admin mode typically sets the session cookie used by the validators.

## Common admin endpoints
- `/admin/` — admin landing (controller=`awards`).
- `/admin/awards` — manage awards (list/edit awards).
- `/admin/awards/:awardcn/:action` — award actions (`give` or `winners`).
- `/admin/coins` — give a user Give Gold: prepaid months of gold they can gift to others (handler: `AdminToolController.GET_coins`).
- `/admin/gold` — give/take gold days for a user (handler: `AdminToolController.GET_gold`).
- `/admin/site` — the site's name, description, contact address and header logo. Saved values apply at once on every web process; blank ones fall back to the ini. Also shows how to change the domain (re-run the installer with `TIPPR_DOMAIN`).
- `/admin/antispam` — spam protection: the captcha for untrusted users (tippr's image captcha, Cloudflare Turnstile, hCaptcha, Google reCAPTCHA or none; on posting, messages, new vaults and, optionally, sign-up) and CleanTalk, which checks sign-ups and untrusted users' posts, comments and messages without a challenge. Spam sign-ups are refused; spam content is hidden in the moderators' spam queue. Saving checks the CleanTalk key.
- `/admin/errors` — recent unhandled errors, grouped by error and code location, with counts and the last traceback (kept in the hardcache; full logs in `journalctl -u tippr-paster`).
- `/admin/email` — outgoing email settings: SMTP or Gmail, and a test message ([EMAIL.md](EMAIL.md)).
- `/admin/ads` — Google AdSense settings ([INSTALL_tippr.md](INSTALL_tippr.md#google-adsense)).
- `/admin/payments` — the payment providers for gold and sold ads (PayPal, Stripe, Coinbase, BitPay): turn them on, enter their API keys and test them, see their webhook addresses, and look up or refund the latest payments ([gold-payments.md](gold-payments.md)).
- `/admin/backups` — export, import and restore the site, and transfer keys for moving servers ([BACKUP.md](BACKUP.md)).
- `/admin/vaults` — find any vault (and the newest and banned ones); on a vault's page, make it a front page default or featured, add or remove moderators without an invitation, and ban it (how a vault is removed: everyone but the admins sees a "banned" page; unbanning restores it). Each action is logged there. Admins can create vaults whatever their karma and account age; the `create_vault_*` limits on `/admin/config` are for everyone else.
- `/admin/privacy` — users' data export and deletion requests ([PRIVACY_FEATURES.md](PRIVACY_FEATURES.md)).
- `/admin/config` — the live settings (staff list, captcha and vault-creation thresholds, sidebar, welcome bar and announcement messages, API app rules and more), saved with one button and applied without a restart; every change is logged.
- `/admin/users` — every account, newest first a page at a time, or search by name, email or IP; an account's page shows its status, IPs, related accounts and support tickets, and lets admins put it in a timeout or suspend it (gold is given on `/admin/gold`).
- `/admin/feeds` — the RSS and Atom feeds that post into vaults, with their bot accounts, intervals and last errors ([CONTENT.md](CONTENT.md#feeds)).
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
- `admingold.html`
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
