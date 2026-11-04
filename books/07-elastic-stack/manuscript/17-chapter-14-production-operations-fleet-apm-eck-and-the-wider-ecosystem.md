# Chapter 14 - Production Operations: Fleet, APM, ECK, and the Wider Ecosystem {#ch14}

## 14.1 Running on Kubernetes with ECK

For estates already on Kubernetes - which by now describes most estates this series' readers work in - the question is not *whether* to run Elastic on Kubernetes but *with what management layer*. Running Elasticsearch as bare Deployments fights the distributed state problem by hand: pod identity, storage binding, rolling upgrades with shard awareness, certificate rotation. The **ECK operator** (Elastic Cloud on Kubernetes, current line 3.x) exists to own exactly those mechanics: it manages Elasticsearch, Kibana, Agent, and Fleet Server through custom resources, generating certificates, wiring storage, and orchestrating shard-safe rolling restarts automatically:

```yaml
apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: logs
spec:
  version: 9.5.5
  nodeSets:
    - name: masters
      count: 3
      config:
        node.roles: ["master", "data_hot", "data_content", "ingest"]
        node.store.allow_mmap: false
      resources:
        requests: { memory: 4Gi, cpu: "2" }
    - name: hot
      count: 4
      config:
        node.roles: ["data_hot", "data_content", "ingest"]
      resources:
        requests: { memory: 16Gi, cpu: "4" }
      volumeClaimTemplates:
        - metadata: { name: elasticsearch-data }
          spec:
            accessModes: ["ReadWriteOnce"]
            resources: { requests: { storage: 500Gi } }
```

