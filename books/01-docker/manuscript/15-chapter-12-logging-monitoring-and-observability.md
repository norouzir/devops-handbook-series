# Chapter 12 - Logging, Monitoring, and Observability {#ch12}

Containers make observability simpler in one way and less forgiving in another: the contract is that everything important goes to stdout and stderr, and nothing important lives only inside the container. This chapter covers the machinery on both sides of that contract - how the daemon captures and ships logs, how to read container and daemon metrics, and the reference stack that turns both into dashboards and alerts.

## 12.1 The Logging Contract and the Drivers

A containerized application writes logs to stdout and stderr and keeps no local log files; the platform owns collection. The daemon implements that ownership with pluggable **logging drivers**. The default `json-file` driver writes each container's output to files under the data root and is what `docker logs` reads. The `local` driver is its production-grade sibling - same behavior, a more compact on-disk format, better default performance - and is the recommended default for hosts that only need local files plus rotation. The shipping drivers forward in real time: `syslog` and `journald` to the host's classic facilities, `fluentd` and `gelf` to log aggregators, `awslogs`, `gcplogs`, and `splunk` to their clouds, and `none` when an external agent (a file-shipping sidecar reading shared volumes, for example) owns collection. Drivers are set per daemon in daemon.json (Chapter 2's `log-driver`) or per container with `--log-driver` and `--log-opt`.

| Driver | Behavior | Use when |
| --------- | --------------------- | -------------------- |
| json-file | Default; JSON lines on local disk; readable by docker logs | Development and small hosts; set rotation opts explicitly |
| local | Compact binary format on disk; docker logs compatible | Production default for local-only logging |
| syslog / journald | Forwards to host syslog or systemd journal | Hosts already centralized on syslog |
| fluentd / gelf | Streams structured events to an aggregator | You run (or target) a central log platform |
| awslogs / gcplogs / splunk | Native cloud delivery | The cloud provider is your log platform |
| none | Discards output | External agents own collection exclusively |

: Table 12.1 - Logging drivers and when to use them

## 12.2 Rotation Before Regret

Unbounded `json-file` logs are the most common self-inflicted Docker outage: a chatty container fills the disk, and everything on the data root suffers. Rotate by default, at the daemon level, exactly as Chapter 2 configured: `log-opts` with `max-size` (10m is a sane start) and `max-file` (5). The options apply at container creation, so containers started before a daemon.json change keep old behavior until recreated - another reason to bake logging config into images and Compose files rather than ad hoc. When shipping drivers are in play, rotation becomes the receiver's problem, which is one more argument for centralizing: local files with rotation for the tail you need at 3 a.m., shipping for everything else.

```bash
docker run -d --name chatty \
  --log-driver local \
  myorg/api:1.4.0

# per-container override with json-file
docker run -d --name capped \
  --log-driver json-file \
  --log-opt max-size=10m --log-opt max-file=5 \
  myorg/api:1.4.0

docker inspect --format '{{.HostConfig.LogConfig}}' capped
```

## 12.3 Events, Stats, and the Daemon Metrics Endpoint

Three interfaces cover live operational truth. `docker events` is the daemon's audit tape - container start/stop/die, OOM kills, health status changes, image pulls - and a saved stream of it is the fastest post-incident reconstruction you will ever run. `docker stats` (and the underlying `/containers/{id}/stats` API) streams per-container CPU, memory, block I/O, and network counters; alert on memory approaching limits because that is where OOM kills are born. The daemon itself exports Prometheus-format metrics when `metrics-addr` is set (Chapter 2) - experimental but genuinely useful, exposing builder activity, container counts, and daemon health on `127.0.0.1:9323/metrics` for your Prometheus to scrape.

```bash
docker events --since 1h --filter type=container --filter event=die
docker stats --no-stream
# prometheus scrape target, after metrics-addr in daemon.json
# 127.0.0.1:9323/metrics
```

## 12.4 The Reference Monitoring Stack

The pattern that dominates Docker estates is Prometheus for metrics, Grafana for dashboards, and Loki (or the aggregator your logging driver feeds) for logs. **cAdvisor** runs as a container itself, collects per-container resource metrics from the kernel, and exposes them for Prometheus scraping; **node_exporter** covers host-level metrics; Prometheus stores and evaluates alert rules; Grafana visualizes; Loki receives logs shipped by `fluentd`/`gelf`/`promtail` and links them to the same labels. Deploy it with the Compose skills of Chapter 9, point it at every Docker host, and resist the urge to collect everything at high cardinality first - start with the four golden signals (latency, traffic, errors, saturation) per service and grow dashboards when an incident asks for them. This book stays deliberately at the Docker boundary: writing alert rules and dashboards belongs to a monitoring text, but standing up the pipeline that feeds them is Docker work and now yours.

## 12.5 Healthchecks as Monitoring Signals

The HEALTHCHECK you added in Chapters 5 and 9 is not just a deploy gate - it is the cheapest availability probe you own. The daemon runs it on schedule, reflects the result in `docker ps` (healthy / unhealthy) and in events, and orchestrators act on it (Swarm replaces unhealthy tasks; Compose `--wait` gates on it). Design probes to test the thing users depend on - an endpoint that touches the database, not merely the process's existence - with an interval fast enough to catch real failures and a `start_period` that forgives boot time. Then wire the signal outward: scrape the health status, alert on sustained unhealthy, and treat a flapping healthcheck as a bug in either the probe or the application - it is always one of the two.

::: {.lab}
### Lab 12 - Ship logs, scrape metrics {#lab12}

1. Check your current defaults (`docker info | grep -A3 Logging`), start two containers with different `max-size` settings, generate output, and find the files on disk (`docker inspect` the LogPath).
2. Run `docker events` in one terminal while starting, stopping, and OOM-killing containers in another; match every event to the action that caused it.
3. Enable `metrics-addr: 127.0.0.1:9323` in daemon.json, restart, and curl the metrics endpoint; identify five metrics you would alert on.
4. Deploy cAdvisor plus Prometheus plus Grafana with a compose file; build one dashboard with container CPU and memory, and verify cAdvisor sees your other lab containers.
:::

**See also:** [Chapter 10](#ch10) for the security events worth shipping to a log store, [Chapter 11](#ch11) for the platform pieces that generate them, and [Chapter 13](#ch13) for alerts that page a human.
