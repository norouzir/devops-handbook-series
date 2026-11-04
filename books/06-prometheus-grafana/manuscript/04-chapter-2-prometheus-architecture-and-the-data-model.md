# Chapter 2 - Prometheus Architecture and the Data Model {#ch2}

## 2.1 The Components of a Prometheus Deployment

A production Prometheus deployment is a small constellation of processes, each doing one job, and learning their names is learning the system. The **Prometheus server** scrapes targets over HTTP, stores the samples in its embedded TSDB, evaluates recording and alerting rules against the stored data, and serves queries. **Exporters** are small daemons that translate the internals of something that does not speak Prometheus - a Linux kernel, a PostgreSQL instance, a message broker - into the exposition format. The **Alertmanager** receives alerts from any number of Prometheus servers and handles the social half of alerting: deduplication, grouping, silencing, routing to the right humans. The **Pushgateway** is a scrape-target cache for batch-job metrics, and **promtool** is the command-line companion that validates configuration and inspects TSDB files.

Two further pieces matter before you meet them in anger. **Client libraries** embed exposition and instrumentation directly in application code, so the application *is* the exporter. And in Kubernetes estates the **Prometheus Operator** (Chapter 13) wraps the server in custom resources so that scrape configuration is expressed as Kubernetes objects rather than hand-edited YAML.

The deployment philosophy is deliberately modular: one Prometheus server per failure domain or team, one Alertmanager per cluster of servers, exporters wherever the thing being measured lives. There is no single "monitoring cluster" that must exist before the first metric flows - a laptop running the server binary is a complete Prometheus deployment.

## 2.2 The Dimensional Data Model

Everything Prometheus stores and every query PromQL evaluates is built on one structure: a **time series** identified by a **metric name** plus a set of **label** key-value pairs, holding an ordered list of float64 samples with millisecond-precision timestamps.

```
http_requests_total{job="api", method="POST", status="200"}   # a series
http_requests_total{job="api", method="GET",  status="500"}   # a different series
```

The metric name is itself stored as a label, `__name__`, so formally a series is a set of labels. The unique set of label values - the series *identity* - is what makes Prometheus dimensional: one metric name, many series, and queries that slice by any label. This contrasts with both the old world (one time series per metric name, labels hacked into the name) and with tracing-style event stores: Prometheus sits deliberately in the middle, structured enough to aggregate cheaply, flat enough to store on one machine.

**Cardinality** is the model's governing constraint. Every distinct combination of label values is a distinct series that must be stored, queried, and aged out independently, so a label whose values scale with users, request IDs, or trace IDs does not add columns - it adds *millions of series*. The number of active series in memory (visible in the TSDB status page, introduced properly in [Chapter 3](#ch3)) is the single number that best predicts a Prometheus server's memory footprint and query latency. Chapters 4 and 7 both return to cardinality control from different directions: instrumentation that does not create series it cannot afford, and relabeling that drops or rewrites series before they are stored.

::: {.warn}
**Watch out - the most expensive mistake in Prometheus**

A label like `user_id`, `request_id`, or `pod_name` on a high-volume metric does not just use memory linearly - every series also carries index structures and query overhead. The classic incident is a metrics endpoint that grows without bound, a scrape that grows with it, and an OOM-killed Prometheus server hours later. If a value does not need its own graph line, it belongs in a log line, not a label.
:::

## 2.3 Metric Types: Counter, Gauge, Histogram, Summary

The exposition format carries type metadata, and the four standard types map onto the four questions you actually ask of a system.

A **counter** is a monotonically increasing value: requests served, bytes written, errors handled. Counters reset to zero on process restart, which is why you never graph one directly and always query it through `rate()` or `increase()`, which detect and absorb resets (Chapter 5). The convention is a `_total` suffix.

A **gauge** is a value that can go up and down: temperature, queue depth, in-flight requests, memory used. Gauges are the only type you graph raw; they answer "what is the current state?"

A **histogram** samples observations into configurable buckets on the server side of the query - `http_request_duration_seconds_bucket{le="0.1"}` and friends, plus `_sum` and `_count` series. Histograms let you compute approximate quantiles (p50, p95, p99) with `histogram_quantile()` (Chapter 6), aggregate across instances before quantile computation, and add buckets later without changing instrumentation - at the cost of one series per configured bucket.

