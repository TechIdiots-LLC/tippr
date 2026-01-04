# Admin Features — How to access and what they provide

This document describes the admin features exposed by the local `r2` instance, where to find the handlers, and how to access them for testing.

## Quick: enable admin mode
- Turn on admin mode in your browser/session: GET `/adminon` (controller `forms`, action `adminon`).
- Turn off admin mode: GET `/adminoff`.

Note: many admin endpoints require elevated flags (`VAdmin`, `VEmployee`) — enabling admin mode typically sets the session cookie used by the validators.

## Common admin endpoints
- `/admin/` — admin landing (controller=`awards`).
- `/admin/awards` — manage awards (list/edit awards).
- `/admin/awards/:awardcn/:action` — award actions (`give` or `winners`).
- `/admin/creddits` — give creddits to a user (handler: `AdminToolController.GET_creddits`).
- `/admin/gold` — give/take gold days for a user (handler: `AdminToolController.GET_gold`).
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
- `admincreddits.html`
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
- Admin page helpers and sidebars: `r2/r2/lib/pages/admin_pages.py` and `r2/r2/lib/pages/pages.py` (admin page classes such as `AdminPage`, `AdminNotesSidebar`, `AdminCreddits`, `AdminGold`).
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
3. Open an admin page, e.g.: `GET /admin/creddits` or `GET /admin/gold`.
4. Check `/health` and `/health/caches` for quick system checks.

## Next improvements
- Document any plugin-provided admin pages (plugins may add `/admin/*` routes).
- Add a debug helper page that lists rendercache stub keys and recent misses for local development.

---
Generated on: January 1, 2026
