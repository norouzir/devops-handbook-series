# Chapter 2 - Elasticsearch Architecture: Clusters, Nodes, Shards, and Documents {#ch2}

## 2.1 The Cluster and the Nodes

Elasticsearch is a distributed system from the first process, not after scaling. One Elasticsearch process is a **node**; a group of nodes that holds the same data and cooperates is a **cluster**, identified by a name. There is no "standalone edition" that later becomes distributed - the single-node sandbox in [Chapter 3](#ch3) and the hundred-node production estate are the same software with the same APIs, which is why learning the vocabulary once is enough.

A node's **role** declares what work it does, and in modern versions roles are explicit in the configuration:

- **Master-eligible** nodes may be elected cluster master; the master maintains cluster state - which indices exist, which shards live where - and does not touch data. A production cluster has at least three master-eligible nodes so it survives one failure without losing the election quorum.
- **Data** nodes hold shards and execute indexing and search. Since 7.10 the data role is refined into **tiers** - `data_hot`, `data_content`, `data_warm`, `data_cold`, `data_frozen` - which [Chapter 10](#ch10) uses to build the hot-warm-cold lifecycle architecture.
- **Ingest** nodes run ingest pipelines - the per-node preprocessing that parses and enriches documents on their way in ([Chapter 4](#ch4)).
- A node with no role is a **coordinating** node: it receives client requests, fans them out to the shards that hold the data, and merges the answers. Every node coordinates by default; large estates add dedicated coordinating nodes to absorb client traffic.

Roles are set in `elasticsearch.yml` (`node.roles: [ master, data_hot, ingest ]`) and, on Kubernetes, by the operator ([Chapter 14](#ch14)). The single-node sandbox sets them all at once, which is exactly right for learning and exactly wrong for production.

## 2.2 Indices, Shards, and Replicas

An **index** is the unit of organization: a named collection of JSON documents with a shared configuration - the **mapping** that defines field types ([Chapter 5](#ch5)) and the settings that control shards and lifecycle. An index is not stored as one monolith; it is split into **shards**, each an independent, fully functional Lucene index living on some data node.

Two numbers define an index's distribution. **Primary shards** hold the data; their count is fixed at index creation (for a classic index) and decides how the write and query load spreads across nodes. **Replica shards** are copies of primaries; their count can change at any time. Replicas serve two masters at once: durability (a node loss does not lose data) and read throughput (search requests spread across primary and replica copies). The default of one primary and one replica per index is a sensible floor.

Routing closes the loop. A document belongs to the shard determined by a hash of its `_id`:

```text
shard = hash(_id) % number_of_primary_shards
```

Deterministic routing is why a GET by ID knows exactly which shard to ask, why shard count is fixed at creation for classic indices - changing it would relocate every document - and why data streams ([Chapter 10](#ch10)) sidestep the problem by rolling over to a fresh index instead of growing one forever.

::: {.warn}
**Watch out - shards are expensive, and the bill arrives later**

Every shard is a Lucene index with its own metadata, file handles, heap overhead, and cluster-state entry, and every search fans out to a copy of *every* shard in the target. A cluster of ten thousand small shards spends more memory deciding where data is than serving queries. The sizing rule this book repeats (and [Chapter 11](#ch11) develops): aim for shards in the tens-of-gigabytes range - roughly 20 to 50 GB - and prefer fewer, larger shards over many small ones. Data streams with rollover at `max_primary_shard_size: 50gb` make the rule automatic.
:::

Under the hood each shard is itself segmented: indexing writes documents into fresh, immutable **segments**, a **refresh** makes recent segments visible to search (the source of the *near* in near real time, roughly every second by default), a **flush** persists them, and background **merges** consolidate many small segments into larger ones. Immutable segments are why indexing is fast and why deleted documents leave tombstones that merges reclaim. You will meet the consequences throughout the book - the one-second visibility delay in [Chapter 3](#ch3), the `forcemerge` of warm data in [Chapter 10](#ch10), the refresh-vs-throughput trade in [Chapter 11](#ch11).

## 2.3 Documents: JSON, `_id`, and `_source`

The unit of data is the **document**: one JSON object, addressed inside the cluster as `index/_doc/_id`. If you do not supply an `_id`, Elasticsearch generates one; if you do, writing to the same `_id` replaces the document, which makes idempotent re-shipping of logs possible when you choose ids from content.

```json
PUT logs-app-error/_doc/app-2026-10-30-0007
{
  "@timestamp": "2026-10-30T09:14:07.231Z",
  "service": "checkout",
  "level": "error",
  "message": "payment gateway timeout after 3000ms",
  "trace_id": "4bf92f3577b34da6",
  "duration_ms": 3004
}
```

Every stored document keeps its original JSON in a field called **`_source`**. Search results return `_source` by default - it is why you get back what you put in without reconstructing it from indexed fields - and it is also what powers reindexing, updates, and highlight reconstruction. The response to the PUT above carries the document's address and a sequence number:

```json
{
  "_index": "logs-app-error",
  "_id": "app-2026-10-30-0007",
  "result": "created",
  "_shards": { "total": 2, "successful": 1, "failed": 0 }
}
```

The `_shards` block in every write response is the distributed system saying hello: the write went to one primary and its replica copy succeeded or failed individually. Operations engineers learn to read these small fields early - they are the cluster explaining itself.

## 2.4 The REST API Conventions

Everything in Elasticsearch is HTTP and JSON, and the API follows a small set of conventions worth internalizing before any chapter of tooling. Verbs map to intent: `PUT` creates or replaces (indices, documents, policies), `POST` runs operations and partial updates (`_search`, `_bulk`, `_update`), `GET` reads, `DELETE` removes. Endpoints prefixed with an underscore are *API operations* rather than data paths: `_search`, `_bulk`, `_cluster/health`, `_cat/*`, `_ilm/policy`, `_snapshot`. The response always includes `acknowledged` or the operation's result, and errors come back as JSON with a `type` and a `reason` that actually say what happened - Elastic's error messages are among the better ones in infrastructure software, and reading them before searching the web is a habit worth forming.

The Kibana **Dev Tools** console (introduced in [Chapter 3](#ch3)) speaks this dialect directly: you write `GET _cat/nodes?v` and it fills in the host, port, and headers. The `curl` equivalent throughout the book is:

```bash
curl -s "http://localhost:9200/_cat/nodes?v"
```

JSON in request bodies must be valid JSON - no trailing commas, no comments - which is the one friction point of the Query DSL that ES|QL ([Chapter 8](#ch8)) was designed to remove.

## 2.5 Reading a Cluster: Health and the `_cat` APIs

An Elasticsearch cluster constantly reports its own state, and two families of endpoints cover most day-to-day reading. **`_cluster/health`** returns the headline: status `green` (all primaries and replicas allocated), `yellow` (primaries fine, some replicas unassigned - the classic single-node symptom, since a lone node cannot host a replica copy), or `red` (some primaries missing - data is unreachable). Yellow on a sandbox is expected; red anywhere is an incident.

The **`_cat` APIs** are the operator's Swiss army knife - flat, `?v`-decorated tables of everything that matters:

```text
GET _cat/health?v          # status, nodes, shards, pending tasks
GET _cat/nodes?v           # heap, disk, CPU, roles per node
GET _cat/indices?v         # every index: docs, size, health
GET _cat/shards?v          # every shard and its placement
GET _cat/allocation?v      # disk usage per node, shard counts
GET _cat/indices/logs-*?v&bytes=mb&sort=store.size:desc
```

Three habits make these APIs operational rather than decorative. First, `?v` adds headers and `?help` lists every column - learn one API and you have learned them all. Second, sorting and filtering are query parameters, so "the ten biggest indices" is a one-liner you will run weekly. Third, these are the same numbers Kibana's Stack Monitoring and the alerting rules in [Chapter 14](#ch14) watch; reading them by hand first teaches you what the automation is looking for.

::: {.note}
**Best practice - make `_cat/health` part of every runbook**

Every diagnostic session on an Elasticsearch cluster should begin with `GET _cluster/health` and `GET _cat/nodes?v`. Status, node count, shard counts, heap, and disk in two calls - and most incidents in the field resolve or get a name before the third call.
:::

## 2.6 Where the Metadata Lives

Two pieces of cluster bookkeeping deserve early awareness because they are invisible until they hurt. The **cluster state** - the master's map of every index, shard, template, and mapping - is held in memory and broadcast to every master-eligible node; it is why ten thousand tiny indices slow the master down, and why [Chapter 10](#ch10) deletes indices instead of just closing them. The system indices (`.security-*` for users and roles, `.kibana*` for Kibana's own objects) are ordinary indices with special custody rules: they are backed up by snapshots like any other data ([Chapter 13](#ch13)), and they are the reason a cluster restore also restores your access model. Neither needs action today; both explain design decisions in every later chapter.

**See also:** [Chapter 3](#ch3) puts a cluster on your laptop, [Chapter 5](#ch5) explains how its documents become searchable terms, and [Chapter 10](#ch10) shows how indices live and die in production.
