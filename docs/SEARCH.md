# Search

Tippr searches posts and vaults with [OpenSearch](https://opensearch.org/)
(`search_provider = opensearch`). The installer sets it up by default.

## How it fits together

- The installer (`TIPPR_SEARCH=opensearch`) installs OpenSearch 3.x from its
  apt repository as a single node listening on `127.0.0.1:9200`, with the
  security plugin off (nothing outside the machine can reach it) and a
  `TIPPR_OPENSEARCH_HEAP` Java heap (default `1g`). Its config is
  `/etc/opensearch/opensearch.yml`, rewritten on every install.
- r2 writes to two indexes, `tippr_links` and `tippr_vaults`
  (`opensearch_index_prefix`).
- New and changed posts and vaults (submissions, edits, deletions, votes,
  comment counts) are queued on `cloudsearch_changes`; the `search_q`
  consumer (`tippr-consumer-search_q@1`) indexes them within seconds.
- The first install builds the index from the database.

`TIPPR_SEARCH=none` skips OpenSearch; search pages then show an error.

## Settings

In the ini (see `example.ini`):

| Setting | Default | |
|---|---|---|
| `opensearch_url` | `http://127.0.0.1:9200` | |
| `opensearch_index_prefix` | `tippr_` | Index names are this plus `links` and `vaults` |
| `opensearch_username` / `opensearch_password` | (none) | Only if the security plugin is on |
| `opensearch_verify_tls` | `true` | For an `https://` URL |

## Query syntax

Free text matches titles first, then self-post text, flair and URLs. It
tolerates small typos and accepts `"quoted phrases"`, `-word` and `OR`.
These fields can be mixed in; put `-` in front of one to exclude it:

| Field | Example |
|---|---|
| `vault:` | `vault:pics` |
| `author:` | `author:someone` |
| `site:` | `site:example.com` (also matches subdomains) |
| `nsfw:` | `nsfw:no` |
| `self:` | `self:yes` |
| `flair:` | `flair:meta` |
| `title:`, `selftext:`, `url:` | `title:release` |

Relevance results are nudged up by votes and down by age; the hot, top, new
and comments sorts and the time filters work as on listings. Vault search
ranks an exact name first, then names starting with the text, then titles
and descriptions, weighted by subscribers.

## Maintenance

Rebuild the index from scratch (drops it first, so search is empty until it
finishes; needed after a mapping change):

```bash
tippr-run -c 'from pylons import app_globals as g; g.search.rebuild_index(recreate=True)'
```

Without `recreate=True` it re-indexes everything in place.

Check OpenSearch:

```bash
curl -s 127.0.0.1:9200/_cluster/health?pretty
curl -s '127.0.0.1:9200/_cat/indices/tippr_*?v'
journalctl -u opensearch
```

A single node reports its health as green (indexes are created without
replicas). Adding nodes later is covered in [ROADMAP.md](ROADMAP.md).
