# Chapter 10 - Data Streams and Index Lifecycle Management {#ch10}

## 10.1 The Problem: Time-Based Data Grows Forever

Logs, metrics, and traces are append-only and time-stamped, which makes them both predictable and unbounded: last month's access log is queried a hundred times less than this morning's, and never deleted only until someone asks why the cluster costs what it costs. The classic answer is time-based indices - `logs-2026.10.30` per day, deleted when old - and it works, but hand-rolled it multiplies operational chores: who creates tomorrow's index, when does one grow too big, where does the alias point, what deletes last month?

**Data streams** plus **Index Lifecycle Management (ILM)** are the platform's mechanized answer, and in current versions they are the default for every Elastic Agent integration, every Beat output configured normally, and every well-run log estate. The pair solves the two halves of the problem separately: data streams handle *where writes go* (always a fresh, correctly-shaped index), ILM handles *what happens to indices over time* (roll over, optimize, move to cheaper hardware, delete). Neither is optional in a serious deployment; together they are the reason [Chapter 11](#ch11)'s shard-count rules stay true without human attention.

## 10.2 Data Streams: Writes That Roll Over

A **data stream** is a named logical index - `logs-nginx-default` - that fronts an ordered list of concrete backing indices (` .ds-logs-nginx-default-2026.10.30-000001`). All writes go to the newest backing index (**write index**); reads fan out across all of them, so searchers never know a rollover happened. **Rollover** retires the write index when a threshold is met and atomically creates the next - the mechanism that replaces both daily index churn and forever-growing single indices.

