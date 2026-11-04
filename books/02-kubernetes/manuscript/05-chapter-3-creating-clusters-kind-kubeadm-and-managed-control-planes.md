# Chapter 3 - Creating Clusters: kind, kubeadm, and Managed Control Planes {#ch3}

There is no single way to run Kubernetes, and pretending otherwise produces bad decisions. A developer iterating on manifests wants a cluster that boots in seconds; an operations team wants a cluster whose control plane they control and can recover; a small team without platform engineers wants someone else to carry the pager for `etcd`. This chapter covers the three honest options, learning clusters with `kind`, self-managed production clusters with `kubeadm`, and managed control planes from cloud providers, and closes with the `kubeconfig` file that lets one `kubectl` speak to all of them.

## 3.1 Choosing the Right Environment

The choice is about who carries which risk. `kind` runs Kubernetes-in-Docker: each node is a container, so clusters are disposable and perfect for tests, CI, and this book's labs. `minikube` serves the same purpose with more drivers and built-in add-ons. `kubeadm` produces a real, self-managed cluster on Linux machines you own, the environment where everything in this book is true without abstraction. Managed control planes, EKS on AWS, GKE on Google Cloud, AKS on Azure, take the control plane off your hands; you operate worker nodes, the API version, and everything above, but you never touch `etcd`. Chapter 2's anatomy still applies everywhere; only the responsibility line moves.

| Environment | Best for | Control plane | You still own |
| ---------- | --------------- | ------------ | ------------- |
| `kind` / `minikube` | Learning, tests, CI pipelines | Runs as containers on your host | Nothing; clusters are disposable |
| `kubeadm` | Self-managed production on VMs or bare metal | You install, back up, and upgrade it | `etcd` health, certificates, upgrades, node OS |
| Managed (EKS/GKE/AKS) | Teams that prefer cloud operations | Provider operates and patches it | Node pools, version upgrades, add-ons, workloads |

: Table 3.1 - Cluster environments compared

## 3.2 Local Clusters with kind

`kind` builds each node from a Kubernetes node image and wires them with Docker networking, which makes it the fastest honest Kubernetes on a laptop: not a simulator, the real components, `containerd` included, squeezed into containers. Install it from the `kind` releases page or with your package manager, have Docker running, and you can create a three-node cluster with a small config file. Pin the node image to the Kubernetes version you intend to learn, because `kind` will otherwise choose its default for you.

```yaml
# create a 1 control-plane + 2 worker cluster (config: kind-3node.yaml)
cat > kind-3node.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
EOF

kind create cluster --config kind-3node.yaml --image kindest/node:v1.37.1
kubectl cluster-info
kubectl get nodes -o wide
```

Two `kind` behaviors matter beyond the lab. First, `kind` injects its own `kubeconfig` into your default context, so creating a `kind` cluster silently changes where `kubectl` points; Chapter 3.5 explains how to switch back deliberately. Second, images used in `kind` must be loadable into the cluster, so build locally and run `kind load docker-image myorg/api:1.0` before referencing the tag, or push to a registry `kind` can pull from. In CI pipelines `kind` is the de facto standard for integration tests: create, test, delete, all inside one job.

## 3.3 Production Clusters with kubeadm

`kubeadm` is the official bootstrap tool: it provisions certificates, writes static control plane manifests for the `kubelet` to keep alive, generates the bootstrap tokens workers use to join, and leaves you with a cluster the standard tooling can upgrade. It deliberately stops at the edge of Kubernetes itself; it does not install your CNI, your load balancer, or your monitoring, which is exactly why it remains the honest way to learn what a cluster is made of.

Preparation is most of the work. Every machine needs a supported Linux with cgroup v2 enabled, `containerd` as the CRI runtime with the `SystemdCgroup` driver configured, swap disabled, and kernel modules and sysctls for bridged traffic; then install `kubeadm`, `kubelet`, and `kubectl` from `pkgs.k8s.io` at the pinned minor version you chose. Pin the version deliberately: the package repositories serve every minor, and drift between node versions is the classic source of subtle `kubelet` failures.

