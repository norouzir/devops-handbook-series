# Chapter 3 - Installation and Your First Metrics {#ch3}

## 3.1 Ways to Run Prometheus

There are three ways to put a Prometheus server into the world, and they map onto three stages of a team's maturity. The **bare binary** is the way to understand the machine: download, unpack, run, and every flag and file is visible. **Containers** - Docker or Docker Compose - are how you run the full demo stack this book uses, because Prometheus plus exporters plus Grafana is a multi-process system that Compose describes better than prose. **Kubernetes**, via the Prometheus Operator and kube-prometheus-stack, is how production estates run it at scale - the entire subject of [Chapter 13](#ch13), which assumes the concepts this chapter builds.

The recommendation is chronological, not either/or: run the binary once to see the defaults, live in Docker Compose for the rest of Part I, and graduate to Kubernetes when the operator model makes sense. Every example in this book runs on a laptop or a single small VM.

## 3.2 The Binary, the Config, and the Anatomy of prometheus.yml

A release tarball from [prometheus.io/download](https://prometheus.io/download/) contains the server binary and `promtool`. A minimal systemd unit is ten lines:

```ini
[Unit]
Description=Prometheus
After=network-online.target

[Service]
User=prometheus
ExecStart=/opt/prometheus/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --web.listen-address=0.0.0.0:9090
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

The configuration file has four top-level sections, and every example in this book is an extension of this skeleton:

```yaml
global:
  scrape_interval: 15s        # how often to scrape each target
  evaluation_interval: 15s    # how often to evaluate rules
  scrape_timeout: 10s         # per-scrape deadline

rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  - job_name: prometheus      # Prometheus monitors itself first
    static_configs:
      - targets: ["localhost:9090"]

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["localhost:9093"]
```

`scrape_configs` is the heart: each `job_name` defines a group of targets scraped with the same policy, and `static_configs` is the simplest source of targets - a literal list. When a scrape runs, Prometheus adds `job="<job_name>"` and `instance="<host:port>"` labels to every sample from that target, which is how most queries slice by service and by replica. [Chapter 7](#ch7) replaces `static_configs` with service discovery; the job label remains the constant.

Configuration changes take effect on **reload**, not restart: send `SIGHUP`, or POST to `/-/reload` with `--web.enable-lifecycle` set, and Prometheus re-reads the file without dropping data. `promtool check config prometheus.yml` validates the file (and any rule files it references) before you touch the running server - make it a pre-commit reflex.

## 3.3 The Docker Compose Stack

The stack this book builds on has four services: Prometheus, node_exporter (host metrics), blackbox_exporter (synthetic probes, used in [Chapter 4](#ch4)), and Grafana (dashboards from [Chapter 9](#ch9)). A single `docker-compose.yml` ties them together:

```yaml
services:
  prometheus:
    image: prom/prometheus:v3.15.1
    volumes:
      - ./prometheus:/etc/prometheus
      - prom-data:/prometheus
    ports: ["9090:9090"]
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --web.enable-lifecycle

  node-exporter:
    image: prom/node-exporter:v1.12.1
    pid: host
    volumes:
      - /:/host:ro,rslave
    command:
      - --path.rootfs=/host
    ports: ["9100:9100"]

  blackbox-exporter:
    image: prom/blackbox-exporter:v0.29.1
    ports: ["9115:9115"]

  grafana:
    image: grafana/grafana:13.3.0
    ports: ["3000:3000"]
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  prom-data:
  grafana-data:
```

The `prometheus.yml` this stack consumes starts with two jobs - the self-scrape above plus `node` targeting `node-exporter:9100` - and grows in every subsequent chapter:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]

  - job_name: node
    static_configs:
      - targets: ["node-exporter:9100"]
```

`docker compose up -d` later, and three UIs are live: Prometheus at `http://localhost:9090`, node_exporter's raw exposition at `http://localhost:9100/metrics`, Grafana at `http://localhost:3000` (default admin/admin, changed on first login). Worth ten minutes of curiosity: the raw `/metrics` text format is plain key-value lines with `HELP` and `TYPE` comments - the format every exporter in the ecosystem speaks, and exactly what Prometheus parses.

::: {.warn}
**Watch out - container networking and localhost**

Inside the Compose network, service names are the hostnames: Prometheus scrapes `node-exporter:9100`, not `localhost:9100`. The reverse confusion - putting container names in a `prometheus.yml` that runs on the host, or `localhost` in a config running in a container - is the most common first-day failure. The scrape *target* URL is resolved by whoever runs the scraper.
:::

## 3.4 Reading the Prometheus Web UI

The 3.x UI is organized into six areas, three of which matter immediately. **Graph** is the query console: type PromQL into the box, and the table view shows instant values while the graph view draws the time range. **Status → Targets** is the operational heartbeat - every configured target with its last scrape time, duration, and any error, green or red; when a dashboard is empty, this page is the first place you look. **Status → TSDB** shows the live cardinality picture: number of series, number of samples in the head block, and a per-metric breakdown that answers "what is eating my memory?" before it becomes an incident. The remaining areas (Rules, Service Discovery, Command-line flags, Build information) document the running configuration and are worth a skim now, so you know where the ground truth lives.

One flag earns its place in every non-trivial deployment: `--web.enable-lifecycle` (already set in the Compose file), which enables `curl -X POST http://localhost:9090/-/reload` for configuration reloads - the difference between a config change being a curl command and a service restart.

## 3.5 Your First Queries

With node_exporter scraped for a few minutes, the TSDB holds thousands of series, and three queries make the data model concrete. Type them into the Graph tab in order:

```promql
up                                          # 1 if the last scrape succeeded, 0 if not
node_load1                                  # 1-minute load average as a gauge
rate(node_cpu_seconds_total{mode!="idle"}[5m])   # per-CPU busy fraction per core
```

`up` deserves special attention: it is synthesized by Prometheus itself for every scrape target, it is the backbone of availability alerting in [Chapter 8](#ch8), and the phrase "is it up?" in a Prometheus shop is literally `up{job="node"} == 1`. The `rate(...)` expression introduces the shape of nearly every useful query in this book - a counter, wrapped in a windowed rate function, filtered by label matchers - and [Chapter 5](#ch5) dissects every token in it. For now, change the `5m` window to `1m` and back, and observe how the graph smooths: that trade between responsiveness and noise is a theme the rest of the book formalizes.

::: {.note}
**Best practice - scrape intervals are a design decision, not a setting**

15 seconds is a sensible default: fast enough for operational alerting, cheap enough for thousands of targets. Dropping to 5s multiplies storage, cardinality pressure, and network chatter for graphs that look identical to a human; stretching to 60s+ makes `rate()` windows and alert `for` clauses sluggish. Choose one interval, document it, and let the recording rules in [Chapter 6](#ch6) provide the faster views where they are genuinely needed.
:::

## 3.6 Lab 1: The Full Loop in Miniature

::: {.lab}
### Lab 1 - Prometheus, node_exporter, and Grafana from zero {#lab1}

1. Create the project directory with `docker-compose.yml`, `prometheus/prometheus.yml` (both jobs), and bring the stack up with `docker compose up -d`. Verify `docker compose ps` shows all four services healthy.
2. Confirm the self-scrape: open `http://localhost:9090/targets` and check both targets are `up` with a scrape duration under 100 ms. Then visit `http://localhost:9100/metrics` and find `node_cpu_seconds_total` in the raw text - note the `HELP`/`TYPE` lines and the label sets.
3. In the Prometheus Graph tab, run `up`, then `rate(node_cpu_seconds_total{mode!="idle"}[5m])`. Graph the result for the last hour, then switch to the Table tab and read the instant values. Explain to yourself why the number of series differs between the two queries.
4. Break it deliberately: stop the node-exporter service (`docker compose stop node-exporter`), refresh the Targets page, and observe `up == 0` and the error message. Query `up` in the graph view. Restart, and watch it recover - this is the alert you will build in [Lab 4](#lab4).
5. Prove the reload workflow: add a third job scraping `blackbox-exporter:9115`, run `docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml`, then `curl -X POST http://localhost:9090/-/reload`, and confirm the new target appears without a restart.
6. Log into Grafana at `http://localhost:3000`, and add a Prometheus data source pointing at `http://prometheus:9090` (the data source chapter is coming - the point today is that the stack is connected end to end). Save, and note the connection status message.
:::

**See also:** [Chapter 4](#ch4) fills the stack with real telemetry from exporters and instrumented code, and [Chapter 9](#ch9) turns Grafana's data source configuration into a discipline.
