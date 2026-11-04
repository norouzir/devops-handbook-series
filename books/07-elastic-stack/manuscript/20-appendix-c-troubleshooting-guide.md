# Appendix C - Troubleshooting Guide {#appC}

Organized by symptom, in the order an operator usually meets them. Every entry names the signal first (what you actually see), then the likely causes, then the fix - and points back to the chapter that owns the concept.

## C.1 Cluster and Node Symptoms

**Cluster status is yellow.** Normal on a single-node sandbox (replicas cannot be placed anywhere; [Chapter 2](#ch2)) - or a real signal elsewhere: a node is down or disk-constrained and replicas lost their homes. `GET _cat/shards?v` filtered to `UNASSIGNED`, and `GET _cat/allocation?v` tell you which; the allocation-explain API (`GET _cluster/allocation/explain`) says *why* in prose.

**Cluster status is red.** Primary shards are unavailable: a node lost with unreplicated primaries, disk at flood stage, or a corrupted shard. First: `GET _cluster/health?level=indices` to scope the damage; `GET _cat/allocation?v` for disk; look for `read_only_allow_delete` blocks ([Chapter 11](#ch11) watermarks). Do not restart nodes before scoping - restarts make the cluster re-shuffle shards, which can turn a one-index incident into a cluster-wide one.

**Node keeps leaving and rejoining the cluster.** The classics: heap pressure with long GC pauses making nodes appear dead (raise heap to half of RAM, watch `heap.percent` in `GET _cat/nodes?v`), network flakiness on the transport layer, or under-provisioned master-eligible nodes delaying elections ([Chapter 11](#ch11) topology). `GET _cat/master?v` and the master's logs name the culprit.

**`429 too_many_requests` on bulk indexing.** The write thread pool is rejecting: ingest is outrunning the cluster. Slow down or batch smarter client-side (5-15 MB bulks, fewer concurrent clients), stretch `refresh_interval` during ingest bursts, and check whether undersized shards are amplifying per-document cost ([Chapter 11](#ch11)). Rejections are back-pressure, not failure - the client retries; but sustained rejections are a capacity plan waiting to be written.

**`cluster_block_exception: index read-only`** after a disk-full episode. The flood-stage watermark locked the index and it stays locked even after space is freed:

```text
PUT <index>/_settings
{ "index.blocks.read_only_allow_delete": false }
```

Fix the disk first ([Chapter 11](#ch11)), then unlock, then verify writes - in that order.

## C.2 Mapping and Search Symptoms

**A search returns nothing you know exists.** Three suspects in order: the field is `text` and you used `term` (exact term vs analyzed text - [Chapter 5](#ch5), [Chapter 6](#ch6); check `GET <index>/_mapping`, test with `_analyze`); the time filter excludes your document (compare `@timestamp` values in Discover - the timezone parse of the ingest pipeline is the usual culprit, [Chapter 4](#ch4)); or you are searching the wrong index pattern (data streams rename under your feet - `GET _data_stream/*`).

**A document appears in Discover only after a delay.** The one-second refresh interval ([Chapter 2](#ch2), [Chapter 3](#ch3)) - by design. A dashboard that must show "now" reads with a small look-back and the Kibana UI refreshes automatically; scripts that need instant visibility call `POST <index>/_refresh` explicitly, and accept its cost.

**Mapping has hundreds of unexpected fields.** Dynamic mapping absorbed something noisy ([Chapter 5](#ch5)): a shipper emitting per-host keys, user data indexed raw. Fix forward - correct the shipper, add `dynamic: strict` to the template, create a new index/stream (mappings cannot be edited in place); the old index ages out under ILM ([Chapter 10](#ch10)). Field-count guard rail: `GET <index>/_mapping` piped to your JSON tool and counted, weekly, on the noisy streams.

**Aggregation fails with "field is not aggregatable" or sorting errors.** You are aggregating a `text` field; use the `.keyword` sub-field or re-map to `keyword` ([Chapter 5](#ch5) Section 5.2, [Chapter 7](#ch7) best practice).

## C.3 Ingestion Symptoms

**Filebeat/Agent is running and shipping nothing.** Check, in order: the registry and input paths (permissions - the `user: root` pattern for containerized Beats reading host logs, [Lab 2](#lab2)); the output (a TLS or API-key error in the shipper's own logs - `filebeat -e` prints to stdout for exactly this); and the pipeline reference (a named ingest pipeline that does not exist drops events with an error in the shipper log). The `filestream` input needs its `id` unique - duplicate ids across two agents silently split the file.

**Logs arrive but timestamps are ship-time, not event-time.** The date processor never matched: wrong `formats` entry, or the field it reads was already removed. Re-run `_simulate` with a real line ([Chapter 4](#ch4)); every time-based query, dashboard, and ILM decision downstream keys on `@timestamp`, so this is a stop-the-line bug.

**Duplicate documents after a shipper restart.** At-least-once delivery means the shipper re-sent its tail ([Chapter 4](#ch4)): harmless for search unless document ids were engine-generated. When exact dedup matters, derive `_id` from content (a hash of the log line) in the ingest pipeline - writes become idempotent.

**Fleet agents show "Degraded" or "Stale".** Check-in failures: Fleet Server reachability (network, certificate), Elasticsearch capacity (agents write their own status indices), or an enrollment token expired. Fleet's agent list shows the last check-in; the agent's own logs on the host (`/var/lib/elastic-agent`) complete the picture ([Chapter 14](#ch14)).

## C.4 Lifecycle and Storage Symptoms

**A data stream stopped rolling over.** The hot index keeps growing; `GET <stream>/_ilm/explain` shows the step waiting. Usual causes: the rollover threshold is unreachable (`max_age` on a stream with no writes; or `max_primary_shard_size` set while `index.number_of_shards` > 1 makes the *per-shard* threshold effectively unreachable - size rollovers assume 1 primary, [Chapter 10](#ch10)), or the ILM index-wide retry counter is exhausted from a persistent error (visible in explain).

**Disk fills faster than the delete phase.** Retention math vs ingest rate ([Chapter 10](#ch10) Section 10.5): either the windows are too long for the volume, or the warm tier is absorbing what delete should have removed (a policy attached to new indices only - old indices keep their old policy; `GET _data_stream/*` shows which). Interim relief: lower `number_of_replicas` on old warm data, or move the delete `min_age` earlier - deliberately, with the retention table as the record.

**ILM phase never advances.** Explain output shows the index waiting on a phase action that cannot complete on current hardware - an `allocate` action demanding a tier with no nodes ([Chapter 10](#ch10) hot-warm-cold), or a forcemerge blocked by read-only blocks. The fix is either hardware (add the tier) or policy (remove the action).

## C.5 Kibana Symptoms

**Dashboards are empty but Discover is not.** The data view's pattern or timestamp field does not match the data (`logs-nginx-*` vs a renamed stream; a data view without a time field shows no time picker). Check Stack Management → Data Views against `GET _data_stream/*` ([Chapter 9](#ch9)).

**"Kibana server is not ready yet".** Kibana cannot reach Elasticsearch or is mid-migration: check `kibana.yml` credentials (the `kibana_system` user), TLS CA path, and Elasticsearch health; on upgrades, the `.kibana` migration runs on first start and needs patience, not restarts.

**Saved objects gone after a cluster rebuild.** They live in indices - they ride snapshots only if `.kibana*` is included ([Chapter 13](#ch13)); otherwise they are re-importable from exported JSON (the Lab 4 export). This is the reminder to check your snapshot `indices` lists right now.

## C.6 Where to Look Next

The debug order that never disappoints: the error message's `type` and `reason` (Elastic's errors are unusually honest); `GET _cat/*` for the resource picture; the relevant `explain` API (`_cluster/allocation/explain`, `_ilm/explain`, task API for slow queries); then the component's own logs (Elasticsearch, Kibana, the shipper) - each names its problem more precisely than any web search will. The series' standing rule applies: read the machine's words before the internet's opinions.
