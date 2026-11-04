# Appendix C - Troubleshooting Guide {#appC}

Organized by symptom, in the order the symptoms usually appear. Each entry names the first place to look, then the likely causes.

## C.1 "My panel/query shows No Data"

**First: Status → Targets in Prometheus** ([Chapter 3](#ch3)).

- Target **down** (red): scrape error in the Target page - wrong address/port ([Chapter 3](#ch3) networking note), TLS failure, exporter not started, network policy blocking.
- Target **up**, metric missing: `curl` the exporter's `/metrics` ([Chapter 4](#ch4)) - is the metric there at all? Then check relabeling: `keep`/`drop` rules ([Chapter 7](#ch7)), `metric_relabel_configs` dropping by name, `sample_limit` exceeded on the target page.
- Metric exists, query empty: label matchers too strict (remember `!=`/`!~` do not match missing labels - [Chapter 5](#ch5)); time range too narrow for staleness ([Chapter 5](#ch5)); dashboard variable empty (variable query returns nothing - fix the variable, [Chapter 10](#ch10)).
- Grafana-only: data source URL wrong *from Grafana's network* (`localhost` inside a container is a classic - [Chapter 9](#ch9)); data source UID changed and dashboards reference the old one; `min interval` set above the scrape interval.

## C.2 "Targets flap up/down"

- Scrape timeout too small for a slow exporter: raise `scrape_timeout` (must stay < `scrape_interval`, [Chapter 3](#ch3)).
- Exporter CPU-starved or blocked on the system it reads (a PostgreSQL exporter waiting on a locked catalog).
- Load balancer or DNS returning rotating addresses; Prometheus is honest about the churn - fix the discovery layer ([Chapter 7](#ch7)).
- Series explosion on one target pushing scrape duration toward the timeout - TSDB status page, per-metric series count ([Chapter 2](#ch2)).

## C.3 "Prometheus memory is climbing / OOMs"

1. TSDB status page: Head stats (series, samples/sec) and the per-metric breakdown.
2. Churn check: series created *per second* high (flapping pod labels, cron-issued label sets) - [Chapter 12](#ch12).
3. Cardinality accidents: a label with unbounded values from [Chapter 4](#ch4)'s watch-out list; fix at instrumentation, then mop with `metric_relabel_configs` ([Chapter 7](#ch7)).
4. Query pressure: someone graphing a year of per-second data ([Chapter 10](#ch10)) - check `prometheus_engine_query_*` metrics and add recording rules.
5. If load is genuine: shard ([Chapter 7](#ch7) hashmod) or move long-term storage out ([Chapter 12](#ch12)).

## C.4 "Queries are slow"

- Count before you compute: `count(your_metric)` per label set - the blast radius ([Chapter 6](#ch6)).
- Aggregate early, avoid `.*` regex on high-cardinality labels, and move repeated expressions into recording rules ([Chapter 6](#ch6)).
- Subqueries on heavy inner expressions: each step re-evaluates everything - convert to recording rules.
- Grafana side: check max data points and refresh ([Chapter 10](#ch10)); compare the same query in the Prometheus UI - if fast there, the dashboard is the problem.

## C.5 "Alerts do not fire / do not arrive"

Pipeline diagnosis, in order ([Chapter 8](#ch8)):

1. **Rule page** (Prometheus → Alerts): is the rule pending/firing? Not firing → test the expression in the query box; check `for` and the evaluation interval; check the rule file loaded (`promtool check config`).
2. **Alertmanager UI**: did the alert arrive? No → `alerting:` section wrong, or AM unreachable from Prometheus.
3. **Routing tree view**: did it match a route? No → matcher syntax (matchers are label *sets*: `severity="critical"`), group_by hiding it.
4. **Silences/inhibition**: something matching ([Chapter 8](#ch8) - the tree view shows held alerts).
5. **Receiver delivery**: contact point credentials, `send_resolved` assumptions, webhook endpoint logs.
6. Grafana alerting stack instead/also? Two pipelines, one on-call - [Chapter 11](#ch11)'s hybrid section.
7. Silent pipeline itself broken: the deadman watchdog ([Chapter 12](#ch12)) exists precisely for this.

## C.6 "Alerts fire but are noisy"

- Missing or too-short `for` ([Chapter 8](#ch8)); add 2-5m for infra metrics.
- Alerting on causes instead of symptoms; rebuild on the symptom dashboard's query.
- Flapping identity: per-instance labels on a service-level condition - aggregate in the expression.
- Single-window burn-rate rules: pair with a short confirmation window ([Chapter 8](#ch8)).
- Grouping off: `group_by` on alertname/job so storms collapse.

## C.7 "Grafana dashboards are slow or erroring"

- Panel error naming the data source: Save & test it ([Chapter 9](#ch9)); check Grafana server logs for the underlying HTTP error.
- Timeouts on heavy panels: recording rules ([Chapter 10](#ch10)); reduce panel count; check refresh rates.
- "Data source not found": UID references after re-provisioning; provisioned dashboards referencing renamed data sources.
- After Grafana upgrade: read the upgrade guide and breaking changes - Grafana 13's dynamic dashboard migration ([Chapter 9](#ch9)) is automatic, but plugins lag.

## C.8 "Kubernetes: my ServiceMonitor/PodMonitor does nothing"

1. `kubectl get servicemonitor <name> -o yaml` - does its `release` label match the Prometheus's `serviceMonitorSelector` ([Chapter 13](#ch13))? The chart default keys on the Helm release name.
2. Service port name mismatch: `endpoints.port` must equal the Service's *port name*.
3. `namespaceSelector` missing the workload's namespace.
4. Operator logs (`kubectl logs -n monitoring deploy/kube-prometheus-stack-operator`) show the generated config; the Prometheus UI's Service Discovery page shows what was actually built.
5. Rule not evaluating: same release-label check on the `PrometheusRule`, then the Rules page in the Prometheus UI.

## C.9 "The numbers do not agree" (two dashboards disagree)

- Different windows: `rate(...[5m])` versus `$__rate_interval` at a different step ([Chapter 5](#ch5), [Chapter 9](#ch9)).
- Different aggregation levels: `by (job)` versus per-instance sums ([Chapter 5](#ch5)).
- One panel reading raw series, the other a recording rule with a different interval ([Chapter 6](#ch6)).
- HA dedup missing: two replicas' series both counted (no `sum`, or dedup not configured - [Chapter 12](#ch12)).
- Histogram buckets changed between versions: quantiles shift legitimately ([Chapter 6](#ch6)).

## C.10 "Everything broke at once"

- Config change gone wrong: reloads are atomic - a bad config is rejected and the old one keeps running; a *valid but wrong* config needs the rollback ([Chapter 3](#ch3)). Check what changed (Git, [Chapter 10](#ch10)).
- Disk full on the TSDB volume: Prometheus exits uncleanly at 100% - expand, and set `--storage.tsdb.retention.size` as the guardrail.
- Certificate or DNS expiry on the scrape path: blackbox probes ([Chapter 4](#ch4)) exist to see it before users do.
- Kubernetes: check the operator first, then the StatefulSets; kube-prometheus-stack's own alerts ([Chapter 13](#ch13)) are the cluster's self-report.
