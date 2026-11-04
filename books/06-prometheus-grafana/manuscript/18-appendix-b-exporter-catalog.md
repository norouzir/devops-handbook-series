# Appendix B - Exporter Catalog {#appB}

The exporters a DevOps engineer meets most often. All are scraped identically ([Chapter 4](#ch4)); "port" is the conventional listen port. Versions are the current stable lines as of October 2026 for the official exporters.

## B.1 Hosts and Infrastructure

| Exporter | Port | Exposes | Notes |
|---|---|---|---|
| node_exporter 1.12 | 9100 | Kernel, CPU, memory, disk, FS, network | Per host/VM; collectors toggleable; textfile collector for scripts |
| windows_exporter | 9182 | Windows perf counters | Services, memory, logical disks, IIS |
| blackbox_exporter 0.29 | 9115 | HTTP/TCP/ICMP/gRPC probe results | Synthetic monitoring; targets via relabeling params |
| snmp_exporter | 9116 | SNMP devices | Switches, routers, UPSes; generator builds config |
| ipmi_exporter | 9290 | IPMI/BMC sensors | Out-of-band hardware health |

## B.2 Kubernetes and Containers

| Exporter / source | Port | Exposes | Notes |
|---|---|---|---|
| kubelet + cAdvisor | 10250 | Per-container CPU/mem/net/FS | Discovered via node role; `container_*` metrics |
| kube-state-metrics | 8080 | Object state | Deployments, pods, jobs, PVCs - `kube_*` series |
| Prometheus Operator | 8080 | Operator + generated targets | CRD health; see [Chapter 13](#ch13) |
| kube-prometheus-stack | - | The assembled stack | Helm chart; ships the mixin rules |
| NVIDIA dcgm-exporter | 9400 | GPU utilization, memory, errors | Standard for AI workloads |

## B.3 Databases and Middleware

| Exporter | Port | Exposes |
|---|---|---|
| postgres_exporter | 9187 | Queries, locks, replication, cache hit ratio |
| mysqld_exporter | 9104 | Throughput, InnoDB, replication lag |
| redis_exporter | 9121 | Ops/sec, memory, keys, latency |
| mongodb_exporter | 9216 | Ops, replication, cache |
| rabbitmq_exporter | 9419 | Queue depth, publish/deliver rates |
| kafka_exporter | 9308 | Offsets, lag, partitions |

## B.4 Applications and Protocols

| Exporter | Port | Exposes |
|---|---|---|
| Client libraries (Go, Python, Java, Ruby, Rust, JS, .NET) | app port | First-party instrumentation - preferred whenever you own the code |
| OpenTelemetry Collector → OTLP | 4317/4318 | OTel SDKs; Prometheus 3 ingests natively ([Chapter 4](#ch4)) |
| jmx_exporter | 9404 | JVM + arbitrary JMX beans (Java agent) |
| statsd_exporter | 9125 | StatsD bridge for legacy emit paths |
| pushgateway 1.11 | 9091 | Batch-job results ([Chapter 4](#ch4)) |
| Grafana Alloy / OTel Collector | - | Agent that scrapes/relays fleets into Prometheus |

## B.5 The textfile Collector Pattern

For host facts no exporter covers, node_exporter's textfile collector reads metric files on schedule - the sanctioned bridge for one-off scripts:

```bash
# /var/lib/node_exporter/textfile/cert_expiry.prom
# HELP cert_expiry_seconds Seconds until certificate expiry
# TYPE cert_expiry_seconds gauge
cert_expiry_seconds{domain="example.com"} 2145600
```

Rules that make it production-grade: atomic writes (write temp, `mv`), one file per producer, `HELP`/`TYPE` on every metric, and a staleness alert on the file's `mtime` so a silently dead cron job cannot outlive its usefulness.

## B.6 Writing a Good Exporter: The Checklist

1. Expose on `/metrics`, plain HTTP, no auth by default (bind to localhost/VPN; auth at the scrape layer).
2. Names: snake_case, unit suffix (`_seconds`, `_bytes`), `_total` on counters; `HELP` and `TYPE` on every family.
3. Labels: bounded values only ([Chapter 2](#ch2)); the job label already says who you are - do not repeat it in names.
4. Idempotent exposition: two scrapes seconds apart may differ in *value*, never in *shape*.
5. Cache expensive queries with a TTL rather than making the scrape interval your worst-case timeout.
6. Derive, do not aggregate: expose facts; let PromQL do the math ([Chapter 5](#ch5)).
7. Document every metric the way a stranger will read it at 3 a.m. - because someone will.