```bash
# on every node (Ubuntu 24.04 example): containerd + kubeadm stack
sudo apt-get update && sudo apt-get install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd

# pin the k8s repo to your chosen minor (v1.37 here) and install
sudo apt-get install -y apt-transport-https ca-certificates curl gpg
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.37/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] \
  https://pkgs.k8s.io/core:/stable:/v1.37/deb/ /" \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update && sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

Initializing the control plane is one command with one decision inside it: the pod network CIDR, which must not collide with your node or service ranges, because the CNI will rely on it. After init, `kubeadm` prints a join command with a one-time token for workers; run `kubeadm join` on each worker as printed. The cluster will show nodes `Ready` only after a CNI is installed, because nodes cannot report network readiness without one; install your CNI's manifest, Calico and Cilium are the usual choices, immediately after init, and verify with `kubectl get nodes` and a test `Pod` that resolves a `Service` name.

```bash
# control plane
sudo kubeadm init --pod-network-cidr=10.244.0.0/16
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# install a CNI (example: flannel for the CIDR above)
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

# on each worker, run the printed join command:
#   kubeadm join 10.0.0.10:6443 --token <token> \
#     --discovery-token-ca-cert-hash sha256:<hash>
kubectl get nodes
```

## 3.4 Managed Control Planes

EKS, GKE, and AKS operate the same components from Chapter 2 inside the provider's estate: the API server is load balanced and patched for you, `etcd` is replicated and backed up, and you receive a `kubeconfig` instead of an init command. What you still own is longer than newcomers expect: the version upgrade itself, because providers stage support windows rather than upgrade for you; node pools, their images, and their taints; every add-on in Chapter 2; quotas and IP ranges; and, critically, the workloads. The failure modes that fill Part II of this book, OOMKills, bad rollouts, certificate expiries in your own manifests, are not solved by management; only the control plane layer is.

Choose managed when the team's scarcest resource is platform attention and the cluster runs in one cloud. Choose `kubeadm` when you need control of the version cadence, on-premises hardware, or specialized networking, and accept the operational duty that comes with it. Many real estates run both: managed clusters for product teams, one `kubeadm` or upstream-based platform for the parts that must stay in-house.

## 3.5 kubeconfig and Contexts

`kubectl` reads connection details from a `kubeconfig` file, by default `~/.kube/config`, and the file holds three lists: clusters with their API endpoints and certificate authorities, users with their credentials, and contexts that bind one cluster to one user and one default namespace. Merging files is routine: `admin.conf` from `kubeadm`, a downloaded EKS or AKS `kubeconfig`, a `kind` context, all combined with `KUBECONFIG=~/.kube/config:~/.kube/eks.yaml` into one view. Switching with `kubectl config use-context` or, better, the explicit `--context` flag per command prevents the classic accident of applying a manifest to production when you meant the lab.

::: {.note}
**Best practice**

Set your shell prompt to show the current context and namespace, through `kubie`, `kubectl ctx` plugins, or a simple `PROMPT` hook, and prefer `kubectl config set-context --current --namespace` for project work. Most apply-to-the-wrong-cluster stories begin with an unmarked context switch, and the fix costs one line of shell configuration.
:::

::: {.lab}
### Lab 1 - Create a cluster and walk the anatomy {#lab1}

1. Install `kind` and create the three-node cluster from Section 3.2, pinned to v1.37.1. Run `kubectl get nodes -o wide` and confirm one control-plane and two workers, all `Ready`.
2. Run `kubectl get pods -n kube-system` and match at least five Pods to Chapter 2's components: `kube-apiserver`, `etcd`, `scheduler`, `CoreDNS`, and the CNI agent. Name each one's job out loud.
3. Deploy a sample app with `kubectl create deployment web --image=nginx --replicas=2`, then use `kubectl get pods -o wide` to verify both replicas landed on worker nodes, not the control plane. Explain which Chapter 2 mechanism kept them off the control plane.
4. Trace one object end to end: `kubectl get deployment web -o yaml`, then its `ReplicaSet` and Pods via `kubectl get rs` and the `ownerReferences` you find. You are re-walking Section 2.3 in a live cluster.
5. Break it on purpose: `kubectl delete pod -l app=web` and immediately `kubectl get pods -w`. Watch the `ReplicaSet` controller reconcile the count back to two, then clean up with `kind delete cluster`.
:::

**See also:** [Chapter 4](#ch4) for what to run once the cluster answers, [Chapter 8](#ch8) for packaging, and [Appendix C](#appC) when a cluster will not come up.
