# Chapter 2 - Cluster Anatomy: Control Plane, Nodes, and the API {#ch2}

Before creating a cluster it pays to know what you are creating. A Kubernetes cluster is two populations of machines: control plane nodes that run the brain, and worker nodes that run your workloads. This chapter names every component, explains what breaks when each one fails, and then walks a single `kubectl apply` through the machinery so the vocabulary becomes a story you can retell. The component names here are the words of the entire book; everything later, from RBAC to upgrades, presupposes them.

## 2.1 The Control Plane

The `kube-apiserver` is the single front door: the only component that talks to storage, the component every client, human or machine, connects to. It authenticates the request, authorizes it against RBAC, applies admission webhooks and defaults, validates the object against schemas, and only then writes it to `etcd`. Because every other component communicates through the API server rather than directly with each other, the API server is both the consistency point and the natural place for policy. It is also stateless, so you scale it horizontally behind a load balancer and restart it without losing cluster state.

`etcd` is the cluster's memory: a distributed key-value store holding every object, strongly consistent, replicated across control plane nodes. Lose quorum and the cluster cannot accept writes, even though running Pods keep running, because nothing can record new desired state. Backups of `etcd`, covered hands-on in Chapter 14, are therefore the closest thing Kubernetes has to a database dump, and protecting `etcd` with TLS, dedicated disks, and access control is a security boundary in itself: whoever can write `etcd` owns the cluster.

The `kube-scheduler` assigns new Pods to nodes. It does not start anything; it computes the best node for each `Pod` by filtering out nodes that cannot fit the `Pod`, then scoring the survivors on soft preferences such as spreading replicas across zones or bin-packing for efficiency, and binding the `Pod` to the winner in the API. The `controller-manager` runs dozens of reconciliation loops: the deployment and `ReplicaSet` controllers, the node controller that evicts Pods from dead machines, the endpoint controllers that keep Services pointed at healthy Pods, the job controller, and the cloud controllers that create load balancers and disks when you ask for them.

## 2.2 Worker Nodes

Each worker runs three residents. The `kubelet` is the node's agent and the only component that talks to both the API server and the container runtime: it watches for Pods assigned to its node, asks the runtime to start their containers, runs health probes, applies resource limits through cgroups, and reports node and `Pod` status back. If the `kubelet` is unhealthy, the node is unhealthy as far as the cluster is concerned, regardless of how well the workloads feel.

The container runtime is `containerd` on every modern cluster. The `dockershim` was removed in v1.24 at the end of 2022, and the industry settled on the CRI interface with `containerd` as the reference implementation; Docker images run unchanged because they are OCI images, which Chapter 1 of the Docker book already established. The `kube-proxy` completes the node's job by implementing `Service` virtual IPs: it programs the node's packet filter, `iptables` by default, `nftables` as a GA alternative since v1.33, or an eBPF data plane if your CNI provides one, so that traffic to a `ClusterIP` is NATed to a live backend `Pod`.

Beyond these three, nodes run the `Pod` network through a CNI plugin such as Cilium, Calico, or Flannel, which wires pod IPs into one flat routable network, and they host the add-ons that make a cluster usable: `CoreDNS` for name resolution, the metrics server, and your ingress or gateway controller. Add-ons are ordinary Deployments and DaemonSets living in `kube-system`, which means they are visible, versioned, and upgradable with the same tools you use for everything else.

## 2.3 The Life of a Deployment

Trace `kubectl apply -f deployment.yaml` from keyboard to running containers. `kubectl` reads the file and sends a POST to the API server; authentication and authorization run first, then mutating admission webhooks fill in defaults such as `imagePullPolicy`, then validation schemas reject anything malformed. The object is written to `etcd`, and `kubectl` returns the moment the write succeeds, long before any container exists. This is the declarative model in miniature: the request recorded the desire, nothing more.

Now the loops take over. The deployment controller notices the new `Deployment` and creates a `ReplicaSet`; the `ReplicaSet` controller notices it needs three Pods and writes three `Pod` objects with `nodeName` unset. The scheduler picks a node for each, scoring on fit, spread, and affinity, and records the binding. On that node the `kubelet` sees the `Pod` in its watch stream, pulls the image through `containerd`, creates the container with the CNI plugin having already assigned a pod IP, runs the startup probe, then readiness, and flips the `Pod` to `Ready` in the API. The endpoints controller adds the `Pod` to its `Service`, and traffic arrives. Every step is an object difference that some controller reconciled; nothing was orchestrated by a central script.

Reading the same story backwards is the debugging method. `Pod` `Pending` means the scheduler story stopped, and `kubectl describe` names the blocker. `ImagePullBackOff` stops the story at the `kubelet`, usually registry access or a typo. `CrashLoopBackOff` gets past the start but the container exits, so the logs are the next question. Chapter 14 turns this into a full playbook; for now, the walkthrough shows why the vocabulary of Chapter 2 pays for itself immediately.

## 2.4 Metadata: Labels, Annotations, Owners, and Finalizers

Four metadata mechanisms organize everything you just saw. Labels are the query system: key-value pairs that selectors across Services, Deployments, and NetworkPolicies match on, which makes them part of your networking and management contract, not decoration. Annotations store non-identifying metadata for tools and humans, such as ingress controller configuration or last-applied manifests. `ownerReferences` link children to parents, so deleting a `Deployment` garbage-collects its ReplicaSets, which in turn own their Pods; debugging is easier when you can name the owner chain. Finalizers are the opposite lever: they block deletion until an external cleanup completes, and a stuck namespace or `PVC` is very often a finalizer waiting on something that will never run.

| Component | Plane | Responsibility | Failure symptom |
| ----------- | ------- | ------------------- | ------------- |
| `kube-apiserver` | Control | All reads and writes; authentication, admission, validation | Cluster unreachable; `kubectl` hangs; nothing can change |
| `etcd` | Control | Stores every object with strong consistency | Writes fail cluster-wide; running workloads keep running |
| `kube-scheduler` | Control | Assigns new Pods to nodes | New Pods stay `Pending` |
| `controller-manager` | Control | Reconciliation loops (deployments, nodes, endpoints, jobs) | Desired state drifts; failed nodes not cleaned up |
| `kubelet` | Node | Runs and probes Pods; reports status | Node shows `NotReady`; Pods evicted or stuck |
| `kube-proxy` | Node | Programs `Service` VIPs on the node | Services unreachable from that node |
| CNI plugin | Node | `Pod` networking and IP allocation | Pods fail networking; nodes `NotReady` |

: Table 2.1 - Components at a glance and what their failure looks like

::: {.warn}
**Watch out**

Never treat the control plane as a convenient place to run workloads. On self-managed clusters the control plane hosts `etcd` and the API server, and a memory-hungry `Pod` scheduled there can take the whole cluster down with an OOM kill. Taint the control plane nodes so ordinary Pods cannot land there, which `kubeadm` does by default, and keep the habit even on small lab clusters where the taint is easiest to relax.
:::

**See also:** [Chapter 3](#ch3) to stand a cluster up and touch these pieces, [Chapter 9](#ch9) for the controls on the API surface you just met, and [Chapter 14](#ch14) for the `etcd` backups this anatomy makes non-negotiable.
