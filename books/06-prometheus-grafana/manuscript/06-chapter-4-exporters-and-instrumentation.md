# Chapter 4 - Exporters and Instrumentation {#ch4}

## 4.1 The Exporter Ecosystem and the Exposition Contract

An **exporter** is a daemon that speaks Prometheus on behalf of something that does not: it queries or observes the real system and exposes the result as labeled metrics at `/metrics`. The ecosystem is enormous - the official exporters cover Linux, Windows, Kubernetes, databases, and brokers, and the community list runs to hundreds - but the design is uniform, which is what makes it navigable. Every exporter is just an HTTP service; every one is scraped by the same `scrape_configs` stanza; every one can be debugged with `curl` before Prometheus is involved.

The official exporters follow the [exporter guidelines](https://prometheus.io/docs/instrumenting/writing_exporters/), and the guidelines are worth reading as an API spec for telemetry: metric names carry their unit (`_seconds`, `_bytes`), counters end in `_total`, every metric has a `HELP` string, names describe *what* is measured rather than *which system* measures it (the `job` label already says that), and state that can be derived should be derived - the exporter exposes facts, not opinions. Two operational corollaries follow. First, run one exporter per machine or service and let Prometheus scrape it, rather than aggregating by hand. Second, prefer a maintained exporter over a bespoke script: the community has already handled the edge cases (blocked syscalls, missing permissions, counter wrapping) that bespoke scripts discover in production.

::: {.note}
**Best practice - the curl-first debugging rule**

When a dashboard is empty, resist the urge to debug Prometheus first. `curl -s http://target:9100/metrics | head` answers three questions in one step: does the endpoint exist, does it return the metric in question, and does the metric carry the labels you expect? More exporter "bugs" are label mismatches visible in the first ten lines of curl output than anything else.
:::

## 4.2 node_exporter: The Host Metric Workhorse

node_exporter exposes Linux host metrics - CPU, memory, disk, filesystem, network - and it is the most widely deployed exporter in the world. Its design point is **collectors**: small subsystems, each enabled or disabled, each contributing a metric family. You rarely need all of them, and on constrained hosts the difference matters: `--collector.disable-defaults --collector.enable=cpu,memory,diskstats,filesystem,netdev,loadavg` is a lean production profile.

Two collectors earn special mention. The **systemd collector** exposes unit states (`node_systemd_unit_state{name="nginx.service",state="active"}`), which turns "is the service running" into a queryable fact. The **textfile collector** reads metrics from files in a directory on a schedule, which is the sanctioned escape hatch for one-off machine facts a script knows and no exporter does - cron jobs write to `/var/lib/node_exporter/textfile/backup_status.prom` and the host reports backup success like any other metric:

```
# HELP backup_last_success_timestamp_seconds Unix time of last successful backup
# TYPE backup_last_success_timestamp_seconds gauge
backup_last_success_timestamp_seconds 1761580800
```

The queries you will use constantly, all introduced properly in [Chapter 5](#ch5): `rate(node_cpu_seconds_total{mode!="idle"}[5m])` for CPU busy-ness, `1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes` for memory pressure, `rate(node_network_receive_bytes_total{device!~"lo"}[5m])` for network throughput.

## 4.3 cAdvisor, Docker Engine, and blackbox_exporter

In container estates, two more sources join node_exporter. **cAdvisor** (built into the kubelet, runnable standalone) exposes per-container CPU, memory, network, and filesystem metrics, labeled by container name and image - the layer node_exporter cannot see into. The **Docker Engine** itself exposes engine-level metrics (`docker_stats` totals, builder activity) on a TCP socket configured in `daemon.json`; both are useful, and in Kubernetes the kubelet's built-in cAdvisor plus kube-state-metrics ([Chapter 13](#ch13)) cover the space.

The **blackbox_exporter** inverts the model: instead of asking a system how it feels, you ask the network how the system looks from outside. It exposes *probe results* - HTTP status and latency, TCP connect time, ICMP round trip - for targets Prometheus passes in as URL parameters:

```yaml
scrape_configs:
  - job_name: blackbox-http
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
          - https://example.com/healthz
          - https://api.example.com/v1/ping
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
```

The relabeling incantation (mechanics in [Chapter 7](#ch7)) rewrites each configured target URL into a parameter of the probe request, and preserves the real URL as the `instance` label. The payoff metrics: `probe_success`, `probe_duration_seconds`, and `probe_http_status_code` - the synthetic-monitoring backbone of "the site is up *from here*". Blackbox probing is how you alert on the failure mode the target itself cannot report: a DNS outage, a bad certificate, a load balancer black hole.

## 4.4 The Pushgateway and Batch Jobs

Pull fails for exactly one workload class: short-lived jobs that finish before any scrape lands - cron backups, batch ETL, one-off migrations. The **Pushgateway** is the sanctioned bridge: the job pushes its metrics on completion, and Prometheus scrapes the gateway as it would any target.

```bash
echo "backup_result 1" | curl --data-binary @- http://pushgateway:9091/metrics/job/backup/instance/db-01
```

The job and instance become labels, the metric becomes scrapable, and `time() - push_time_seconds{job="backup"}` answers "how stale is the last push?" - the alert that matters most on this path.

The gateway's cardinality trap is equally important to state plainly: pushed metrics persist until explicitly deleted, so a gateway accumulates series from every historical run instance unless the job deletes its own group on completion. Use the Pushgateway for *service-level* batch outcomes, never as a general push channel for application metrics - applications that live long enough to be scraped should expose, not push (that includes instrumented code, next section).

## 4.5 Instrumenting Your Own Code

Client libraries exist for every mainstream language, and the four metric types from [Chapter 2](#ch2) map directly onto the API. The discipline of good instrumentation fits in four rules, shown here in Python but identical in shape everywhere:

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

REQUESTS = Counter(
    "http_requests_total", "HTTP requests processed.",
    ["method", "endpoint", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds", "Request duration.",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
IN_FLIGHT = Gauge("http_requests_in_flight", "Requests currently being served.")

@app.before_request
def before():
    IN_FLIGHT.inc()

@app.after_request
def after(response):
    REQUESTS.labels(request.method, request.path, response.status_code).inc()
    return response

start_http_server(9101)   # /metrics on port 9101, scraped like any exporter
```

**Rule one: label values must come from a bounded set.** `method`, `endpoint`, and `status` are enumerable; a raw URL path or user ID is unbounded cardinality ([Chapter 2](#ch2)) and a future outage. **Rule two: count what users experience** - one counter labeled by outcome beats five clever internal metrics. **Rule three: durations are histograms**, with buckets chosen around your SLO target, because a p95 you cannot compute is decoration. **Rule four: the exposition endpoint is a public API** - bind it deliberately, and never expose it to the internet unauthenticated.

::: {.warn}
**Watch out - the label that seemed useful**

Adding `path` as a label value feels like observability and is usually a time bomb: `/users/4271` and `/users/4272` are different series. Normalize first (`/users/:id`) or count at the route level. The TSDB status page from [Chapter 3](#ch3) will show you the explosion if you skip this.
:::

## 4.6 OpenTelemetry and Prometheus 3: Two Roads, One Destination

Instrumentation in 2026 has two supported roads, and Prometheus 3 makes them converge. The native road - Prometheus client libraries - remains the shortest path when the destination is Prometheus: one dependency, one endpoint, no moving parts. The OpenTelemetry road - OTel SDKs and the OTel Collector - is the right choice when the same instrumentation must also feed traces and logs, when the application fleet spans multiple backends, or when a collection agent must sit between applications and storage anyway.

With the OTLP receiver enabled, Prometheus accepts OpenTelemetry metrics directly:

```yaml
# prometheus.yml — nothing to add here; the flag does it:
# --web.enable-otlp-receiver
```

```bash
# from an OTel SDK or Collector, metrics land at:
# POST http://prometheus:9090/api/v1/otlp/v1/metrics
```

Resource attributes map to labels under configurable translation strategies, and the receiver applies the same cardinality discipline as a scrape. The practical guidance for a new system: instrument with OpenTelemetry if traces are on the roadmap (they usually are), expose Prometheus-native metrics from infrastructure, and let Prometheus 3 ingest both. The metrics end up in the same TSDB, queryable by the same PromQL you will build in [Chapter 5](#ch5).

## 4.7 Lab 2: Instrument and Probe

::: {.lab}
### Lab 2 - A custom application and synthetic probes {#lab2}

1. Extend the Compose stack with the Pushgateway and a tiny Python service using `prometheus_client`: one `Counter` labeled `["endpoint", "status"]`, one `Histogram` for request duration, `/metrics` on port 9101. Generate traffic with `hey` or a loop of `curl`, and confirm the series appear in Prometheus's TSDB status page.
2. Deliberately push cardinality: add a `user` label fed with random values, push 100 requests, and read the series count explosion on the TSDB page. Remove the label, restart, and verify recovery - then write down the cardinality budget rule for your own team.
3. Push a batch result: `echo "batch_result 1" | curl --data-binary @- http://localhost:9092/metrics/job/nightly/instance/lab`, scrape the Pushgateway from Prometheus, and query `time() - push_time_seconds{job="nightly"}`. Restart the lab tomorrow in your head: what would the staleness alert look like?
4. Wire the blackbox job from [Chapter 4](#ch4) against two real URLs (one of your own services, one external). Query `probe_success` and `probe_duration_seconds`, and identify which labels came from relabeling.
5. Break synthetic monitoring on purpose: point one probe target at a closed port, confirm `probe_success == 0`, then write the query you would alert on. You will implement this alert for real in [Lab 4](#lab4).
:::

**See also:** [Chapter 5](#ch5) queries everything this chapter produced, [Chapter 7](#ch7) replaces the static target lists with discovery and relabeling, and [Chapter 13](#ch13) shows what cAdvisor and kube-state-metrics look like when Kubernetes is the substrate.
