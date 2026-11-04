# Appendix A - PromQL and CLI Quick Reference {#appA}

## A.1 Data Types and Selectors

| Concept | Syntax | Notes |
|---|---|---|
| Instant vector | `metric{label="v"}` | One sample per series at evaluation time |
| Range vector | `metric[5m]` | Window of samples per series; input to rate/`_over_time` |
| Matchers | `=`, `!=`, `=~`, `!~` | Regex is RE2, fully anchored |
| Metric name | `{__name__=~"node_.*_bytes"}` | Long form for multi-metric selection |
| Label-less series | `method=""` matches missing | `!=`/`!~` do **not** match missing labels |
| Subquery | `expr[1h:1m]` | Range from instant expression, own resolution |
| Offset / pin | `offset 1w`, `@ 1700000000` | Compare past; pin to timestamp |

## A.2 Counter and Gauge Functions

| Function | Use | Notes |
|---|---|---|
| `rate(c[5m])` | Per-second average, reset-aware | Window ≥ 4 × scrape interval |
| `irate(c[5m])` | Last-two-samples rate | Graphs only; not for alerting |
| `increase(c[1h])` | Estimated increase over window | rate × window |
| `delta(g[1h])` | Gauge change over window | Can be negative |
| `idelta(g[5m])` | Last-two-samples gauge delta | |
| `*_over_time(r[1h])` | avg, min, max, sum, count, quantile, stddev, last, present | Gauge/window reductions |
| `predict_linear(g[6h], 86400)` | Linear forecast | Disk-fill alerts |
| `absent(m)`, `absent_over_time(m[30m])` | Metric stopped existing | Different from `up == 0` |

## A.3 Aggregation and Arithmetic

```promql
sum by (job) (rate(http_requests_total[5m]))
sum without (instance) (rate(http_requests_total[5m]))
topk(3, rate(http_requests_total[5m]))
histogram_quantile(0.95, sum by (job, le) (rate(latency_seconds_bucket[5m])))
rate(errors_total[5m]) / rate(requests_total[5m])          # per-label match required
sum by (job) (rate(errors_total[5m])) / sum by (job) (rate(requests_total[5m]))
metric * on (instance) group_left(node_info_field) node_info   # many-to-one join
sum(rate(x[5m])) > bool 10                                    # filter vs 0/1 mode
```

Aggregators: `sum`, `avg`, `min`, `max`, `count`, `stddev`, `stdvar`, `topk`, `bottomk`, `quantile`, `count_values`, `group`. Matching: `on` / `ignoring` + `group_left` / `group_right`. Label algebra: `label_replace(v, "dst", "$1", "src", "(.*)")`, `label_join(v, "dst", "-", "a", "b")`.

## A.4 Recording Rule Naming

`level:metric:operations` - colon-delimited, no units in the level, operations listed at the level applied:

```
job:http_requests:rate5m
job:http_errors:ratio_rate5m
job:http_request_duration_seconds:p95_rate5m
namespace:node_cpu_utilisation:rate5m
```

## A.5 prometheus.yml Skeleton

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
rule_files: ["/etc/prometheus/rules/*.yml"]
alerting:
  alertmanagers:
    - static_configs: [{ targets: ["alertmanager:9093"] }]
scrape_configs:
  - job_name: node
    static_configs: [{ targets: ["node-exporter:9100"] }]
remote_write:
  - url: https://mimir.example.com/api/v1/push
```

Useful flags: `--config.file`, `--storage.tsdb.path`, `--storage.tsdb.retention.time=15d`, `--web.enable-lifecycle` (POST `/-/reload`), `--web.enable-otlp-receiver`, `--log.level=info`.

## A.6 alertmanager.yml Skeleton

```yaml
route:
  receiver: default-slack
  group_by: [alertname, job]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers: [severity="critical"]
      receiver: pagerduty
inhibit_rules:
  - source_matchers: [alertname="TargetDown"]
    target_matchers: [severity="warning"]
    equal: [instance]
receivers:
  - name: default-slack
    slack_configs: [{ send_resolved: true, text: '{{ .CommonAnnotations.summary }}' }]
```

## A.7 CLI Cheat Sheet

| Command | Purpose |
|---|---|
| `promtool check config prometheus.yml` | Validate config + referenced rules |
| `promtool check rules rules/*.yml` | Validate rule files alone |
| `promtool query instant http://localhost:9090 'up'` | Query from the shell |
| `promtool query range ... 'query' --start=... --end=...` | Range query |
| `promtool tsdb list` / `promtool tsdb analyze` | Inspect TSDB blocks / cardinality |
| `curl -X POST http://localhost:9090/-/reload` | Hot reload (needs lifecycle flag) |
| `amtool config check alertmanager.yml` | Validate AM config |
| `amtool silence add instance=web-01 -d 2h -c "reason"` | Create silence |
| `amtool silence expire <id>` / `amtool silence list` | Manage silences |
