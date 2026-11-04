# Chapter 8 - Packaging and Releases: Helm 4 and Kustomize {#ch8}

By now a realistic service is a folder of YAML: `Deployment`, `Service`, `ConfigMap`, `HPA`, and a `Gateway` route, with small per-environment differences in image tags, `replicas`, and endpoints. Copying that folder by hand is how drift is born. Packaging tools solve it in two philosophies: Helm treats your stack as a versioned package with templates and a release lifecycle, while Kustomize patches a base with overlays and ships inside `kubectl`. This chapter covers both honestly, because real estates run Helm for third-party software and Kustomize or plain manifests for first-party services, and you will maintain all of them.

## 8.1 Helm 4: Packages with a Lifecycle

Helm packages manifests into charts, parameterizes them through values files, and records each installation as a named release with revision history, which is what turns upgrade and rollback into first-class operations: `helm upgrade --install api myorg/api -f values-prod.yaml` does the right thing whether release `api` exists or not, and `helm rollback api` returns to the previous revision using history Helm stored itself. A chart's templates are Go templates over the values; start from the structure of a well-maintained chart rather than from an empty directory, because conventions like named templates, helpers, and `NOTES.txt` are load-bearing in the charts you will inherit.

Helm 4, the current major since late 2025, changes two fundamentals you should understand even if your charts barely change. `Install` and `upgrade` now use server-side apply by default, so Helm records field ownership the way Chapter 5 described and three-way merges handle out-of-band edits predictably; the upgrade path from Helm 3 is designed to be low-risk, but read the migration notes before touching shared clusters. Plugin authors gain a WASM runtime as the preferred extension model, and the new `kstatus`-based waiting makes `helm upgrade`'s readiness checks consistent with what `kubectl` sees. None of this changes the values workflow; it changes what happens under the release machinery, which matters exactly when a release is half-applied and someone asks why.

```bash
# install the Prometheus stack you will use in Chapter 12
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --version 62.7.0 -f monitoring-values.yaml

# everyday verbs
helm list -n monitoring
helm get values monitoring -n monitoring
helm history monitoring -n monitoring
helm rollback monitoring 1 -n monitoring
```

## 8.2 Kustomize: Overlays Without Templates

Kustomize takes plain manifests as the base and applies declarative patches per environment, no templating language involved. A `kustomization.yaml` names `resources` and transformations: `images` sets new tags, `replicas` adjusts counts, `patches` modify fields by selector, and `configMapGenerator` creates hashed `ConfigMaps` whose name changes force the `Pod` template to update, giving you restart-on-config-change for free. Overlays layer environments over the base: `overlays/prod` names the base plus prod patches, and `kubectl apply -k overlays/prod` builds and applies it in one step, since Kustomize is built into `kubectl`. The philosophy is visible YAML: every difference between environments is a patch you can read, not a conditional buried in a template.

```yaml
# base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
images:
  - { name: myorg/api, newTag: 1.4.0 }
---
# overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [ ../../base ]
patches:
  - path: prod-patch.yaml
    target: { kind: Deployment, name: api }
replicas:
  - { name: api, count: 5 }
# build without applying:
#   kubectl kustomize overlays/prod
# apply directly:
#   kubectl apply -k overlays/prod
```

## 8.3 Choosing Between Them

The tools answer different questions, and most estates use both. Helm is strongest when a third party publishes and versions the software, when parameterization is genuinely complex, or when you want release history and rollback managed for you; it is the packaging standard for databases, monitoring, and ingress controllers. Kustomize is strongest for first-party manifests that already exist, teams that refuse templating in reviews, and differences that are genuinely small and structural. The antipattern to avoid is both at once on the same objects: Helm applying a release that Kustomize also patches is a field-ownership conflict of exactly the kind server-side apply was built to detect, and the detector will be your pager.

| Aspect | Helm 4 | Kustomize |
| ------------- | ------------------- | ------------------ |
| Model | Templated chart packaged and versioned | Plain YAML base + declarative patches |
| Lifecycle | Releases, history, rollback, hooks | None; state lives in the cluster and `git` |
| Third-party charts | Native: install and upgrade products | Possible but awkward; charts are Helm's home |
| Learning curve | Template language + chart conventions | Small; YAML in, YAML out |
| Best fit | Products, complex parameterization, rollbacks | First-party services, small env differences |

: Table 8.1 - Helm and Kustomize compared

::: {.note}
**Best practice**

Pin everything: chart versions in the `helm` command or `Chart.lock`, image digests for release builds as the Docker book recommended, and values files per environment with names that say what they are. Upgrades are then a pull request that changes one line, reviewable by someone who was not awake at 3 a.m. when the last one shipped.
:::

**See also:** [Chapter 4](#ch4) for the objects Helm renders, [Chapter 13](#ch13) for the GitOps flow that deploys them, and [Chapter 14](#ch14) for upgrades and rollbacks in production.
