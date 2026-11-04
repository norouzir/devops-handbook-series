# Chapter 7 - EKS: Managed Kubernetes on AWS {#ch7}

## 7.1 What EKS Actually Manages

**EKS** (Elastic Kubernetes Service) runs upstream Kubernetes - not a fork, the same API your `kubectl` already speaks - with AWS operating the control plane and you operating the workloads. Since this series already taught the platform itself in *Kubernetes for DevOps Engineers*, this chapter teaches only what changes when Kubernetes is *on AWS*: which parts AWS takes, which parts you keep, and the AWS-specific wiring (IAM, networking, load balancers, image registries) that a cluster needs to be useful. The control plane AWS runs for you is the etcd-quorum-sensitive, upgrade-sensitive heart: three master nodes across three AZs, patched and version-bumped by AWS, priced as a flat hourly control-plane fee that does not scale with cluster size. What remains yours is the **data plane** - the worker nodes - plus everything the earlier chapters built: the VPC the cluster lives in ([Chapter 4](#ch4)), the SGs around it, and the IAM identities it uses ([Chapter 2](#ch2)).

Version policy is the operational consequence: EKS supports several recent upstream Kubernetes minor versions and requires you to upgrade on a schedule (the console and `aws eks describe-cluster` show each cluster's status and versions). Upgrades are Section 7.7's topic; the working habit is to treat the EKS Kubernetes calendar like a dependency you pin and review, not a surprise.

## 7.2 Creating a Cluster: eksctl and What It Really Builds

The honest way to create a first cluster is `eksctl`, the CLI built for exactly this, because the raw sequence (`aws eks create-cluster` plus a hand-rolled VPC, IAM roles, and networking) is a day of YAML for a first-timer:

```bash
eksctl create cluster \
  --name shopnow \
  --region eu-central-1 \
  --nodegroup-name workers \
  --node-type t4g.medium \
  --nodes 2 --nodes-min 2 --nodes-max 4 \
  --managed
```

Ten minutes later the cluster exists, and the command's real value is what it *created* for you - every piece is something you should be able to name: a dedicated VPC with public and private subnets across AZs (the [Chapter 4](#ch4) layout, unless you pass `--vpc-*` flags to use your own); a control-plane **IAM role**; a **node IAM role** (`AmazonEKSWorkerNodePolicy`, `AmazonEKS_CNI_Policy`, `AmazonEC2ContainerRegistryReadOnly`) that node processes use; a **managed node group** of `t4g.medium` workers in the private subnets; the security groups wiring control plane to nodes; and an **OIDC identity provider** for the cluster - the seed of Section 7.4's pod-level IAM. `aws eks update-kubeconfig --name shopnow` merges the cluster into `~/.kube/config`, and `kubectl get nodes` shows the workers Ready. From here on, it is the Kubernetes you know, with AWS showing through at specific seams.

## 7.3 Data Plane Choices: Managed Node Groups, Self-Managed, Fargate

Three ways to own the worker layer, in increasing order of abstraction. **Managed node groups** are the default and this book's choice: you specify instance type, size, and subnets; AWS provisions, patches (on its own rolling schedule), and drains the ASG-managed nodes, and upgrades respect your PodDisruptionBudgets. **Self-managed nodes** mean you own the ASG and the AMI lifecycle - the path for custom kernels, GPU tuning, or baked images (Packer from [Chapter 3](#ch3)). **Fargate** removes nodes entirely: pods land on AWS-managed micro-VMs, billed per pod-second, with a *Fargate profile* defining which namespaces run there. The decision table:

| Option | You patch | Pods per node | Best for |
| --- | --- | --- | --- |
| Managed node group | nobody (AWS rolls nodes) | many | the default workload |
| Self-managed | you | many | custom nodes, GPU, baked AMIs |
| Fargate | nobody (no nodes) | isolated per pod | bursty batch, strict isolation |

The mature pattern mixes them: node groups for steady services, Fargate for spiky or untrusted workloads, spot-backed node groups (Section 3.7) for the interruptible middle.

## 7.4 Pods with AWS Identities: IRSA

The question "how does a pod call AWS?" has a modern answer: **IRSA** - IAM Roles for Service Accounts. At cluster creation, eksctl registered an **OIDC identity provider** for the cluster; a service account annotated with a role ARN lets pods holding that service account exchange a signed token for temporary AWS credentials, with the trust policy checking the token's namespace and service account. The effect is the [Chapter 2](#ch2) ideal taken to pod granularity: no node-level wildcard permissions, no secrets mounted for AWS access, one role per workload, each auditable:

```bash
eksctl create iamserviceaccount \
  --cluster shopnow --namespace app \
  --name asset-reader \
  --attach-policy-arn arn:aws:iam::111122223333:policy/shopnow-assets-readonly \
  --approve
```

A pod using `serviceAccountName: asset-reader` can call `aws s3 ls s3://shopnow-assets-eu-central-1-prod` with no other configuration - the SDK finds the token, assumes the role, and the trust policy (namespace `app`, service account `asset-reader`) is what made it legal. Every AWS SDK built this decade supports it natively; it is the single most "AWS-native" mechanism in the chapter, and [Chapter 9](#ch9)'s pipeline deploys workloads that depend on exactly this wiring.

## 7.5 Images: ECR and the Pull Path

**ECR** (Elastic Container Registry) is AWS's private Docker registry, and its integration with EKS is mostly a matter of three facts. First, nodes pull from ECR using the node role's `AmazonEC2ContainerRegistryReadOnly` - no per-pod image credentials for private repos in the same account. Second, CI pushes to ECR with a token minted from the pipeline's role ([Chapter 9](#ch9) does it with OIDC):

```bash
aws ecr get-login-password --region eu-central-1 \
  | docker login --username AWS --password-stdin 111122223333.dkr.ecr.eu-central-1.amazonaws.com
docker tag shopnow:1.4.2 111122223333.dkr.ecr.eu-central-1.amazonaws.com/shopnow:1.4.2
docker push 111122223333.dkr.ecr.eu-central-1.amazonaws.com/shopnow:1.4.2
```

Third, repos need **lifecycle policies** or they accumulate every layer ever pushed - the S3 bucket problem of Section 5.3 in container form (`aws ecr put-lifecycle-policy` keeping the last N untagged images is the standard rule). Graviton nodes need arm64 images: the build stage sets `--platform linux/arm64` (or builds natively on Graviton runners), and the mismatch - an amd64 image on arm64 nodes - is a classic "exec format error" with a one-line fix.

## 7.6 Load Balancing: The AWS Load Balancer Controller

Kubernetes on AWS gets its ingress from an operator: the **AWS Load Balancer Controller** watches `Ingress` and `Service` objects and provisions real AWS load balancers - an **ALB** per Ingress (or shared across Ingresses via groups) and an **NLB** for raw TCP/UDP Services. Install it once per cluster (Helm, with IRSA for its own identity), then the YAML is portable and the AWS resources appear:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shopnow
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
spec:
  ingressClassName: alb
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: shopnow-web
                port: { number: 80 }
```

Two annotations carry the meaning: `internet-facing` puts the ALB in the public subnets (an `internal` scheme serves traffic from inside the VPC only), and `target-type: ip` routes the ALB directly to pod IPs (the VPC CNI gives every pod a real VPC address - a defining AWS-Kubernetes fact worth knowing) instead of through NodePorts. The controller also wires ACM TLS certificates, so the HTTPS story is an annotation, not a project.

## 7.7 Upgrades Without Drama

EKS upgrades are controlled by you and follow a fixed order: upgrade the **control plane** (one minor version at a time; AWS manages the rollout), then update each **add-on** (CNI, CoreDNS, kube-proxy - managed add-ons make this one flag), then roll the **node groups** to the new node AMI version, then your workloads. The rehearsal discipline from the Kubernetes book applies unchanged and is the difference between an upgrade and an incident: staging first, PodDisruptionBudgets so drains evict politely, and *stateful sets checked before stateless ones*. Node group rolling updates - two new nodes up, old ones drained and terminated - need the PDBs to have somewhere to put the pods; the most common upgrade failure is not Kubernetes at all, it is a workload with `replicas: 1` and no PDB that cannot tolerate its own eviction.

## 7.8 Lab 4: Cluster, App, IAM-Enabled Pod, Cleanup

::: {.lab}
### Lab 4 - EKS End to End {#lab4}

1. Install `eksctl` and `kubectl`, then create the Section 7.2 cluster (two Graviton nodes, min/max for autoscaling). Confirm `kubectl get nodes` shows two `Ready` nodes and inspect what eksctl created: `aws eks list-clusters`, the new VPC's subnets, and the two IAM roles.
2. Build and push an image: a tiny nginx-based page or the [Chapter 3](#ch3) bootstrap content, built for `linux/arm64`, pushed to a new ECR repository. Add a repository lifecycle policy keeping the last five untagged images.
3. Deploy: a `Deployment` (2 replicas) plus `Service`, then the Section 7.6 `Ingress`. Install the AWS Load Balancer Controller first (Helm; its IAM service account via IRSA). Wait for the ALB's DNS name in `kubectl get ingress` and curl it.
4. IRSA proof: create the `asset-reader` service account of Section 7.4 attached to a policy that reads your [Chapter 5](#ch5) bucket, run a one-off pod (`kubectl run -it --rm aws-cli --image=amazon/aws-cli --serviceaccount=asset-reader -- s3 ls s3://<your-bucket>`), and confirm it lists the bucket. Run the same pod with the default service account and confirm it is denied - the negative test is the lesson.
5. Scale test: `kubectl scale deployment shopnow-web --replicas=5`, watch the node group react (or not, with room to spare), then scale back.
6. Cleanup in the right order: delete the Ingress and Service first (the ALB is the bill line), delete the iamserviceaccount, then `eksctl delete cluster --name shopnow`. Verify with `aws elbv2 describe-load-balancers` that nothing was orphaned.

Deliverable: a script that creates a working Kubernetes platform on AWS - cluster, image, ALB-served app, pod-level IAM - and deletes it completely, in two commands each way.
:::

**See also:** [Chapter 9](#ch9) automates steps 2-3 into a GitHub Actions pipeline with OIDC, [Chapter 10](#ch10) watches the cluster's control plane and workload metrics, and [Chapter 11](#ch11) turns the eksctl incantation into reviewed Terraform. The Kubernetes mechanics assumed here - Deployments, Services, PDBs - are the *Kubernetes for DevOps Engineers* volume's territory.
