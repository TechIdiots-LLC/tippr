# Vault Migration Runbook (sr → vault)

Summary
- This document describes the recommended, safe sequence to migrate persisted names and query caches from `sr`/`subreddit` to `vault` in Tippr.

Preconditions
- Take Cassandra snapshots (`nodetool snapshot -t pre_vault_rename tippr`).
- Ensure Solr cores are accessible and you have a staging environment.

High-level steps
1. Create new Cassandra CFs
   - Create `subscribed_vaults_by_account`, `vault_query_cache`, and any other `vault_*` CFs non-destructively.
2. Backfill data into new CFs (staging)
   - Run backfill scripts in `scripts/migrate/backfill/` with conservative limits.
   - Validate sample rows and counts.
3. Reindex Solr to include `vault_id`
   - Add `vault_id` field via Solr Schema API if missing.
   - Reindex documents (app indexer preferred) so each document has `vault_id`.
   - Validate totals and per-vault facets.
4. Deploy read-paths to use new CFs
   - Roll out code that reads `vault_*` CFs in staging first; use feature flags if available.
5. Verify end-to-end
   - Run integration checks, sample queries, UI spot-checks, and confirm consumers (traffic jobs) read new outputs.
6. Stop writing old names & capture deltas
   - Disable old writes or enable dual-write for a brief period; re-run backfills to capture deltas.
7. Cleanup (destructive)
   - After verification window and final backups: drop old CFs and remove legacy Solr fields via Schema API.

Validation commands (examples)
- Solr field add:
```bash
curl -s -X POST -H 'Content-type:application/json' --data-binary '{"add-field": {"name":"vault_id","type":"string","stored":true,"indexed":true}}' http://SOLR_HOST:8983/solr/CORE/schema
```
- Solr count check:
```bash
curl 'http://SOLR_HOST:8983/solr/CORE/select?q=vault_id:*&rows=0&wt=json' | jq '.response.numFound'
```
- Cassandra snapshot:
```bash
nodetool snapshot -t pre_vault_rename tippr
```

Recommendations
- Always test in staging first.
- Use `--dry-run` and small `--limit` values for initial backfills; I can add flags to backfill scripts.
- Keep old CFs and Solr fields until after a verification window and confirmed backups.

Notes
- I searched the repo docs and found no direct `subreddit`/`sr` tokens inside `docs/` that require automated replacement. `docs/PRODUCTION_DEPLOYMENT.md` contains historical attribution to Reddit (intentional). Please review that file manually to ensure references to the original project are acceptable.

If you want, I will:
- (A) add `--dry-run`/`--after`/`--limit` flags to backfill scripts now, or
- (B) generate exact CQL statements for every `*_cf` used by models, or
- (C) prepare a timed maintenance playbook including hostnames and exact commands (provide host/core names).

