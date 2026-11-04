# Chapter 11 - Scaling Elasticsearch: Shards, Capacity, and Performance {#ch11}

## 11.1 The Decisions That Age Badly

Elasticsearch clusters fail at scale in two symmetric ways, and both are decisions made early with consequences paid late. **Oversharding** - the instinct that more shards means more parallelism - leaves a cluster of ten thousand tiny shards that spends its heap on shard metadata, its file handles on half-empty segments, and its query time on fan-out overhead. **Undersharding** - one enormous shard per index - serializes writes, makes recovery a day-long event, and turns rebalancing into a game of Tetris with pieces the size of refrigerators. Both come from the same mistake: treating shard count as a performance knob rather than a storage-layout decision.

The arithmetic that keeps clusters healthy has been stable for years, and current versions automate more of it than ever (data streams and size-based rollover, [Chapter 10](#ch10), embody it). Target **shard sizes in the tens of gigabytes** - the working band is roughly 20 to 50 GB, with Elastic's guidance settling around that range for years. Keep **per-node shard counts in the hundreds**, not thousands - heap per shard is real and non-negotiable. Let **rollover by size** - not by calendar - keep shards uniform. A cluster that obeys these three rules at creation time almost never needs a reindex for shard reasons; a cluster that ignores them schedules one.

## 11.2 Heap, Memory, and the Watermarks

Three resource ceilings define Elasticsearch capacity planning, and all three are measured, not guessed.

**JVM heap** follows two linked rules: heap no more than **half of the machine's RAM** (the rest stays for the OS page cache, which Lucene's reads depend on), and never past the **compressed-oops ceiling around 31 GB** (below ~32 GB, Java object pointers stay compressed and effective memory per heap byte is significantly larger; past it, heap buys less). A 64 GB data node therefore runs ~31 GB of heap and leaves ~33 GB for the filesystem cache. Heap pressure shows up as old-generation GC pauses before it shows up as slowness; `GET _cat/nodes?v` (the `heap.percent` column) and Stack Monitoring's GC metrics are the daily readings, and a node that lives above 75% heap needs a reason, not a shrug.

**Disk watermarks** are the cluster's self-preservation: at 85% disk used, Elasticsearch stops allocating new shards to the node (`low`); at 90%, it starts *moving* shards off (`high`); at 95%, it marks indices read-only (`flood_stage`). The sequence is deliberate - degrade before you die - but the read-only lockout has stranded many teams who let a disk fill at 2 a.m.; clearing it requires `index.blocks.read_only_allow_delete: false` per index *after* freeing space. Monitoring at 70% and acting at 80% is the operational discipline; ILM's delete phase ([Chapter 10](#ch10)) is the mechanism that keeps the discipline automatic.

**File descriptors and thread pools** complete the picture - `ulimit` of 65,535 for Elasticsearch's user is in every install guide and still surprises someone monthly - and `_cat/thread_pool/search?v` (queue sizes, rejections) is where query pressure becomes visible before users complain.

## 11.3 Topology: Which Nodes Do What

Scaling a cluster is mostly role assignment. The **hot-warm-cold tiering** of [Chapter 10](#ch10) handles the storage economics; role separation handles the failure and load economics. Dedicated **master-eligible** nodes (three of them, modest hardware - 8 GB RAM is plenty for all but the largest cluster states) insulate cluster stability from data-node load: a master that also indexes at full tilt delays cluster-state updates, and cluster-state delays look like inexplicable cluster-wide flapping. Dedicated **coordinating** nodes absorb client load for large query populations - dashboards, scripts, integrations all hammering one cluster benefit from a buffer layer that holds no data and cannot be slowed by merges.

A reference production shape for a mid-size observability estate: three master-eligible (small), four to eight hot data nodes (NVMe, big heap), four to eight warm data nodes (dense, cheap), two coordinating nodes, and - when the lifecycle policy includes cold/frozen - a tier of nodes (or none at all, with searchable snapshots on object storage). Below that size, combined roles are honest economics: a three-node cluster of do-everything data nodes with `master` eligibility is a fine production cluster. Above it, separation stops being optional.

::: {.note}
**Best practice - scale writes first, reads second**

Log estates scale in one dimension mostly: ingest rate. Size the hot tier by the write path - daily ingest volume divided by per-node indexing throughput, with headroom for spikes and recovery - and size read capacity by adding replicas ([Chapter 2](#ch2)), which spread read load without changing shard layout. Clusters sized this way meet their first scaling wall in disk, not CPU - which ILM exists to manage.
:::

## 11.4 Query Performance: Where the Time Goes

A search request in Elasticsearch is two phases - **query** (every shard of the target index/indices produces its top candidates, from its segments, in parallel) then **fetch** (the coordinating node pulls full documents for the winners) - and most latency questions reduce to: *how many shards were touched, and how much did each shard scan?* The levers follow.

**Shard count per query** is the multiplier: a search across a 200-shard index waits for 200 parallel scans plus the merge; a search across 5 right-sized shards waits for 5. Data streams with rollover help both ways - bounded shard sizes *and* the ability for ILM-managed reads to target fewer, merged, warm indices. **Segment count** is the second multiplier: shards of many small segments scan slower than forcemerged ones, which is the performance case for the warm-phase `forcemerge: 1` ([Chapter 10](#ch10)). **What you ask for** is the third: filter-context-only queries ([Chapter 6](#ch6)) skip scoring; `"size": 0` aggregation requests ([Chapter 7](#ch7)) skip fetching; `fields` and `_source` filtering trim network and parsing; and keyword filters on well-mapped fields hit `doc_values` (columnar) rather than text.

Indexing speed has its own short list, and the settings are per-index and tunable live: `refresh_interval` (stretching the near-real-time refresh from 1s to 5-30s during heavy ingest trades visibility latency for substantial write throughput; bulk-load jobs set `-1` and restore it after), `translog.durability` (async for bulk loads that are re-runnable; sync - the default - for anything you would lose sleep over), and bulk sizing (5-15 MB per `_bulk` request, single client process saturating first, then add clients). The profile tools - `_search?profile=true` and the task API - turn speculation into line items when a query needs autopsying.

## 11.5 Monitoring Elasticsearch Itself

The cluster watches itself, and the operational layering is worth knowing in order of formality. **The `_cat` APIs** ([Chapter 2](#ch2)) are the manual floor - health, nodes, indices, shards, allocation, thread pools. **Stack Monitoring** - Kibana's monitoring UI - collects node, index, and (in current versions) log-level metrics into dedicated monitoring indices, viewable in-cluster with zero external tooling: enable `xpack.monitoring` collection or, in the modern recommendation, ship metrics with an Elastic Agent on the monitoring cluster. **External monitoring** - Prometheus scraping Elasticsearch's metrics endpoint (with the `prometheus_exporter` plugin or an Agent integration) and alerting on heap, disk, and cluster status alongside everything else - is the pattern this series prefers, and [Chapter 14](#ch14) shows Elasticsearch as a Grafana data source completing that loop.

The alert set that earns its keep before any dashboard polish: cluster status red or yellow-persistent; any node's heap above 75% sustained; disk above 80% anywhere; indexing or search thread-pool rejections nonzero; pending tasks nonzero (`GET _cluster/pending_tasks` - the master backlog). Every one of these is a leading indicator of an incident the cluster will otherwise announce by getting slow.

::: {.warn}
**Watch out - recovery speed is a capacity line item**

When a node rejoins after a restart or failure, the cluster must recover shard copies onto it, and until recovery completes, the cluster runs degraded - replicas unassigned, status yellow, redundancy reduced. Recovery is throttled (`indices.recovery.max_bytes_per_sec`, defaulting to a conservative 40 MB/s) precisely so it does not strangle live traffic; big clusters tune it up on fast networks. Plan restarts (rolling, node by node, with the `cluster.routing.allocation.enable` dance) rather than discovering the throttle during an outage, and keep shards in the 20-50 GB band so each one is minutes of recovery, not hours.
:::

**See also:** [Chapter 10](#ch10) automates the shard-size discipline this chapter quantifies, [Chapter 12](#ch12) locks down what you have scaled, and [Chapter 14](#ch14) runs the whole estate on Kubernetes.
