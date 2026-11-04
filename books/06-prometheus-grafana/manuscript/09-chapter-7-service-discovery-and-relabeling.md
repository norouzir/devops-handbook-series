# Chapter 7 - Service Discovery and Relabeling {#ch7}

## 7.1 The Pipeline: Discover, Relabel, Scrape, Relabel Again

Static target lists break the moment targets start moving - autoscaling groups, Kubernetes pods, DNS round-robins. Service discovery (SD) makes Prometheus *ask* where the targets are, and relabeling is the language in which every target decision is expressed. The mental model that makes the whole chapter simple is one pipeline applied to every scrape configuration:

```
SD mechanisms  →  targets with __meta_* labels  →  relabel_configs
               →  final scrape targets          →  scrape
               →  samples with target labels    →  metric_relabel_configs
               →  stored series
```

**Discovery** produces candidate targets, each carrying `__meta_*` labels describing where it came from (pod name, node, availability zone, tags). **`relabel_configs`** run *before* the scrape and decide the target's fate: rewrite its address, add or remove labels that will attach to its samples, or drop it entirely. The scrape runs, and **`metric_relabel_configs`** run *after* - per-sample, with the metric in hand - deciding which series to keep, rewrite, or drop. Two relabeling stages, one syntax, different moments: target decisions before, sample decisions after. Labels beginning with `__` (double underscore) are internal, removed after relabeling, and never stored.

## 7.2 static_configs, file_sd, and DNS

