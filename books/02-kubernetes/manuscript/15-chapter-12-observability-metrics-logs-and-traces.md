# Chapter 12 - Observability: Metrics, Logs, and Traces {#ch12}

Kubernetes gives you an observable system by accident and an understood system only by design. The API streams events for everything, containers log to stdout by the Docker book's convention, and every component exports Prometheus metrics; none of that helps until the three pillars are collected, labeled, and retained somewhere queryable. This chapter builds the standard stack, metrics with Prometheus, logs with aggregation, traces with OpenTelemetry, and closes with the discipline that makes it useful in an incident: alerts that a human can act on.

## 12.1 Metrics: The Numbers Layer

Two layers of metrics exist and confusing them wastes debugging time. The resource metrics pipeline is small and built-in: `metrics-server` scrapes `kubelets`, serves `metrics.k8s.io`, and powers `kubectl top` and the HPA; it holds minutes of history and answers the question, what is consuming capacity right now. The monitoring pipeline is Prometheus: a time-series database that scrapes every component's `/metrics` endpoint, from `kube-state-metrics`, which turns API objects into series, to `node-exporter` on every node to `cAdvisor` in the `kubelet` to your own applications. The `kube-prometheus-stack` Helm chart from Chapter 8 installs the whole layer with Grafana and a sensible default ruleset, which is why it is the de facto starting point.

PromQL is small and worth learning properly, because the four golden signals, latency, traffic, errors, saturation, are each one or two queries away. A service's p99 latency is `histogram_quantile` over a histogram metric; traffic is a rate counter; error rate is a ratio of error counters to total; saturation is usage against a limit, and for Kubernetes specifically, `container_memory_working_set_bytes` against the `Pod`'s memory limit predicts OOMKills before they happen, the query every cluster should have on a dashboard.

```bash
# p99 request latency by service (histogram metric)
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))

# error ratio over 5 minutes
sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
  / sum(rate(http_requests_total[5m])) by (service)

# memory saturation vs. limit - the OOMKill predictor
max(container_memory_working_set_bytes{namespace="prod"}) by (pod)
  / max(kube_pod_container_resource_limits{resource="memory", namespace="prod"}) by (pod)
```

## 12.2 Logs: The Words Layer

The contract from the Docker book holds unchanged: applications log to stdout and stderr, the runtime captures them, and `kubectl logs` reads them, with `-f` to follow, `-p` for the previous crashed instance, and container names to disambiguate multi-container `Pods`. The cluster-level move is shipping: a `DaemonSet` agent such as Fluent Bit or Promtail tails the container log files on every node, enriches each line with `Pod`, namespace, and label metadata, and forwards to Loki, Elasticsearch, or your cloud's log service. Because enrichment happens at the node, labels travel with every line, and the Kubernetes-native debugging chain works: from an alert to a `Pod`, from the `Pod`'s labels to its logs, from the logs to the commit.

Two practices keep logs usable at scale. Structured logging, one JSON object per line with stable keys, turns `grep` into query and is the difference between finding and skimming under pressure. And retention is an architecture decision: keep the hot tail in the query engine for days, ship the cold tail to cheap storage, and set the `kubelet`'s log rotation limits on the node, because an unrotated log on a small node is a disk-pressure eviction waiting for a busy night. What you should not log is as important: secrets and personal data in logs are incidents in storage, and the redaction habits from the Docker book's configuration chapter apply verbatim.

## 12.3 Traces: The Journey Layer

Metrics say something is slow; traces say where. OpenTelemetry has settled into the standard instrumentation layer: applications emit spans through a vendor-neutral SDK, an OTLP exporter ships them to a collector, and the collector routes to Jaeger for development or a commercial backend, all without changing application code when you change vendors. A trace assembles one request's path across `Services`, and in a Kubernetes estate the essential contextual link is automatic only if you propagate it: the trace and span IDs ride headers, and every hop must forward them. Instrument the edges first, the gateway and the first two internal hops, because that is where the majority of latency hides, and sample deliberately at volume rather than recording everything and paying for it later.

## 12.4 Alerts That Respect Operators

Observability fails socially before it fails technically: the stack that pages for everything trains its humans to ignore everything. Alert on symptoms users feel, error ratio, p99 latency, queue age, rather than causes, and let `Alertmanager` route, group, and deduplicate; a `Pod` restarting twice is a dashboard line, an error budget burn is a page. Ground the thresholds in SLOs, the error budget method gives you a defensible line between noise and emergency, and review alerts after every incident with one question: would the on-call have acted differently with, or without, this alert. The cluster's own health belongs in the same discipline, node conditions, certificate expiries, PVC capacity, all of which the `kube-prometheus-stack` defaults already cover if you actually read what they alert on.

::: {.lab}
### Lab 4 - Stand up the observability stack {#lab4}

1. Install `metrics-server` and the `kube-prometheus-stack` chart from Chapter 8 into your `kind` cluster, then confirm `kubectl top nodes` and `kubectl top pods -A` return data. Note which metrics API version serves them.
2. Open Grafana with `kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring`, log in, and find the Node Exporter and Kubernetes compute dashboards. Identify the memory-saturation panel and match it to the PromQL from Section 12.1.
3. Generate load against the `api` `Deployment` from Chapter 4, watch `kubectl top pods` climb, and confirm the HPA from Chapter 10 reacts if you installed it; if not, observe the metrics yourself and compute what the HPA would do.
4. Break the logs contract on purpose: run a `Pod` that writes to a file instead of stdout, then run one that logs JSON to stdout. Use `kubectl logs -f` and a Loki query (or the Grafana log view) to show which one you can actually search.
5. Query the API's event stream like an operator: `kubectl get events -A --sort-by=.lastTimestamp | tail -30`. Pick the three most recent warnings and say, for each, which pillar you would consult next and why.
:::

**See also:** [Chapter 10](#ch10) for the metrics a scheduler already exposes, [Chapter 14](#ch14) for incident response.