The manifest is the architecture of [Chapter 11](#ch11) expressed declaratively: role-separated node sets, sized resources, persistent volumes - and the operator's reconciliation loop keeps reality matched to it. A matching `Kibana` resource attaches the UI, and `Agent` resources roll Elastic Agents out as DaemonSets across the cluster's own nodes. The operator's security defaults deserve the emphasis: TLS on both layers, generated credentials, and per-node certificates come out of the box, making the manual loop of [Chapter 12](#ch12) an automated inheritance. ECK is free (Basic tier) with the same license structure as the stack itself; the operational trade it makes is a real one - the operator *is* a component to monitor and upgrade, and teams adopting it should version its manifests like any other infrastructure code, per the Terraform and Ansible volumes of this series.

## 14.2 Fleet at Scale

[Chapter 4](#ch4) introduced Fleet as the agent management plane; at production scale it becomes an ingestion architecture with its own sizing and failure questions. **Fleet Servers** scale horizontally (one per region or cluster, behind your load balancer) and are stateless against Elasticsearch - the agents hold enrollment keys per policy, check in on schedule, and pull policy revisions; a Fleet Server outage pauses *management*, not *collection*, because agents keep collecting under their last known policy. The upgrade path is the feature to appreciate in year two: agent versions roll out as a Fleet-managed, policy-scoped, rate-limited operation with automatic rollback on failure - which converts "upgrade four hundred shippers" from a quarter's project into a maintenance-window button.

The integration catalog deserves a strategy, not just browsing. Integrations bring schemas (ECS-mapped fields, [Chapter 5](#ch5)), dashboards, and prebuilt detection or alerting rules with them - the difference between "we have Nginx logs" and "we have the Nginx integration" is visible in Kibana within minutes. Two practices keep the fleet sane at scale: one policy per environment-and-role boundary (production-web, production-db, staging-all) rather than one giant policy, so blast radius of a policy change is bounded; and custom log inputs shipping into your own data-stream naming convention (`logs-custom.<app>-default`) when an integration does not exist, keeping custom data eligible for the same ILM and security machinery as first-party data.

## 14.3 APM and Tracing

**Application Performance Monitoring** is the stack's answer to the trace signal from [Chapter 1](#ch1): requests are traced across service boundaries, spans aggregate into latency percentiles, error rates, and dependency maps, and the whole lands in Elasticsearch indices that Kibana's APM app renders as service inventories, per-transaction waterfalls, and correlation views - the "which hop added 800 milliseconds" question answered visually.

The ingestion architecture consolidated in recent versions: **OpenTelemetry** is the recommended instrumentation path - OTel SDKs (or auto-instrumentation agents for Java, Node, Python, Go, .NET) emit OTLP to an **OpenTelemetry Collector**, which exports into the stack - while Elastic's own APM agents and the Elastic Agent's APM integration remain the batteries-included alternative for teams already standardized on the Elastic toolchain. Either way the data model converges: traces, spans, and metrics in ECS-shaped indices, where the same Query DSL, ES|QL ([Chapter 8](#ch8)), and dashboards of this book query them - and where the correlation that makes APM valuable lives: from an error-rate alert, to the slow transactions behind it, to the exact log lines around the failing span, in one UI chain.

APM's operational cost is the honest part of the conversation: traced traffic is *high-cardinality* ingest - per-request documents - and the sampling strategy (head-based at the SDK, tail-based at a collector) is a cost lever with user-visible consequences. Start with conservative sampling (10% or lower on high-traffic services), protect the APM indices with their own ILM policy ([Chapter 10](#ch10)), and let the error *counts* - cheap, unsampled - be what alerting keys on.

## 14.4 Alerting in Kibana

Kibana ships its own alerting engine - rules that run queries on a schedule and connectors that deliver notifications - and it is the natural home for alerts whose logic is a *search* rather than a metric: "more than 50 documents matching this error filter in 15 minutes," "any new value appears in `error.signature`," "a log-based SLI drops below threshold." A rule is a saved query plus a condition plus a schedule; a **connector** is a delivery channel - email, Slack, webhooks, PagerDuty, and generic HTTP - shared across rules; an **action** fires when the rule transitions to alerting, with variables interpolated from the matched documents.

```text
# Rule skeleton (Alerts → Create rule → Log threshold)
WHEN   count of documents in logs-nginx-*
WHERE  http.response.status_code >= 500
GROUP  BY service.name, url.path
IS     ABOVE 50
FOR    the last 15 minutes, checked every 5 minutes
THEN   notify Slack via connector #oncall, with the top documents attached
```

The design conversation this book's readers will recognize from the metrics volume's alerting chapter applies unchanged: alert on *symptoms users feel* (error counts, latency, absence of data) rather than causes; attach the query that fired so the first response action is one click from the evidence; and route by ownership - group-by fields in the rule, per-team connectors, and the severity ladder (warning at threshold, critical at twice threshold) that keeps pages meaningful. The two alerting systems - Kibana's and Prometheus's (Alertmanager) - coexist cleanly in dual-stack estates: metrics-based alerts stay with Prometheus rules where their dashboards live; search-based alerts (and anything needing document context) live here, with [Chapter 12](#ch12)'s API keys scoped so alerting rules read only what they must.

## 14.5 The Bridge to Grafana

Estates that run Prometheus for metrics - the subject of this series' companion volume, *Prometheus & Grafana for DevOps Engineers* - frequently ask whether Grafana can sit on Elasticsearch too, and the answer is a matter-of-fact yes: Grafana ships an **Elasticsearch data source** speaking the Query DSL, with aggregation queries (terms, date_histogram, filters) mapping onto Grafana panels, template variables over keyword fields, and the log context view wired to raw documents. The division of labor that has settled out in dual-stack teams is the one this book has argued since [Chapter 1](#ch1): Grafana remains the metrics cockpit (Prometheus first), and Elasticsearch-backed panels add *search-derived series* to the same walls - error counts by service from logs next to request rates from metrics, one time range, one look.

The companion volume covers the Grafana side - data source configuration, panel types, variable design - so this book contributes only the Elasticsearch-side checklist: create a dedicated read-only role for Grafana (`view_index_metadata` + `read` on the target patterns, per [Chapter 12](#ch12)), use an API key with expiration rather than a shared password, and keep the data view patterns narrow (`logs-nginx-*`, not `logs-*`) so dashboards fail loudly on rename instead of silently charting nothing. Teams that run both stacks under one roof usually conclude within a quarter that each tool's native alerting is stronger in its own signal, and standardize on that split.

## 14.6 A Production Checklist

The chapters of Part II compress to a page of binary questions, and a cluster that answers all of them *yes* is run, not merely hosted:

- **Lifecycle**: every log and metric stream under ILM ([Chapter 10](#ch10)); rollover by size; retention documented per stream; disk headroom monitored against watermarks ([Chapter 11](#ch11)).
- **Capacity**: shards 20-50 GB; per-node shard counts in the hundreds; heap ≤ half of RAM and ≤ ~31 GB; recovery throttles reviewed.
- **Security**: TLS on both layers; no shared superuser; roles in version control; one API key per writer, expiring; negative tests in the change process ([Chapter 12](#ch12)).
- **Backup**: SLM policies with retention; repository verified; restore drill on the calendar and its results recorded ([Chapter 13](#ch13)).
- **Ingestion**: agents enrolled via configuration management; Fleet Servers redundant; per-agent keys revocable; integration schemas preferred over custom mappings ([Chapter 4](#ch4)).
- **Observing the observer**: stack metrics alerting externally ([Chapter 11](#ch11)); SLM and ILM failure alerts; Kibana availability checked like any other production service.
- **Change management**: manifests in Git ([Chapter 14](#ch14)); upgrades rolling and rehearsed; breaking-changes release notes read before, not after ([Chapter 1](#ch1)).

::: {.warn}
**Watch out - the checklist is the floor, not the ceiling**

Every item above prevents a specific, named incident this book has seen; none of them proves the *data* is useful, the dashboards are read, or the alerts are actionable. The floor keeps the platform alive; the ceiling - queries that answer real questions, the discipline of [Chapter 9](#ch9)'s design and the triage flow of [Chapter 8](#ch8) - is what makes keeping it alive worth the cost.
:::

**See also:** the appendices - the [API quick reference](#appA), the [starter configurations](#appB) that put this book's examples into files, and the [troubleshooting guide](#appC) for the day something on the checklist fails anyway.
