# Appendix A - Query DSL, API, and ES|QL Quick Reference {#appA}

## A.1 The API Map

| Endpoint | Purpose |
|---|---|
| `GET /` | Node identity, version |
| `GET _cluster/health` | Status: green / yellow / red |
| `GET _cat/nodes?v` | Heap, disk, CPU, roles per node |
| `GET _cat/indices?v&bytes=mb` | All indices: docs, size, health |
| `GET _cat/shards?v` | Shard placement and state |
| `GET _cat/thread_pool/search?v` | Search queue and rejections |
| `GET _cluster/pending_tasks` | Master backlog |
| `GET _data_stream/<name>` | Backing indices, ages, sizes |
| `GET <index>/_ilm/explain` | Lifecycle position per index |
| `GET <index>/_mapping` | Live field definitions |
| `GET <index>/_settings` | Index settings |
| `POST _refresh` / `POST _flush` | Visibility / durability helpers |

## A.2 Query DSL Skeletons

Full-text and structured filtering ([Chapter 6](#ch6)):

```json
{ "query": { "bool": {
    "must":     [ { "match":        { "message": "payment timeout" } } ],
    "filter":   [ { "term":         { "level": "error" } },
                  { "terms":        { "http.response.status_code": [500, 502] } },
                  { "range":        { "@timestamp": { "gte": "now-1h" } } },
                  { "exists":       { "field": "trace.id" } },
                  { "prefix":       { "url.path": "/checkout" } } ],
    "must_not": [ { "term":         { "service.name": "healthcheck" } } ]
} } }
```

Aggregation tree ([Chapter 7](#ch7)):

```json
{ "size": 0,
  "query": { "range": { "@timestamp": { "gte": "now-24h" } } },
  "aggs": {
    "over_time": { "date_histogram": { "field": "@timestamp",
                                       "fixed_interval": "5m", "min_doc_count": 0 },
      "aggs": { "avg_ms": { "avg": { "field": "url.request_duration_ms" } } } },
    "worst_paths": { "terms": { "field": "url.path", "size": 10,
                                "order": { "p99": "desc" } },
      "aggs": { "p99": { "percentiles": { "field": "url.request_duration_ms",
                                          "percents": [99] } } } }
} }
```

Mapping and template essentials ([Chapter 5](#ch5)):

```json
{ "properties": {
    "@timestamp": { "type": "date" },
    "service":    { "type": "keyword" },
    "message":    { "type": "text" },
    "status":     { "type": "integer" },
    "client.ip":  { "type": "ip" } } }
```

```json
{ "index_patterns": ["logs-*"], "data_stream": {},
  "template": { "settings": { "index.lifecycle.name": "logs-policy",
                              "index.number_of_shards": 1 } } }
```

## A.3 ES|QL Cheat Sheet

| Command | Does |
|---|---|
| `FROM <index> [METADATA _id, _index]` | Source rows (index, pattern, or data stream) |
| `WHERE <condition>` | Filter rows (`==`, `!=`, `IN`, `LIKE`, `RLIKE`, ranges) |
| `KEEP a, b` / `DROP c` | Project / remove columns |
| `EVAL x = <expr>` | Compute columns |
| `STATS m = FN(f) [BY g, bucket(@timestamp, 5 minutes)]` | Aggregate (COUNT, SUM, AVG, MIN, MAX, PERCENTILE, MEDIAN, COUNT_DISTINCT, TOP; `COUNT(*) WHERE <cond>`) |
| `SORT a DESC, b ASC NULLS LAST` / `LIMIT n` | Order / cap (default 1000, max 10,000 rows) |
| `ENRICH <policy>` | Lookup-join reference data |
| `DISSECT` / `GROK <field> "..."` | Parse text at query time |

Date and time: `NOW() - 1 hour`, `bucket(@timestamp, 1 hour)`, comparisons against ISO strings. Strings: double quotes; wildcards with `LIKE`; regex with `RLIKE`.

## A.4 Ingestion and Lifecycle One-Liners

```text
PUT _ingest/pipeline/<name>          # processors: grok, date, set, remove, ...
POST _ingest/pipeline/<name>/_simulate
PUT _ilm/policy/<name>               # phases: hot (rollover), warm, cold, delete
PUT _index_template/<name>           # data_stream: {}, composed_of, priority
GET  _data_stream/*                  # audit streams weekly
GET  <stream>/_ilm/explain           # why is this index still hot?
```

Rollover threshold of record: `"max_primary_shard_size": "50gb"` (with `"max_age"` as backstop).

## A.5 Security and Backup One-Liners

```text
PUT  _security/role/<name>           # indices: names, privileges, FLS grant, DLS query
PUT  _security/user/<name>           # roles: [...]
POST _security/api_key               # name, expiration, role_descriptors
DELETE _security/api_key/<id>        # revoke one credential
PUT  _snapshot/<repo>                # type fs|s3|azure|gcs + settings
PUT  _slm/policy/<name>              # schedule, repository, retention
POST _snapshot/<repo>/<snap>/_restore  # indices, rename_pattern
```

Diagnostic habit: `GET _cluster/health` and `GET _cat/nodes?v` before anything else, always ([Chapter 2](#ch2)).
