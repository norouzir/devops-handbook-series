# Chapter 11 - Orchestration: Swarm, Kubernetes, and the Runtime Landscape {#ch11}

The moment your application outgrows one host, plain Docker stops being the whole answer: something must place containers on machines, restart them when nodes die, load-balance between replicas, and roll updates without downtime. That something is an orchestrator. This chapter gives you a working grasp of Swarm - the orchestrator inside Docker Engine - a precise account of why Kubernetes became the default, and a sober map of the runtime landscape you will meet in the wild.

## 11.1 What Orchestration Adds

List the operational verbs you would otherwise hand-roll and the case closes itself: scheduling (which of fifty nodes runs which of two hundred containers), reconciliation (a container or node dies; desired state is restored automatically), service discovery and load balancing across replicas, secrets and configuration distribution, and rolling updates with health-gated progress and rollback. Orchestrators are declarative: you state the desired state - five replicas of image X with this healthcheck - and a control loop converges reality onto it forever. Docker ships one such control loop natively in Swarm mode, and it remains the least-machinery way to run a small cluster without adding a second system to operate.

## 11.2 Swarm Mode Essentials

Swarm mode is built into the Engine: `docker swarm init` turns a node into a manager, join tokens add workers and additional managers (run an odd number, three for small estates), and everything afterwards is expressed against desired state. Services are the unit - a specification of image, replicas, ports, and constraints that the swarm maintains:

```bash
docker swarm init
docker swarm join-token worker        # print the worker join command

docker service create --name web \
  --replicas 3 \
  --publish published=8080,target=80 \
  --update-delay 10s --update-parallelism 1 \
  --health-cmd "wget -qO- http://127.0.0.1:80/ || exit 1" \
  --rollback-parallelism 1 \
  myorg/api:1.4.0

docker service ls
docker service ps web                 # task placement and history
docker service scale web=6
docker service logs -f web
```

Three swarm primitives matter most in daily operation. The **routing mesh** publishes a port once on any node and load-balances across tasks everywhere - clients do not need to know where replicas live. **Rolling updates** are declarative: pushing a new tag to a service replaces tasks in bounded waves with healthchecks gating progress, and an unhealthy wave triggers automatic rollback (the flags above). **Secrets and configs** distribute sensitive and plain files to exactly the tasks that declare them, mounted at `/run/secrets`. A `stack` (a Compose file version 3 deployed with `docker stack deploy`) packages all of it, which makes the migration path from Chapter 9's compose files gentle: same mental model, cluster-wide reach. Swarm's honest limits: one ecosystem, a small extension market, and a feature velocity that is maintenance-level rather than competitive - which is precisely why it suits small, stable estates and not hyperscale ambitions.

## 11.3 Kubernetes and the dockershim Story

Kubernetes won because it treats everything - storage, networking, scaling, deployment - as composable declarative resources with a colossal ecosystem behind them. For a Docker-focused engineer, one historical fact matters most: Kubernetes removed its dockershim in version 1.24 (2022). Since then, the kubelet speaks the Container Runtime Interface to runtimes such as containerd and CRI-O directly - containerd being the very component inside Docker Engine. The practical consequences are all good news with one nuance. Good news: images built with Docker are OCI images and run unchanged; the build skills in this book transfer fully; and the containerd you met in Chapter 1 is the same component cluster nodes run. The nuance: on a Kubernetes node there is no `docker` CLI - debugging uses `crictl` and `ctr`, logs and exec go through the kubelet, and your Docker-fingered muscle memory maps onto `kubectl` commands instead. Docker Desktop ships a single-node Kubernetes cluster (and `kind` - Kubernetes in Docker - runs full multi-node clusters on any Docker host), so you can learn the kubectl side of the house without leaving the toolchain this book taught you.

## 11.4 Choosing: Compose, Swarm, Kubernetes, Nomad

The choice is a function of team size, estate size, and appetite for operating a platform - not fashion. Compose is for single-host stacks and CI environments. Swarm is for small multi-host estates (roughly two to a dozen nodes) run by a small team that wants orchestration without adopting a new platform. Kubernetes is for larger estates, polyglot workloads, and organizations that will invest in a platform team and benefit from its ecosystem; its cost is a genuinely steep operational learning curve, mitigated by managed offerings (EKS, GKE, AKS) that remove control-plane toil. HashiCorp Nomad remains a credible middle path with simpler operations, notable in shops already running HashiCorp tooling. Write the decision down with your constraints; revisit it when node count doubles, not when a conference talk says so.

| Estate | Sensible default | Reason |
| --------------- | ----------- | ------------------------ |
| One host, many services | Compose | Zero extra systems; the file is the documentation |
| 2-12 nodes, small team | Swarm | Orchestration with no new platform to operate |
| Dozens of nodes, many teams | Kubernetes (managed) | Ecosystem, hiring pool, managed control planes |
| Mixed non-container workloads | Nomad (consider) | One scheduler for containers, VMs, and binaries |

: Table 11.1 - Orchestration choices in practice

## 11.5 Podman and the Wider Runtime Landscape

You will share infrastructure with tools that are not Docker, and fluency means knowing what they change. **Podman** is Red Hat's daemonless container engine: commands are Docker-compatible (`alias docker=podman` famously just works), but there is no root daemon to harden, roots are user-native, and pods group containers the way Kubernetes will later schedule them - which is why it is the default on RHEL-family servers. **containerd plus nerdctl** is the minimal path for hosts that run only containers (and the reality inside every Kubernetes node), speaking the same OCI formats. **crun** and **runc** are interchangeable low-level runtimes you will meet in tuning conversations. The strategy that keeps you portable: author OCI artifacts and Compose/Kubernetes manifests, avoid Docker-proprietary features in production paths, and treat engine choice as an infrastructure decision per host class rather than a worldview.

::: {.lab}
### Lab 11 - Swarm in three nodes {#lab11}

1. Using three VMs (or three Docker-in-Docker containers on one machine), run `docker swarm init` on one and join the others as workers; verify with `docker node ls`.
2. Deploy the Chapter 9 stack with `docker stack deploy -c compose.yaml app` and find where its three tasks actually landed (`docker service ps`).
3. Publish port 8080 through the routing mesh and curl it from every node - including nodes with zero local replicas; explain why that works.
4. Perform a rolling update by pushing a new tag with `--update-parallelism 1 --update-delay 10s`, then sabotage the healthcheck on the next update and watch the automatic rollback. Record which flag caused each behavior.
:::

**See also:** [Chapter 9](#ch9) for the single-host tooling orchestration replaces, [Chapter 12](#ch12) for what you will need once workloads span nodes.
