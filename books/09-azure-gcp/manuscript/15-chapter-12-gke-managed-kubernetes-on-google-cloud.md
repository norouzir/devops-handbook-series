# Chapter 12 - GKE: Managed Kubernetes on Google Cloud {#ch12}

## 12.1 The Home Team, Two Ways

Google invented Kubernetes and runs the largest Kubernetes fleet in existence, and GKE's two operating modes express that confidence. **Autopilot** is the managed everything: you deploy pods, Google runs the nodes - provisioning, scaling, patching, and hardening them - and billing follows *pod resources requested*, with an SLA per pod rather than per machine. **Standard** is the classic mode: node pools of real machines ([Chapter 10](#ch10) instances in Kubernetes clothing), full control over kernels, DaemonSets, GPUs, and cost, full responsibility for the same. This book defaults to Autopilot for the same reasons the series defaults to managed everything: the workloads shopnow runs gain nothing from node ownership, and Autopilot's enforced pod `requests`/`limits` - the platform refuses pods without them - quietly implements the right-sizing discipline the AWS book had to teach. Standard earns its keep when a workload needs kernel-level tuning, GPU scheduling, Windows nodes, or DaemonSets on every machine.

Clusters are **regional by default** - the control plane replicates across three zones, nodes spread with it - and versioning follows **release channels**: subscribe to `regular` and the cluster tracks the current stable minor with automatic patching, the managed answer to the upgrade-calendar problem both previous clouds left to you:

```bash
gcloud container clusters create-auto gke-shopnow-dev \
  --region=europe-west3 \
  --release-channel=regular

gcloud container clusters list
gcloud container clusters get-credentials gke-shopnow-dev --region=europe-west3
```

::: {.warn}
**Watch out - the illustration above is a pattern, not a flag list**

GKE ships more cluster-level toggles than any two other managed Kubernetes platforms combined, and the flags change with every release; this book pins the *shape* of the command (`create-auto`, a region, a release channel) and leaves the flag surface to `gcloud container clusters create-auto --help` in your shell - the moving-detail discipline the series has applied to every versioned surface. The kubeconfig step, by contrast, has been stable for a decade and is yours to memorize.
:::

## 12.2 Workload Identity: The Canonical Implementation

GCP's **Workload Identity for GKE** is the original of the pattern [Chapter 5](#ch5) rebuilt on Azure: a Kubernetes service account, annotated with the Google service account it should act as, whose projected token GKE exchanges for Google credentials without any key anywhere. The setup is three commands and one annotation, and it is the flow [Lab 4](#ch12) exercises end to end:

```bash
# 1. The Google-side identity with its permissions (created in Chapter 9 style)
gcloud iam service-accounts create sa-shopnow-api-gke
gcloud storage buckets add-iam-policy-binding gs://shopnow-assets-eu \
  --member="serviceAccount:sa-shopnow-api-gke@shopnow-dev-eu.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# 2. The binding: this K8s SA may act as this Google SA
gcloud iam service-accounts add-iam-policy-binding \
  sa-shopnow-api-gke@shopnow-dev-eu.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:shopnow-dev-eu.svc.id.goog[shopnow/shopnow-api]"

# 3. The annotation on the Kubernetes service account
kubectl -n shopnow annotate sa shopnow-api \
  iam.gke.io/gcp-service-account=sa-shopnow-api-gke@shopnow-dev-eu.iam.gserviceaccount.com
```

Workload Identity is enabled by default on Autopilot; on Standard clusters it is the `--workload-pool=PROJECT.svc.id.goog` cluster flag plus per-node-pool opt-in. The pod side needs nothing but the annotated service account in its spec - the SDK in the container picks up credentials from the metadata path, exactly as the AKS pod did with its federated credential, and the two implementations differ by annotation syntax and nothing else.

## 12.3 Exposure: Gateway, Ingress, and the Google Load Balancer

GKE's edge story is its own: Services of type `LoadBalancer` become regional load balancers, and the **Gateway API** - the standard Kubernetes evolved past Ingress, with GKE as its flagship implementation - provisions Google Cloud's load balancers directly: the `gke-l7-global-external-managed` GatewayClass fronts the cluster with the anycast global load balancer of [Chapter 10](#ch10), managed TLS certificates attach to Gateway listeners, and container-native load balancing (NEGs) targets pods, not nodes. For shopnow, a Gateway plus one HTTPRoute replaces the ingress resources of Part I - and because Gateway is a Kubernetes standard, the manifest shape stays portable across the three clouds even when the implementation classes differ (a point [Chapter 15](#ch15) exploits).

## 12.4 Day Two: Upgrades, Cost, and Policy

Day two on GKE is quieter than on any platform this series has covered, and the reasons are worth naming. Upgrades arrive through the release channel and roll with maintenance windows and exclusions you set (`gcloud container clusters update --maintenance-window`). Cost has two dials: Autopilot bills the pod resources you request, so right-sized requests are a *billing* control and not just a scheduling hint, and **Committed Use Discounts** cut the steady-state bill the way Savings Plans did on AWS. The policy layer - Binary Authorization for image provenance, GKE security postures for workload configuration - covers the supply-chain story the AWS book delegated to tools, and **Backup for GKE** rounds out the state story for the cluster's own objects.

## 12.5 Lab 4: Autopilot, Identity, and the App

::: {.lab}
### Lab 4 - Autopilot Cluster, Identity-Aware Pods, Cleanup {#lab4}

1. Create the cluster and its kubeconfig: `gcloud container clusters create-auto gke-shopnow-dev --region=europe-west3 --release-channel=regular`, then `gcloud container clusters get-credentials`.
2. Build and push the app: `gcloud auth configure-docker europe-west3-docker.pkg.dev`, then `gcloud builds submit --tag europe-west3-docker.pkg.dev/shopnow-dev-eu/shopnow/api:v1 .` - Cloud Build builds in-region, no local Docker required.
3. Identity: create `sa-shopnow-api-gke` with `roles/storage.objectViewer` on the assets bucket and `roles/cloudsql.client` on the database from [Chapter 11](#ch11); add the WIF binding and the Kubernetes service-account annotation from [Section 12.2](#ch12).
4. Deploy shopnow: namespace `shopnow`, the annotated service account, a Deployment (with honest `requests`, or Autopilot will reject the pod - read the event), and a Service.
5. Expose with Gateway: create a Gateway (`gatewayClass: gke-l7-global-external-managed`) and an HTTPRoute to the Service; wait for the managed certificate, then curl the address.
6. Prove identity: `kubectl exec` into a pod and list the assets bucket with the Google SDK - no key material anywhere, the audit log on the bucket proving which SA read it.
7. Delete it all: `gcloud container clusters delete gke-shopnow-dev --region=europe-west3` - and note that the regional cluster's goodbye takes a few minutes and leaves nothing behind.
:::

::: {.note}
**Best practice - Autopilot makes right-sizing a billing control, so let it**

On Standard fleets, pod requests are a scheduling fiction teams over-provision for safety; on Autopilot they are the invoice. That inversion is the feature: measure real usage for a week, set requests to the p90, and the cluster's bill follows the truth instead of the anxiety - the same conversation as the right-sizing chapters of the AWS and Azure volumes, settled by the platform's pricing model instead of by meetings.
:::

**See also:** [Chapter 5](#ch5) is the AKS twin of this chapter's identity and exposure story, [Chapter 9](#ch9) owns the service-account model, [Chapter 13](#ch13) runs the same app without a cluster at all, and [Chapter 14](#ch14) wires the pipeline that deploys here.
