# Chapter 13 - Monitoring Kubernetes with Prometheus {#ch13}

## 13.1 What Needs Monitoring in a Kubernetes Cluster

A Kubernetes cluster emits telemetry from four distinct layers, and a complete monitoring story touches all of them. **Nodes**: kernel and hardware metrics via node_exporter (deployed as a DaemonSet - one per node, service-discovered automatically). **Containers**: per-pod CPU, memory, network via cAdvisor, embedded in the kubelet - the layer [Chapter 4](#ch4) introduced, now provided by the cluster itself. **Kubernetes objects**: desired versus running replicas, pod phases, job completions, PVC capacity - object state that lives in the API server, not in any kernel, exposed by **kube-state-metrics**, a small service that listens to the API and exports it as metrics. **Control plane**: API server latency and error rates, scheduler and controller-manager health, etcd latency and leader changes - the cluster's own availability story. Each layer answers different questions: node metrics explain a slow pod, kube-state-metrics explains a Deployment that will not scale, control-plane metrics explain a cluster where *everything* is inexplicably slow.

The monitoring stack also monitors itself: Prometheus's own health (`up` on its own job), the deadman watchdog ([Chapter 12](#ch12)), and the pipeline's end-to-end liveness. kube-prometheus-stack ships all of this - which is why it is the standard.

## 13.2 The Prometheus Operator Model

The **Prometheus Operator** ([prometheus-operator](https://prometheus-operator.dev/)) turns the configuration files of [Chapter 3](#ch3) and [Chapter 7](#ch7) into Kubernetes custom resources. The CRDs that matter daily:

| CRD | Replaces | What it does |
|---|---|---|
| `Prometheus` | prometheus.yml + deployment | Defines a server: version, replicas, retention, resources, and *which* ServiceMonitors it follows |
| `ServiceMonitor` | scrape_configs (kubernetes_sd) | Selects Services by label; generates the scrape config for their pods' endpoints |
| `PodMonitor` | pod-role scrape configs | Selects Pods directly, for services without a Service |
| `PrometheusRule` | rule_files | Recording and alerting rules, evaluated by the matching Prometheus |
| `Alertmanager` | alertmanager.yml + deployment | Defines an Alertmanager cluster and its configuration |
| `Probe` | blackbox jobs | Synthetic probes against ingress targets |
| `ScrapeConfig` | advanced SD configs | Direct access to the raw scrape config surface |

The key mechanic is **label selection**: a `ServiceMonitor` carries labels (commonly `release: <helm-release>`); a `Prometheus` object declares `serviceMonitorSelector` matching them. A ServiceMonitor that the Prometheus does not select is invisible - and a `namespaceSelector` question ("why does my ServiceMonitor in namespace X not work?") is the most common first-day failure, followed closely by the release-label mismatch.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: payments
  labels:
    release: kps          # must match the Prometheus's serviceMonitorSelector
spec:
  selector:
    matchLabels:
      app: payments
  namespaceSelector:
    matchNames: [prod]
  endpoints:
    - port: metrics
      interval: 30s
```

The operator compiles this, along with every selected ServiceMonitor, into a generated scrape configuration and reconfigures the running Prometheus - the kubernetes_sd plus relabeling pipeline from [Chapter 7](#ch7), generated and maintained for you.

## 13.3 kube-prometheus-stack: The Standard Install

**kube-prometheus-stack** ([prometheus-community/kube-prometheus-stack](https://github.com/prometheus-community/helm-charts)) is the Helm chart that assembles the operator plus the full telemetry kit: Prometheus (HA pair), Alertmanager (cluster of 3), Grafana with curated dashboards and data source pre-wired, node_exporter DaemonSet, kube-state-metrics, and the default rule library - Kubernetes health alerts ([Kubernetes mixin](https://github.com/kubernetes-monitoring/kubernetes-mixin)) covering node pressure, pod crash loops, certificate expiry, and control-plane health.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kps prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.adminPassword=change-me \
  --set prometheus.prometheusSpec.retention=7d \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=50Gi
```

The `prometheusSpec` values map one-to-one onto concepts you already own: `retention` and storage are [Chapter 2](#ch2)'s TSDB knobs; `serviceMonitorSelector`/`podMonitorSelector` control what the server follows; `remoteWrite` is [Chapter 12](#ch12)'s outbound stream; `replicas: 2` is the HA pattern. The chart's Grafana arrives with the data source pointing at the in-cluster Prometheus and a folder of dashboards (Node, Pods, Workloads) - proof by example of everything [Chapter 10](#ch10) teaches, provisioned from files.

::: {.note}
**Best practice - values.yaml is your config, not the chart's**

Install with a committed `values.yaml` ([Terraform](https://www.terraform.io/) or plain Git, this series' infrastructure volumes), not a chain of `--set` flags. The chart is a platform decision - upgrades change defaults - and your values file is the contract that survives it.
:::

## 13.4 Writing ServiceMonitors, PodMonitors, and Rules for Your Workloads

Onboarding your own workloads is now a label exercise. Deploy the app with a Service exposing a `metrics` port, then apply the ServiceMonitor from [Section 13.2](#ch13) - and the series arrive, labeled with namespace, pod, service, and endpoint. Workloads without Services (batch pods, sidecar-instrumented jobs) use a `PodMonitor` with the same selector shape. The verification loop is operator-native: `kubectl get servicemonitor`, then query `up{namespace="prod", service="payments"}` - and if the target never appears, the diagnosis order is: is the Service's port name matching (`port: metrics` must match the Service's port *name*), does the ServiceMonitor's `release` label match the Prometheus selector, and does the namespaceSelector include the workload's namespace.

Alerts follow via `PrometheusRule`, with the alert design discipline of [Chapter 8](#ch8) unchanged:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: payments-rules
  labels:
    release: kps
spec:
  groups:
    - name: payments.workload
      rules:
        - record: namespace:payments_errors:ratio_rate5m
          expr: |
            sum by (namespace) (rate(http_requests_total{namespace="prod",job="payments",status=~"5.."}[5m]))
            /
            sum by (namespace) (rate(http_requests_total{namespace="prod",job="payments"}[5m]))
        - alert: PaymentsErrorRatioHigh
          expr: namespace:payments_errors:ratio_rate5m > 0.01
          for: 2m
          labels: { severity: critical, team: payments }
          annotations:
            summary: "Payments 5xx ratio {{ $value | humanizePercentage }} in {{ $labels.namespace }}"
            runbook_url: "https://runbooks.example.com/payments-errors"
```

The recording-rule convention ([Chapter 6](#ch6)) carries into the cluster unchanged, and kube-prometheus-stack's own rules are worth reading as worked examples - they are the industry's most-deployed alert library, and their shape (symptom-based, `for`-clauses everywhere, severity-labeled) is the style this book has been teaching.

## 13.5 Dashboards and Alerts for Kubernetes Out of the Box

The chart's Grafana ships the canonical Kubernetes dashboards, and reading them is a crash course in the metric names that matter: **Node Exporter Full** (the community's most-imported dashboard) for node detail; **Kubernetes / Compute Resources / Namespace (Pods)** for per-workload CPU and memory against requests and limits; **Kubernetes / Networking** for cluster network; kube-state-metrics dashboards for deployment and pod lifecycle. The queries they use are the ones you will reach for in ad-hoc diagnosis: container CPU against requests (`rate(container_cpu_usage_seconds_total{container!=""}[5m])` vs `kube_pod_container_resource_requests`), memory working set vs limits (the OOM predictor), `kube_pod_status_phase` counts, `kube_deployment_status_replicas_available` vs desired. These dashboards are provisioned from files - open them, find the JSON ([Chapter 10](#ch10)), and copy the patterns rather than the JSON wholesale.

Two operational additions complete the picture: the **deadman watchdog** rule ships enabled - route it to a healthcheck-integrated receiver ([Chapter 12](#ch12)) so a silent pipeline pages; and dashboard-as-code applies in-cluster exactly as in [Chapter 10](#ch10) - dashboards in ConfigMaps (via the `grafana_dashboard: "1"` sidecar convention) or in the Git Sync repository, never hand-built on a StatefulSet pod's disk.

## 13.6 Lab 5: kube-prometheus-stack on kind

::: {.lab}
### Lab 5 - The full operator stack on a local cluster {#lab5}

1. Create a kind cluster ([Kubernetes in Docker](https://kind.sigs.k8s.io/)), install the chart as in [Section 13.3](#ch13) with a committed `values.yaml`, and verify the pods: two Prometheus replicas, three Alertmanagers, Grafana, node-exporter per node, kube-state-metrics, and the operator.
2. Port-forward to Grafana and explore the pre-provisioned dashboards; find *Node Exporter Full* and *Kubernetes / Compute Resources*; then open the data source page and confirm Prometheus was auto-wired - provisioning ([Chapter 9](#ch9)) doing its job.
3. Deploy a small app with a `metrics` port, onboard it with a ServiceMonitor (mind the `release` label), and verify with `up{service="..."}`. Then break onboarding deliberately: remove the release label, observe the target vanish from the Prometheus targets UI, diagnose from the operator's logs, and restore.
4. Add a PrometheusRule with one recording rule and one alert (a crash-loop or error-ratio alert), verify the series exists, then crash the app until the alert fires; confirm it reaches the in-cluster Alertmanager (port-forward its UI) and appears grouped. Silence it with `amtool` against the in-cluster Alertmanager.
5. Wire the watchdog: find the `Watchdog` alert in the rules UI, create a receiver that would integrate with a healthcheck service, and write down what "silence" means for a deadman switch (answer: never silence it; it exists to detect silence).
6. Tear down and rebuild from `values.yaml` alone. If the rebuild reproduces the monitoring stack - minus deliberately persistent data - the configuration-as-code loop is closed, exactly as it would be in production.
:::

**See also:** [Chapter 12](#ch12) for attaching Thanos sidecars or remote write to this deployment, [Chapter 10](#ch10) for dashboard-as-code in the cluster, and [Chapter 7](#ch7) for what the operator generates underneath every ServiceMonitor.
