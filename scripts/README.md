# Admin scripts

This directory contains ad-hoc admin and diagnostic scripts used during
maintenance and migration tasks. Many of these scripts interact directly with
Cassandra and may mutate production data.

Safety rules before using any script that mutates data:

- Prefer running these scripts in a development or staging environment first.
- Scripts that write require either `--force` on the command-line or the
  environment variable `TIPPR_ALLOW_MUTATE=1` to actually perform writes.
- Use `--dry-run` where available to preview actions.
- Review the script source before running; do not run as root unless necessary.

## Site setup and maintenance

Run these with `tippr-run` (e.g. `tippr-run $TIPPR_HOME/src/tippr/scripts/import_feeds.py`).
The installer runs the first four on every install; they're safe to re-run.

- `create_default_user.py`: the admin account.
- `create_default_vaults.py`: the starter vaults, and the front page
  defaults if the site has none (docs/CONTENT.md).
- `create_default_awards.py`: the starter awards (trophies).
- `init_policy_wiki_pages.py`: the policy and help pages from docs/policies
  and docs/help, kept up to date on every install except pages an admin
  edited on the site (`FORCE_POLICY_IMPORT=1` replaces those too).
- `import_feeds.py`: see below; adds the starter feeds.
- `prune_default_vaults.py`: takes front page defaults without an enabled
  feed off the list (`PRUNE_DRY_RUN=1` to preview, `PRUNE_KEEP=a,b` to keep
  some).
- `fix_feed_titles.py`: decodes HTML codes (`&#8216;`) left in feed posts'
  titles (`FIX_DRY_RUN=1` to preview).
- `backfill_thumbnails.py`: queues recent link posts without a thumbnail
  for the thumbnail finder (`THUMB_DAYS`, default 3).
- `gmail_oauth_setup.py`: connects a Google account for sending email
  (docs/EMAIL.md).

## Maintenance and diagnostics

Files:

- `import_policy_cqlsh.py`: imports policy pages into Cassandra via `cqlsh`.
  Supports `--dry-run` and `--force`. Configure Cassandra connection via
  `--host/--port/--user/--password` or the environment variables
  `CASSANDRA_HOST`, `CASSANDRA_PORT`, `CASSANDRA_USER`, `CASSANDRA_PASS`.

- `force_create_revs.py`: creates `WikiRevision` rows from `docs/policies`.
  Requires `--force` or `TIPPR_ALLOW_MUTATE=1` and supports `--dry-run`.

- `force_revise_policies.py`: revises existing `WikiPage` content from
  `docs/policies`. Requires `--force` or `TIPPR_ALLOW_MUTATE=1` and supports
  `--dry-run`.

- `import_feeds.py`: adds many feeds to /admin/feeds at once from a list
  (`FEEDS_FILE`, default `starter_feeds.txt`: public feeds for the vaults
  `create_default_vaults.py` makes). A dry run unless `FEEDS_ADD=1` or
  `TIPPR_ALLOW_MUTATE=1`; an address can be a site's homepage if the page
  links to its feed. The installer runs it with `FEEDS_STARTER=auto|1|0`
  (`TIPPR_STARTER_FEEDS`), which adds only feeds not offered to the site
  before, so feeds an admin removed stay removed. Run it with `tippr-run`.

- `migrate_media_to_s3.py`: copies `/srv/www/media` into an S3-compatible
  bucket before switching the site to it (docs/STORAGE.md). A dry run unless
  `TIPPR_ALLOW_MUTATE=1`; skips files already copied. Run it with `tippr-run`.

- `inspect_cassandra.py`: read-only inspection of app Cassandra pools.

- `inspect_wikirevision_schema.py`: prints the `wikirevision` table schema.

- `inspect_wikirevs.py`: scans `WikiRevision` rows; use `--limit` to control
  scan size and `--match` to filter by pageid.


Use examples:

```bash
# Dry-run import
python3 scripts/import_policy_cqlsh.py --dry-run

# Create revisions (force)
TIPPR_ALLOW_MUTATE=1 python3 scripts/force_create_revs.py --force

# Revise policies with confirmation env
TIPPR_ALLOW_MUTATE=1 python3 scripts/force_revise_policies.py --force

# Inspect schema
python3 scripts/inspect_wikirevision_schema.py --host 127.0.0.1
```
