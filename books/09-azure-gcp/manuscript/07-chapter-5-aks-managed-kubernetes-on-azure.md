# Chapter 5 - AKS: Managed Kubernetes on Azure {#ch5}

## 5.1 Managed Kubernetes Without the Control-Plane Bill

AKS hands you the same deal as EKS - a managed, etcd-backed control plane, your nodes, your manifests - with one immediately visible difference: the control plane is **free** in the standard base configuration. Where the AWS book budgeted roughly seventy-three dollars a month per cluster just for EKS, AKS charges for nodes, load balancers, and storage, and the paid **Standard tier** exists for the SLA and zone-redundant control plane, not for the API server itself. AKS runs *upstream* Kubernetes with Azure integrations bolted on, follows the standard **N-2 version support policy** with releases every quarter or so, and upgrades must walk through minor versions one at a time - no skipping - with a supported window you track like EOL dates. Creation and kubeconfig are the two commands everything else hangs on:

```bash
az aks create \
  -g rg-shopnow-dev -n aks-shopnow-dev \
  --network-plugin azure --network-plugin-mode overlay \
  --zones 1 2 3 \
  --enable-cluster-autoscaler --min-count 2 --max-count 5 \
  --enable-oidc-issuer --enable-workload-identity \
  --tier free
az aks get-credentials -g rg-shopnow-dev -n aks-shopnow-dev   # writes kubeconfig context
```

