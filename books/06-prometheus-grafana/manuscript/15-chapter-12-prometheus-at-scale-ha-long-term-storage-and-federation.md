# Chapter 12 - Prometheus at Scale: HA, Long-Term Storage, and Federation {#ch12}

## 12.1 High Availability: Two Servers and the Dedup Contract

Prometheus's high-availability story is refreshingly literal: run **two identical servers**, scraping the same targets with the same configuration, and send alerts from both to a clustered Alertmanager ([Chapter 8](#ch8)) which deduplicates. There is no consensus protocol, no leader election, no shared storage - a server that dies takes nothing with it that its twin does not have, and the failure mode of the pair disagreeing is *two notifications*, not zero. Both servers get distinct `external_labels` (`replica: A` / `replica: B`) so their series can be told apart downstream, and the pattern extends vertically: three or five replicas for teams whose monitoring must survive maintenance windows and upgrades simultaneously.

Query-side HA is the second half of the contract. A Grafana data source pointing at one replica fails over manually; the standard answers are a load balancer with Prometheus-aware health checks, or - the estate-scale pattern - a query layer that federates across replicas and **deduplicates** (Thanos Query, Mimir Query Frontend, or Grafana Mimir's own query path). The dedup contract matters at the query layer because the two replicas' series differ only by the `replica` external label: deduplication selects one sample per (series, timestamp) pair, tolerating the small scrape-time skew between replicas.

::: {.note}
**Best practice - HA means two of everything, configured once**

The pair must be *identical*: same config file, same rule files, deployed from the same source ([Ansible](https://www.ansible.com/) or your provisioner of choice). Hand-edited divergence between replicas produces alerts that fire on one replica and not the other - a debugging session nobody enjoys. If config drift is possible, it will eventually be real.
:::

## 12.2 Remote Write: Shipping Samples Out

**Remote write** is Prometheus's outbound stream: as samples are committed, they are queued and shipped to a compatible endpoint - Grafana Mimir, Thanos Receive, Cortex, Amazon Managed Service for Prometheus, Grafana Cloud, VictoriaMetrics - with per-metric relabeling to decide what goes:

```yaml
remote_write:
  - url: https://mimir.example.com/api/v1/push
    queue_config:
      max_samples_per_send: 2000
      capacity: 5000
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "go_.*"
        action: drop
```

Remote Write 2.0 (standard since Prometheus 3.0) carries metadata, exemplars, created timestamps, and native histograms with materially better compression than 1.0; the two protocol versions interoperate via negotiation, and both keep the same operational shape - a bounded queue with configurable backpressure (`capacity`, `max_shards`), and metrics (`prometheus_remote_storage_*`) that tell you when the remote is behind. Remote write is *additive*: the local TSDB keeps doing its job, and the remote becomes the long-term store. The relabeling at the boundary is the cardinality contract with your wallet - in a managed or shared backend, `write_relabel_configs` is where [Chapter 2](#ch2)'s cardinality discipline gets enforced with a budget line attached.

## 12.3 Long-Term Storage: Thanos and Mimir

When "15 days on local disk" stops being enough - year-over-year capacity trends, compliance, cross-cluster queries - the ecosystem offers two mature open-source architectures, both storing the same TSDB blocks that [Chapter 2](#ch2) described in object storage, and both querying them with the same PromQL.

**Thanos** wraps existing Prometheus servers: a **Sidecar** runs next to each server, uploads TSDB blocks to object storage (S3, GCS, Azure) and serves the local data; **Store Gateway** serves downloaded historical blocks; **Compactor** merges blocks and applies retention and downsampling (5m/1h resolutions); **Query** federates live Prometheis and Store Gateways behind one deduplicating PromQL endpoint; **Ruler** evaluates rules globally. The appeal is incremental adoption - existing servers keep their identity, and each component scales independently - at the cost of operating several stateless-ish components plus a compactor.

**Grafana Mimir** (3.2.x as of October 2026) is the scale-out database: Prometheus servers remote-write into Mimir, which shards ingestion and queries across a horizontally scalable cluster, stores everything in object storage, and serves multi-tenant PromQL with a query frontend. The appeal is architectural simplicity at fleet scale - one system to operate, native HA and dedup, multi-tenancy by tenant ID - at the cost of committing to remote-write topology rather than wrapping servers. (Mimir is AGPLv3; Grafana Enterprise Metrics is the commercial distribution.)

| Dimension | Thanos | Mimir |
|---|---|---|
| Ingestion model | Sidecar wraps existing servers | Remote write into the cluster |
| Best fit | Many independent Prometheus servers, gradual adoption | Centralized fleet, multi-team, single global view |
| Query layer | Thanos Query (dedup across replicas) | Mimir query frontend (built in) |
| Components to run | Sidecar, Store GW, Compactor, Query, Ruler | One distributed system (monolithic mode to start) |
| Multi-tenancy | Per-Prometheus | Native, per-tenant |
| Global rules | Thanos Ruler | Built-in ruler |

The decision procedure is shorter than the table: if you already run many Prometheis and want a global query layer without changing them, Thanos; if you want one metrics database for the whole estate and are willing to centralize ingestion, Mimir. Both read the same dashboards, and neither changes anything in Parts I of this book - PromQL is PromQL.

## 12.4 Federation and Sharding

Two older patterns remain in the toolkit for specific jobs. **Hierarchical federation**: a top-level Prometheus scrapes `/federate` from lower-level servers, pulling selected aggregated series (`honor_labels: true` preserves the child's labels):

```yaml
scrape_configs:
  - job_name: federate
    scrape_interval: 30s
    honor_labels: true
    metrics_path: /federate
    params:
      'match[]':
        - '{__name__=~"job:.*"}'          # pull all recorded series
    static_configs:
      - targets: ["site-a.prometheus:9090", "site-b.prometheus:9090"]
```

The `job:.*` selector is not an aesthetic choice - federating *recording rules only* (the `level:metric:operations` series from [Chapter 6](#ch6)) is what keeps the top-level server cheap; federating raw series recreates the entire estate in one process. **Sharding** by `hashmod` ([Chapter 7](#ch7)) splits a too-big scrape universe across N servers, each owning a shard, with a query layer (Thanos Query) reassembling the whole. The general guidance for new estates: federation for modest hierarchical rollups, sharding plus a global query layer for scale, and Mimir/Thanos as the durable answer - reserving raw federation for the glue cases the big architectures do not cover.

## 12.5 Sizing, Tuning, and Monitoring the Monitor

Prometheus capacity is a function of three numbers - **active series**, **samples per second** (series × scrape rate), and **retention** - and the working reference points: a well-tuned server handles low millions of active series; memory is dominated by the head block (active series × churn rate); disk is approximately `samples/sec × retention × ~2 bytes` after compression. The knobs, in order of likelihood: `--storage.tsdb.retention.time` matched to disk; `scrape_interval` questioned before heroic tuning ([Chapter 3](#ch3)); `--storage.tsdb.head-chunks-write-queue-size` and friends only under measured pressure. Churn - series created and destroyed rapidly (cron-pod label sets, retry labels) - is the silent killer: a fleet with modest steady-state series can still OOM on churn, and the TSDB page's *series created per second* graph is the early-warning instrument.

And then monitor the monitor, because a silent Prometheus is the failure nobody pages on. The standard kit: `up{job="prometheus"}` and `prometheus_tsdb_head_series` for the servers themselves; a **deadman switch** - an always-firing watchdog alert (`expr: vector(1)`) routed through Alertmanager to a "watchdog" receiver, integrated with your alerting provider's healthcheck so a *silent* pipeline pages (the inverse alarm); and the recording-rule staleness alerts from [Chapter 6](#ch6). [Lab 5](#lab5) wires the deadman pattern into the kube-prometheus-stack deployment, where it ships by default.

::: {.warn}
**Watch out - the scale-up that hides the design problem**

Before sizing hardware, re-read the cardinality chapter: a Prometheus struggling under 2M series of which 1.5M are `http_requests_total{path=...}` does not need a bigger server - it needs the label rewritten ([Chapter 4](#ch4)). Scale-up is the correct answer to genuine load and the expensive answer to instrumentation debt; know which one you are buying.
:::

## 12.6 Reference Topology for a Growing Estate

A reference shape for the estate this book has been building: per-cluster Prometheus pairs (HA, [Section 12.1](#ch12)), per-cluster Alertmanager clusters, Thanos sidecars uploading blocks to object storage with a global Thanos Query for cross-cluster dashboards; Grafana reading Thanos Query as one data source plus each cluster's local Prometheus as drill-down data sources ([Chapter 9](#ch9)); infrastructure alerts evaluated locally per cluster ([Chapter 8](#ch8)), product and multi-source alerts in Grafana ([Chapter 11](#ch11)); federated or Mimir-aggregated rollups for executive dashboards. Every piece of that topology was a chapter decision, and the estate it forms has a property worth naming: *no single component's failure blinds the whole*, which is the entire point of running monitoring as infrastructure rather than as an appliance.

**See also:** [Chapter 13](#ch13) for the Kubernetes-native packaging of this topology, [Chapter 6](#ch6) for the recording rules federation and dashboards consume, and [Chapter 2](#ch2) for the block storage model Thanos and Mimir build on.
