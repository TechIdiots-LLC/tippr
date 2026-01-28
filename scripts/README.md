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