The flags to notice now: `--zones` spreads nodes across the AZs of [Chapter 1](#ch1), and the two `--enable-*` flags stand up the OIDC issuer that [Section 5.4](#ch5) turns into pod-level identity - the IRSA pattern of the AWS book, rebuilt in Azure vocabulary.

## 5.2 Node Pools: System, User, and Spot

Each AKS node pool is a VMSS from [Chapter 3](#ch3) wearing a Kubernetes label, and the pool is the unit you manage. The **system pool** hosts the add-on pods every cluster needs (CoreDNS, the ingress controller, metrics) and should be small and boring; **user pools** host your workloads, one pool per resource class, so a memory-hungry service does not fight a CPU-bound batch job for placement. Spot node pools (`--priority Spot --eviction-policy Delete`) give the chapter-on-EC2 spot story a Kubernetes home for batch and stateless work. The cluster autoscaler is enabled per cluster (as above) and tuned per pool, and scaling behavior you configure on the pool - not by editing the VMSS underneath, which the platform owns.

::: {.note}
**Best practice - AKS can stop, and the cheapest dev cluster is a stopped one**

`az aks stop -g rg-shopnow-dev -n aks-shopnow-dev` halts the nodes and their compute charges while keeping the cluster object, config, and state on disk - something EKS has no equivalent for, and the reason overnight-and-weekend dev clusters on Azure are a rounding error. Start it with `az aks start`; keep the habit from the AWS book of distinguishing *stopping for the weekend* from *deleting for real* (`az group delete`).
:::

## 5.3 Networking: Overlay, Egress, and Ingress

AKS networking has a default that deserves a paragraph because it differs from AWS. With **Azure CNI in overlay mode** (the default on new clusters), pods draw IPs from a private pod-CIDR overlaid on the VNet instead of consuming VNet addresses - so a 200-pod deployment does not burn 200 subnet slots, and subnet planning stays boring. (AWS's VPC CNI gives every pod a VNet address; overlay trades that direct reachability for scale, and container networking between clouds is compared properly in [Chapter 15](#ch15).) Egress goes through a managed route - load balancer or, for private clusters, a NAT gateway - and inbound HTTP lands on a Kubernetes `LoadBalancer` service backed by an Azure Load Balancer with an optional static public IP.

For ingress, the managed **Web App Routing** add-on installs and operates an nginx ingress with DNS and optional Key Vault-backed TLS - the shortest path to `https` on AKS; `helm install ingress-nginx` remains the portable alternative and is what the capstone in [Chapter 15](#ch15) uses to keep the three clouds' manifests identical.

## 5.4 Workload Identity: Pods Without Secrets

The AWS book's IRSA chapter has a near-verbatim Azure translation, and learning it once here pays off twice - [Chapter 12](#ch12) repeats the pattern on GKE with different flags and the same shape. With the OIDC issuer enabled, a pod presents its projected service-account token to Entra ID, which trusts it via a **federated credential** attached to a user-assigned managed identity:

```bash
MI_ID=$(az identity create -g rg-shopnow-dev -n mi-shopnow-api --query id -o tsv)
CLIENT_ID=$(az identity show --ids $MI_ID --query clientId -o tsv)

az identity federated-credential create --name fic-shopnow-api \
  --identity-name mi-shopnow-api -g rg-shopnow-dev \
  --issuer $(az aks show -g rg-shopnow-dev -n aks-shopnow-dev --query oidcIssuerProfile.issuerUrl -o tsv) \
  --subject system:serviceaccount:shopnow:shopnow-api \
  --audience api://AzureADTokenExchange

kubectl annotate sa shopnow-api azure.workload.identity/client-id=$CLIENT_ID -n shopnow
kubectl label   ns shopnow azure.workload.identity/use=true   # namespace label enables it for pods
```

The pod then reads Azure resources as the managed identity - blobs with a data-plane role from [Chapter 2](#ch2), Key Vault secrets, the database of [Chapter 4](#ch4) - with no credential anywhere in the manifest or the image. The subject is the K8s service account, exactly as IRSA's trust condition was; the vocabulary changed, the design did not.

## 5.5 Registry and Day Two

Pulling from **ACR** is one attach away - `az aks update -g rg-shopnow-dev -n aks-shopnow-dev --attach-acr acrshopnowdev` - which grants the cluster's kubelet identity the pull role, and `az acr build` (introduced properly in [Chapter 7](#ch7)) fills the image with the pipeline. Day-two operations mirror the EKS chapter: upgrades roll node pools with surge and drain handled by the platform, maintenance windows and `az aks upgrade` version pinning keep it deliberate, and Microsoft Defender for Containers and AKS-managed Guardrails add the policy layer the AWS book left to tools.

## 5.6 Lab 2: Cluster, Identity-Aware Pod, App, Cleanup

::: {.lab}
### Lab 2 - Build AKS, Run shopnow with Workload Identity, Tear It Down {#lab2}

1. Create the registry and the cluster exactly as in [Section 5.1](#ch5), with `--attach-acr` to your `acrshopnowdev` from [Chapter 7](#ch7)'s setup (create it now with `az acr create` if you skipped ahead).
2. Build and push the shopnow API into ACR: `az acr build -r acrshopnowdev -t shopnow/api:v1 .`
3. Wire identity: create `mi-shopnow-api` and the federated credential from [Section 5.4](#ch4), and grant it **Storage Blob Data Contributor** on the dev storage account.
4. Deploy the app: namespace `shopnow`, a service account annotated with the client ID, a Deployment whose pods carry `azure.workload.identity/use: "true"`, and a Service of type `ClusterIP`.
5. Prove the identity: `kubectl exec` into a pod and read a blob from the dev account with the Azure SDK/CLI inside the pod - no credentials, only the federated token, and the access log in the storage account to prove it.
6. Expose it: enable the Web App Routing add-on (`az aks update --enable-webapp-routing`) or install ingress-nginx with Helm, point an Ingress at the Service, and curl the public endpoint.
7. Costs and cleanup: `az aks stop` for the weekend option, and `az group delete -n rg-shopnow-dev -y` for the real one - the cluster, MI, and ACR were all in one group on purpose.
:::

::: {.warn}
**Watch out - version upgrades do not skip minors**

An AKS cluster on 1.28 cannot jump to 1.31: each minor upgrade must land and settle in turn, and support ends two minors after each release, which turns "we'll upgrade next quarter" into two quarters of upgrades. Schedule them like the EKS chapter taught - a maintenance window, a canary pool, and the release-channel discipline of never being the last one on an unsupported version.
:::

**See also:** [Chapter 2](#ch2) supplied the managed-identity mechanics this lab exercised, [Chapter 4](#ch4) owns the network the cluster sits in, [Chapter 7](#ch7) replaces `az acr build` in your terminal with the pipeline, and [Chapter 12](#ch12) repeats the whole pattern on GKE.