The stream is created by an index template with `data_stream: {}` - the pattern you met in [Chapter 5](#ch5):

```text
PUT _index_template/nginx-logs
{
  "index_patterns": ["logs-nginx-*"],
  "data_stream": {},
  "priority": 200,
  "composed_of": ["logs-mappings"],
  "template": {
    "settings": {
      "index.number_of_shards": 1,
      "index.number_of_replicas": 1,
      "index.refresh_interval": "5s"
    }
  }
}
```

The first write to a name matching the pattern creates the stream, its first backing index, and wires ILM if the template carries a policy. Two configuration keys carry the design weight. `index.number_of_shards: 1` - because the rollover *size* threshold, not the shard count, is what scales: one big-enough shard per backing index is the modern default for log streams, and the stream's shard count grows by adding indices, not by re-sharding. And the rollover threshold itself lives in the ILM policy, where `max_primary_shard_size: 50gb` has displaced calendar-day rollover as the default advice: rollover happens when a shard fills, not when a clock ticks, which keeps shard sizes uniform whether traffic is Tuesday-morning or Christmas-Eve quiet.

::: {.warn}
**Watch out - the stream is not an index, and some APIs still think it is**

Data streams accept only append writes: no updates, no deletes of individual documents by default (delete-by-query and the `@timestamp`-anchored exceptions aside). Direct writes to backing indices, aliased two ways onto one stream, or a classic index created where a stream template matches - these are the confusion classics, and the error messages are honest about them. When in doubt: `GET _data_stream/logs-nginx-default` shows the truth (backing indices, their ages, sizes, and the policy attached).
:::

## 10.3 ILM: The Five Phases

An **ILM policy** is a timeline of named phases; indices progress through them based on their age (`min_age`) and the thresholds each phase defines. Five phases exist, and the first four are a temperature scale:

**Hot** - the write index lives here: active indexing and frequent queries on fast hardware. The defining action is `rollover` (size or age threshold). **Warm** - indexing stops; indices become read-only, `forcemerge` into few large segments (typically 1), and replicas may drop; queries still served, hardware can be slower. **Cold** - rare queries; data can move to cheaper nodes via shard allocation (tier preference `data_cold`) and, with the paid tier, become **searchable snapshots** held on object storage with local caches. **Frozen** - the paid-tier endgame: fully object-storage-hosted, with only a small cache on disk - retention measured in years at storage costs near raw S3. **Delete** - the phase that pays for everything: documents leave the cluster on schedule.

```text
PUT _ilm/policy/logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": { "max_primary_shard_size": "50gb", "max_age": "7d" }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "forcemerge": { "max_num_segments": 1 },
          "allocate": { "number_of_replicas": 0 }
        }
      },
      "delete": {
        "min_age": "30d",
        "actions": { "delete": {} }
      }
    }
  }
}
```

This three-phase policy - rollover at 50 GB or 7 days, merge and thin out after a week, delete after a month - is the workhorse default this book's stack ships with, and the template wires it with one setting (`index.lifecycle.name: logs-policy`). `min_age` counts from rollover, not from index creation, once a rollover action exists - a subtlety that saves an hour of confusion the first time a policy seems to fire "early."

## 10.4 Hot-Warm-Cold Architecture

Phases only buy money back if they map onto different hardware, and that mapping is the **hot-warm-cold** topology: nodes carry tier roles (`data_hot`, `data_warm`, `data_cold`, `data_frozen`), and ILM's `allocate` action pins indices to tiers via `tier_preference`. The economics are the whole point. Hot nodes are the expensive ones - NVMe disks, big RAM, fast CPUs - sized for ingest rate and interactive query load, holding perhaps a week of data. Warm nodes are slower and denser - spinning disks or bulk SATA, high storage per euro - holding the long tail of occasionally-queried data. Cold and frozen extend the scale-out to object storage, where the cluster's cost curve finally flattens to near-cloud-storage prices.

Sizing the boundary is an economics exercise, not a technical one: measure daily ingest volume, decide what fraction of queries touch data older than N days (Kibana's search analytics and your own access patterns answer this), and place the boundary where the query-frequency curve bends. The universal pattern in practice: everything you can afford hot stays hot; the delete boundary is set by policy or regulation; warm exists in between to make retention affordable. A cluster with uniform hardware can still use ILM (all phases on the same nodes - rollover, merge, delete are valuable regardless); tiering is where lifecycle turns into cost engineering.

## 10.5 Retention Economics and Downsampling

The delete phase makes retention a budget line, and three levers control it. **Retention windows** per data stream - debug logs for 7 days, application logs for 30, audit logs for 365 - are separate policies attached per stream by name; one estate, several policies, each cheap in the phases it uses. **Compression and codec** settings trade a few percent CPU for meaningful disk savings (`index.codec: best_compression` at the warm phase is a standard move). **Downsampling** - for the metrics side of the estate - rewrites time-bucketed data into coarser intervals (10-second raw series become 1-minute averages after 30 days, 1-hour after a year), cutting storage by orders of magnitude while preserving the resolution dashboards actually show; time series data streams (TSDS) carry the mechanism.

::: {.note}
**Best practice - write the retention table down before the cluster exists**

Retention decisions are organizational, not technical - who needs which data, for how long, under which regulation - and they are cheapest to make as a one-page table attached to the cluster's ILM policies, not reverse-engineered from a full disk six months in. The table has three columns (stream, retention, phase boundaries) and prevents both the disk-full incident and the accidental audit-trail deletion.
:::

## 10.6 Operating Lifecycle in Practice

ILM is observable, and the observability belongs in your runbook next to health checks. `GET _data_stream/*` lists every stream with its backing indices, ages, and sizes - the weekly glance that catches a stream whose rollover stopped (usually a full disk or a stuck write index). `GET logs-nginx-default/_ilm/explain` shows exactly where each backing index sits in its policy and *why* - which phase, which step, any errors; this one endpoint resolves most "why is my data still hot?" mysteries. And `GET _ilm/status` plus the per-index explain together separate "ILM is broken" from "ILM is waiting" - the distinction between an incident and a plan.

Two failure modes account for most real ILM pain. A stream whose rollover never fires because a threshold is unreachable - `max_age: 7d` with a stream that receives no writes, or `max_primary_shard_size` on an index that never reaches it while age keeps the hot tier fat. And policies attached to streams through templates that later changed - existing indices keep the old policy until migrated (`_ilm/migrate_to_data_streams` and reindexing cover the historical cases). Both are visible in `explain` output before they are visible in a graph.

**See also:** [Chapter 11](#ch11) sizes the cluster these policies manage, [Chapter 13](#ch13) backs up what ILM will eventually delete, and [Chapter 5](#ch5) defined the templates that wire policies to streams.