Not everything needs a discovery system. `static_configs` from [Chapter 3](#ch3) is fine for a handful of long-lived endpoints; the next step up is `file_sd`, which reads target lists from JSON or YAML files and *watches them for changes*:

```yaml
scrape_configs:
  - job_name: node
    file_sd_configs:
      - files:
          - /etc/prometheus/targets/node/*.yml
        refresh_interval: 30s
```

```yaml
# /etc/prometheus/targets/node/web.yml
- targets:
    - web-01.example.com:9100
    - web-02.example.com:9100
  labels:
    env: prod
    role: web
```

file_sd is the lowest-friction answer to "some targets come from a system with no API": a config-management tool ([Ansible](https://www.ansible.com/) style or otherwise) writes the files, Prometheus follows along. `dns_sd_configs` adds the record-based variant - SRV records for services that publish themselves in DNS, with ports and instance identity carried by the records. Both mechanisms keep the pipeline mental model intact: they are just the first box, producing targets with fewer `__meta_*` labels than the big discovery systems.

## 7.3 Relabeling Mechanics: The Four Fields and the Actions

Every relabeling rule has the same shape, and learning it once covers both stages forever:

```yaml
- source_labels: [__meta_kubernetes_pod_label_app]
  separator: ";"           # how multiple source labels are joined (default ";")
  regex: "(.*)"            # RE2, fully anchored
  target_label: app        # destination for the replacement
  replacement: "$1"        # may reference regex groups
  action: replace          # the default action
```

`replace` copies and transforms; the other actions read differently. `keep` and `drop` filter by regex match on the concatenated source labels - the workhorses of target selection. `hashmod` shards: hash the source labels modulo N into a target label, the standard pattern for splitting a fleet across multiple Prometheus servers. `labelmap` copies labels matching a regex wholesale (`__meta_kubernetes_pod_label_(.+)` → the captured name), the one-liner that ingests pod labels as metric labels. `labeldrop`/`labelkeep` remove matching labels from the set. Every mechanism from this chapter onward - Kubernetes pod selection, blackbox probing from [Chapter 4](#ch4), Thanos sharding in [Chapter 12](#ch12) - is expressed in exactly this vocabulary.

::: {.note}
**Best practice - relabel to decisions, not to decoration**

Every relabeling rule is a decision someone must maintain. Prefer the rules that *filter* (`keep`, `drop`) and the handful that *map* metadata (`labelmap`, one or two `replace`s per job); resist building label empires in relabel_configs, because every label added at scrape time is cardinality paid at storage time ([Chapter 2](#ch2)). The question each rule must answer: what decision does this enable that the target's own labels do not?
:::

## 7.4 Kubernetes Service Discovery

`kubernetes_sd_configs` is the discovery mechanism most readers will run in production, and its design is roles: the role declares *what kind of thing* is a target. The two roles that matter most:

**`role: pod`** discovers every pod, with `__meta_*` labels for namespace, pod name, node, and - crucially - every pod label and annotation, projected as `__meta_kubernetes_pod_label_<name>` and `__meta_kubernetes_pod_annotation_<name>`. The standard pattern turns pod annotations into scrape decisions: a pod annotated `prometheus.io/scrape: "true"` with a port annotation is scraped, everything else is dropped:

```yaml
- job_name: kubernetes-pods
  kubernetes_sd_configs:
    - role: pod
  relabel_configs:
    - action: keep
      source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
      regex: "true"
    - action: replace
      source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_port]
      target_label: __address__
      regex: "(.+)"
      replacement: "${1}"
    - source_labels: [__address__]
      regex: "(.*):\\d+"
      target_label: __address__
      replacement: "${1}:${2}"   # host from address + annotated port
    - source_labels: [__meta_kubernetes_namespace]
      target_label: namespace
    - source_labels: [__meta_kubernetes_pod_name]
      target_label: pod
```

**`role: service`** and **`role: endpoints`/`endpointslice`** discover Services and their backing endpoints - the path the Prometheus Operator takes ([Chapter 13](#ch13)) when a ServiceMonitor selects a Service. The node role discovers kubelets for cAdvisor and kubelet metrics. In all cases the pipeline is identical: discovery yields candidates with `__meta_*` labels, relabeling selects and renames, the scrape happens with `job` and `instance` plus the labels you kept. [Chapter 13](#ch13) shows why operator-managed `ServiceMonitor` objects are the day-to-day interface - but every ServiceMonitor compiles down to exactly the relabeling above, and reading it fluently is what debugging in a real cluster requires.

## 7.5 The Broader Discovery Landscape and Scrape Tuning

The same `*_sd_configs` pattern extends to every platform a fleet might live on: `consul_sd_configs` for Consul service catalogs, `http_sd_configs` for "our own tool serves a JSON target list" (the universal escape hatch), and the cloud roles - EC2, GCE, Azure, DigitalOcean, Hetzner, and friends - for instances tagged into existence. Choosing among them is not a religion: file_sd when something else already knows the targets, http_sd when you own the inventory, the platform SD when the platform is the source of truth.

Per-job tuning knobs complete the picture. `scrape_interval` and `scrape_timeout` may be overridden per job (timeout must be shorter than interval); `metrics_path` changes the endpoint; `scheme` selects http/https; `honor_labels` decides whether the target's own `job`/`instance` labels win over Prometheus's (default: Prometheus wins, target labels are prefixed `exported_`) - the blackbox job from [Chapter 4](#ch4) leaned on `honor_labels: true` semantics to preserve the probed URL as `instance`. And `sample_limit` per target is the guardrail that turns a cardinality accident ([Chapter 4](#ch4)) from a server-wide outage into a single target's scrape error.

## 7.6 metric_relabel_configs: The Second Gate

Where `relabel_configs` decide *whether to scrape*, `metric_relabel_configs` decide *what to store*, sample by sample, after the scrape returns. The two standard uses both show up as one-liners:

```yaml
metric_relabel_configs:
  # drop the chatty-but-useless families, by name
  - source_labels: [__name__]
    regex: "go_(gc|memstats|threads|info)_.*"
    action: drop
  # rewrite a high-cardinality label into a bounded one
  - source_labels: [le]
    regex: "\\+(inf|[0-9]+)\\.[0-9]+"
    target_label: le
    replacement: "${1}"
    action: replace
```

Dropping by `__name__` is the routine diet for Go runtime internals and other families you will never graph. Rewriting is rarer - the `le` normalization above is a real histogram case - and the action set is the same as the first stage. One boundary matters: metric relabeling cannot see scrape health (`up` is generated after) and cannot reduce *target* count, only series count. When the goal is fewer targets, relabel before the scrape; when the goal is fewer series, relabel after.

::: {.warn}
**Watch out - dropping after scraping is still expensive**

`metric_relabel_configs` prevents storage cost, not scrape cost: the bytes still cross the network and get parsed. A target emitting 500k series that you drop all of still costs 500k series of scrape every interval. For "never wanted it at all", the fix is at the source (instrumentation flags, exporter collectors - [Chapter 4](#ch4)) or at target selection (first-stage relabeling). Metric relabeling is the mop, not the plumber.
:::

## 7.7 Drill: A Fleet Under Discovery

::: {.lab}
### Drill 1 - Relabeling drill (companion to [Lab 2](#lab2)) {#drill1}

1. Convert the stack's node job from `static_configs` to `file_sd`, move the target into `targets/node.yml`, and prove hot reload: change the file, watch the Targets page update without touching `prometheus.yml`.
2. Add pod-style annotations to a blackbox job: keep only targets whose `__address__` matches a name regex, and map an environment label from the target file. Confirm the Targets page shows the filtered set and the new label on samples.
3. Write a `hashmod` rule (`__address__` mod 2 → `prometheus_shard`) and query `count by (prometheus_shard) (up)` to see the distribution - the exact pattern [Chapter 12](#ch12) uses for horizontal sharding.
4. Add `metric_relabel_configs` dropping `go_*` families from one job; verify with `count by (__name__) ({job="node"})` before and after, and note the series-count delta on the TSDB status page.
5. Set `sample_limit: 1000` on the node job and confirm a violation surfaces as a target error ("exceeded label count/sample limit") rather than silent truncation - then right-size the limit with data.
:::

**See also:** [Chapter 8](#ch8) for the alerts this pipeline feeds, [Chapter 12](#ch12) for hashmod sharding at scale, and [Chapter 13](#ch13) for the operator objects that generate this YAML for you.
