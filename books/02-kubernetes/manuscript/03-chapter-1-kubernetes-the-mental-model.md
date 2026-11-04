# Chapter 1 - Kubernetes: The Mental Model {#ch1}

Docker taught you to run one container well. Kubernetes answers the question that follows within weeks of real usage: who restarts the container when the node dies, who replaces it when the host is patched, who spreads thirty replicas across three zones, and who updates the load balancer when a replica moves? An orchestrator is the answer, and Kubernetes won that role so thoroughly that running containers in production and running Kubernetes have become nearly synonymous. This chapter builds the mental model once, correctly, because almost every operational surprise in the rest of the book traces back to a fuzzy understanding of three ideas: declarative configuration, control loops, and the API.

## 1.1 From Containers to Orchestrated Containers

A container engine gives you process isolation and packaging; it does not give you operations. The moment a second host exists, manual `docker run` becomes a coordination problem: which image is where, what happens on reboot, how traffic finds a container that just moved hosts. Kubernetes treats that coordination as a first-class problem. It takes a set of machines, virtual or physical, and presents them as one programmable surface: a single API through which you declare what should run, and a set of controllers that continuously work to make the cluster match your declaration.

The unit Kubernetes schedules is not a container but a `Pod`, the smallest deployable object. A Pod wraps one or more containers that share a network namespace, an IP address, and storage volumes, plus a shared fate: they are scheduled together, started together, and killed together. Most Pods contain exactly one container, and the patterns where two containers deliberately share a `Pod`, such as a main application with a log shipper or a service mesh proxy, are called sidecars. Since Kubernetes v1.29 sidecars are a native construct with defined start and stop ordering, rather than a hack of ordinary containers listed together.

What you gain from the orchestration layer is precisely what was missing. Self-healing replaces restart scripts: a controller notices the desired replica count and recreates what is missing. Scheduling replaces hand-picked hosts: the scheduler places each `Pod` by constraints and available capacity. Services with stable virtual IPs and DNS names replace container-linking and port spreads, so a frontend does not care which node its backend runs on. And because everything is expressed as API objects stored in one place, the entire desired state of your platform is serializable, reviewable in git, and reproducible.

## 1.2 The Declarative Model and Control Loops

Kubernetes configuration is declarative: you do not command a sequence of steps, you publish the desired end state. A `Deployment` object that says five replicas of image `myorg/api:1.4.0` is not a request to start five containers right now; it is a statement that five replicas is the truth, and it stays the truth whether you apply it once or a hundred times. This is different from the imperative `docker run` habit, and the difference is the source of most beginner friction: you stop asking how and start specifying what.

Underneath, Kubernetes is a federation of control loops. Each controller watches the actual state of one resource kind, compares it to the declared state, and performs whatever action moves the world closer to the declaration, then watches again. The `ReplicaSet` controller creates Pods when the count is low and deletes them when it is high. The node controller marks machines unreachable when heartbeats stop. The deployment controller rolls out new ReplicaSets one step at a time. No controller knows the whole plan, and none needs to: the reconciliation pattern, converge repeatedly toward a declaration, is enough to produce remarkably robust behavior from simple parts.

The model has a corollary that experienced operators repeat like a spell: if you edit the running world by hand, the controllers will eventually undo you. Change a `Deployment` image with `kubectl edit` and the new value is stored, which is legal but fragile; change a `Pod` spawned by a `ReplicaSet` and your manual fix is destroyed at the next reconciliation. The discipline that follows is to treat the API as state and the manifest in git as source, and Chapter 13 builds an entire delivery workflow on exactly that.

## 1.3 The API Is the Product

Everything in Kubernetes is an API object: Pods, Services, ConfigMaps, and the cluster's own nodes are all records stored in `etcd` and served by the API server. The `kubectl` you use daily is a thin, convenient client over a REST API with a small verb set: `get`, `list`, `create`, `update`, `patch`, `delete`, and `watch` for streaming changes. Roles and RoleBindings gate every request; the audit log records every mutation; and because the API is versioned, the ecosystem can build on it without forking. When you debug, you are almost always asking a question about API objects, and `kubectl get` with `-o yaml` is the honest answer sheet.

API resources carry a stability level that tells you how much to trust them. Stable resources, at `v1`, are safe for production. Beta resources usually work but may change or default differently. Alpha resources are experimental, disabled by default, and excluded from support promises. The same ladder applies to whole features: the Dynamic Resource Allocation core APIs reached GA in v1.34, while scaling workloads to zero with the `HorizontalPodAutoscaler` is alpha in v1.37. Reading the stability level before adopting a field is a habit that prevents upgrade-day surprises.

The API is also extensible, which is why Kubernetes has swallowed entire product categories. Custom Resource Definitions let you add new object kinds, and a custom controller can watch and reconcile them like any built-in kind. A database operator, for example, adds a kind called `PostgresCluster` and then knows how to create StatefulSets, Services, and backups for it. Chapters 11 and 13 lean on this mechanism heavily; for now, register that Kubernetes is not a fixed feature set but a framework whose feature set grows through the same API.

## 1.4 What Kubernetes Does Not Do

Kubernetes does not build images; Docker and BuildKit remain the build layer, and the cluster consumes their artifacts from a registry. It does not run your CI system, though CI systems deploy through its API. It does not collect or store logs and metrics beyond what `kubelet` exposes, so Chapter 12 adds the standard stack. It does not manage the nodes' operating systems, patch kernels, or configure your cloud networking, though it tells you clearly when nodes are unhealthy. Where a responsibility ends, the book says so, because assuming Kubernetes handles something it does not is how gaps become outages.

Kubernetes also does not make small estates automatically simpler. A three-node cluster running two services is a distributed system with `etcd`, certificates, upgrades, and a control plane to babysit, and Compose on a single host would serve it with less ceremony. The honest threshold most teams converge on is: adopt Kubernetes when you have enough services, team members, or failure modes that the orchestration, standardization, and ecosystem pay for themselves. Everything beyond that threshold, this book covers.

| Docker concept | Kubernetes counterpart | What changed |
| ------------- | --------------- | ---------------------- |
| `docker run` | `Pod` / `Deployment` | Declared desired state instead of a one-shot command; controllers keep it true |
| `docker compose service` | `Deployment` + `Service` | Replicated, self-healing, and reachable through a stable virtual IP and DNS name |
| `--restart=always` | `ReplicaSet` controller | Managed at cluster level, survives node failure, not just container exit |
| `docker network create` | CNI network + `Service` | Every `Pod` is cluster-routable; discovery is DNS, not container names |
| `-v /data:/var/lib/data` | `Volume`, `PVC`, `StorageClass` | Storage is a first-class API with provisioning, quotas, and lifecycle |
| `ENV` / `.env` file | `ConfigMap` / `Secret` | Configuration is versioned, applied, and injectable without rebuilding images |
| `docker stack deploy` | Helm / Kustomize / GitOps | Packaging and release tooling grown around the API, covered in Chapter 8 and 13 |

: Table 1.1 - Docker concepts and their Kubernetes counterparts

::: {.note}
**Best practice**

When a pod behaves strangely, resist the urge to reason from the Docker habit of inspecting a process. Ask the three Kubernetes questions first: what does the declared state say (`kubectl get -o yaml`), what does the controller think happened (`kubectl describe`, Events), and what is the actual state (pod status, logs). Diagnosis becomes mechanical when you always compare declaration, controller view, and reality in that order.
:::

**See also:** [Chapter 2](#ch2) for the components behind this model, [Chapter 4](#ch4) for the objects you will spend your days in, and the *Docker for DevOps Engineers* volume if the container half is still shaky.