A **summary** is the pre-quantile alternative: the client computes quantiles itself and exposes them directly. Summaries cannot be aggregated across instances and their quantiles are fixed at instrumentation time, which relegates them to single-instance use; in most estates, histograms are the right default choice for durations.

::: {.note}
**Best practice - units in names, not in values**

Name metrics for their unit - `http_request_duration_seconds`, `node_memory_MemAvailable_bytes` - and store base SI units (seconds, bytes) unadorned. The Grafana panels in Chapter 9 can then format freely, and two metrics from different sources are always comparable without mental arithmetic.
:::

## 2.4 Inside the TSDB

Prometheus's time-series database is worth a mental model, because several operational knobs (retention, memory, query performance) only make sense against it. Samples arrive in memory into an **active head block** holding the most recent hours of data, protected by a write-ahead log so a crash loses seconds, not hours. Every two hours the head is **compacted** into an immutable, chunked **block** on disk with an index; background compaction then merges small blocks into larger ones - two-hour blocks into six, twelve, twenty-four - until the configured retention window is reached, after which old blocks are deleted. Every block is content-addressed and self-describing, a fact that Chapter 12 exploits: Thanos and Mimir store *these exact blocks* in object storage, which is why long-term storage in the Prometheus world is an addition, not a replacement.

Query execution reads recent data from the head and older data from blocks, which is why queries spanning many days are inherently slower than single-hour lookups, and why recording rules (Chapter 6) exist: precompute the expensive aggregation, store it as a new series, and let dashboards read the cheap result.

Two flags govern storage size directly: `--storage.tsdb.retention.time` (default 15 days) and, less commonly, `--storage.tsdb.retention.size`. Retention interacts with scrape interval and cardinality in the obvious way - double either and you double storage - so the capacity planning conversation always involves all three numbers.

## 2.5 What Prometheus Deliberately Does Not Do

Prometheus's reliability comes from refusing jobs, and knowing the refusals prevents years of architectural regret.

It is **not a long-term store** by default: local disk and a 15-day default retention are design intent, not an oversight; scale-out retention is an explicit architecture (Chapter 12). It is **not clustered**: one server is one failure domain, and the high-availability story is two independent servers scraping the same targets (Chapter 12), not a consensus protocol. It does **not provide 100 percent accuracy**: the pull model samples state at intervals, so values between scrapes and events shorter than the interval are invisible - build with the interval in mind rather than pretending it away. It does **not store individual events**: a metric is an aggregation over samples, and the request that errored at 03:14:07 is found in logs and traces, not in Prometheus. And it does **not do single-sign-on dashboards, notification escalation policies, or ticketing** - that is the Alertmanager's job for delivery, Grafana's for human interfaces, and your incident tooling's job for process.

::: {.note}
**Best practice - choose boring failure modes**

Every "Prometheus is down" conversation should start with "the two replicas see the same world, alerts flow to two Alertmanagers, dashboards read a load-balanced query endpoint." None of those pieces require Prometheus to be a distributed system, and all of them are configured, not invented.
:::

## 2.6 Prometheus 3: What Changed and What It Means for You

Three Prometheus 3 capabilities change day-to-day practice, and all three reappear later in the book.

**The new web UI** replaces the AngularJS interface of the 2.x era with a faster, modern single-page application, including a PromQL tree view for exploring queries interactively. **Remote Write 2.0** adds metadata, created timestamps, exemplars, and native histogram support to the wire protocol with significantly better compression - relevant the moment you ship metrics to Mimir, Thanos Receive, or a managed service (Chapter 12). **UTF-8 metric and label names** are now standard, with legacy escaping applied automatically when a client or remote endpoint does not support them; practically, you will still see snake_case names everywhere, because every major client library and exporter continues to emit them, and the Prometheus naming guidelines remain the shared language. **OTLP ingestion** deserves a sentence of its own: with the receiver enabled (`--web.enable-otlp-receiver`), an OpenTelemetry SDK can POST metrics directly to `/api/v1/otlp/v1/metrics`, and translation strategies map OTel resource attributes onto Prometheus labels - the detail is Chapter 4's closing section.

The 3.x upgrade also removed some 2.x conveniences (for example, targets no longer get a default port inferred from their scheme) and the migration guide is short enough to read in full before any upgrade from 2.x. For a new build, none of this is visible friction: everything you install in [Chapter 3](#ch3) is 3.x-native.

**See also:** [Chapter 3](#ch3) turns this architecture into a running stack, and [Chapter 5](#ch5) begins querying the data model you just learned.
