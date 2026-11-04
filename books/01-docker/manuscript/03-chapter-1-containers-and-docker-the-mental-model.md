# Chapter 1 - Containers and Docker: The Mental Model {#ch1}

Before touching a single command, you need a precise mental model of what a container is and what it is not. Almost every production mistake with Docker traces back to a fuzzy understanding of this model: people expect containers to behave like virtual machines, or expect data inside a container to survive replacement, or assume the daemon runs on the same kernel boundaries as the workload. This chapter builds the model once, correctly, and everything in the rest of the book hangs off it.

## 1.1 Virtual Machines versus Containers

A virtual machine virtualizes hardware. A hypervisor emulates CPUs, memory, disks, and network cards, and on top of that emulated hardware each VM boots its own full operating system, including its own kernel. A container does none of that. A container is an ordinary Linux process - or a group of processes - that the kernel isolates and constrains using built-in primitives. Containers share the host kernel; they do not boot anything. That is why a container starts in milliseconds instead of tens of seconds, why dozens of containers fit where one or two VMs would fit, and why a container image of a few dozen megabytes can do the work of a multi-gigabyte VM image.

The trade-off is the boundary. A VM gives you kernel-level isolation: a crash or an exploit inside a VM stays inside that kernel. A container only isolates what the kernel primitives it uses can isolate - process trees, filesystem views, network stacks, resource budgets. For most workloads that boundary, hardened correctly as Chapter 10 shows, is entirely adequate and is the same boundary that virtually all modern cloud platforms rely on. What you gain in exchange is consistency: the unit you test on your laptop and the unit that runs in production are literally the same artifact, byte for byte.

| Aspect | Virtual machine | Container |
| ------------ | ------------------- | ------------------- |
| Kernel | One full kernel per guest | Shared host kernel |
| Boot time | Tens of seconds | Milliseconds |
| Image size | Gigabytes | Typically 5-300 MB |
| Density per host | A handful | Tens to hundreds |
| Isolation boundary | Hypervisor plus guest kernel | Kernel namespaces and cgroups |
| Portability artifact | VM image per hypervisor | OCI image, runs on any compliant runtime |

: Table 1.1 - Virtual machines and containers compared

## 1.2 The Kernel Primitives Underneath

Docker did not invent containerization; it packaged and popularized three primitives that the Linux kernel had grown over decades. First, **namespaces** give each container its own view of the system: the PID namespace gives it a private process tree whose first process is PID 1, the network namespace gives it a private network stack with its own interfaces and routing table, the mount namespace gives it a private filesystem view, and the UTS, IPC, and user namespaces isolate hostname, inter-process communication, and user identity respectively. When a container says it is alone in the world, namespaces are why.

Second, **cgroups** (control groups, version 2 on every modern distribution) cap what a container may consume: CPU time, memory, I/O bandwidth, and the number of processes. This is the mechanism behind flags you will use daily such as `--memory` and `--cpus`, and it is why one misbehaving container cannot starve its neighbors by default. Third, **union filesystems**, implemented in practice by `overlay2` and now by the containerd snapshotter, let an image be composed of read-only layers stacked on top of each other, with a thin writable layer added per container. Layers make images cheap to store, fast to pull, and shareable between images - the entire registry economy rests on this one design.

::: {.note}
**Best practice**

Remember the phrase: namespaces decide what a container can see, cgroups decide what it can use, and union filesystems decide what it is made of. Diagnosing almost any surprising container behavior starts by asking which of the three is involved.
:::

## 1.3 Docker Architecture: CLI, Daemon, containerd, runc

When you type `docker run nginx`, the journey is longer than it looks. The `docker` **CLI** is a thin client that speaks REST over a Unix socket (`/var/run/docker.sock`) or a TCP socket. The **Docker daemon** (`dockerd`) receives the request, resolves the image, and delegates. Since the v29 architecture, image and layer management happens in the **containerd image store**, and container execution is delegated to **containerd**, which supervises a per-container shim and invokes **runc**, the reference OCI runtime, to actually create the namespaces and cgroups and start your process. Once runc finishes setting the process up, it exits by design; the lightweight shim keeps the standard streams connected so the container survives daemon restarts.

This chain matters operationally. It explains why `docker` commands fail when the daemon is down even though running containers may keep working, why `systemctl restart docker` does not necessarily kill your workloads when `live-restore` is enabled, and why the Docker socket is so sensitive: whoever talks to it can ask the daemon, and therefore the kernel, to do anything, including starting a container with the host root filesystem mounted. Chapter 10 returns to that point repeatedly. Since Engine v29, fresh installations use the containerd image store by default; upgraded hosts keep their legacy graph driver until you migrate deliberately, and the legacy drivers are on a published deprecation path.

| Component | Role | You touch it when |
| ----------- | ---------------------- | ----------------- |
| docker CLI | Thin REST client | Every command you type |
| dockerd (daemon) | API server, orchestration of builders, networks, volumes | Configuring daemon.json, restarting the service |
| containerd | Supervises containers, owns the image store | Rarely directly; ctr/crictl debugging |
| containerd-shim | Per-container process that outlives daemon restarts | Troubleshooting live-restore behavior |
| runc | OCI runtime that creates namespaces and cgroups | Almost never directly |
| BuildKit / buildx | Image build engine and CLI plugin | Every docker build you run |

: Table 1.2 - The moving parts of a modern Docker installation

## 1.4 The OCI Standards

Docker, Inc. donated the core container formats to the Open Container Initiative (OCI) years ago, and three specifications now define the ecosystem. The **image specification** describes how layers and configuration are packaged; the **runtime specification** describes what a compliant runtime such as runc must do; and the **distribution specification** describes how registries push and pull content. The practical consequence for a DevOps engineer is freedom of tooling: an image built by Docker runs under Podman, is scheduled by Kubernetes through containerd, and can be copied between any two registries, because everyone is exchanging the same artifact. It also means that when you harden or audit images, you are auditing an OCI artifact, not a Docker proprietary format - a distinction that matters in procurement and compliance conversations.

## 1.5 Docker in the 2026 Toolchain

It is worth being honest about where Docker sits today. Kubernetes won the orchestration war, and every serious cluster runs containers through a CRI runtime - containerd in practice - rather than through the Docker daemon; Kubernetes removed its dockershim in version 1.24, and images built with Docker run there without any conversion because they are OCI images. Docker the product remains the dominant developer-facing toolchain: the Engine and Docker Desktop build and run containers locally, Compose defines multi-container applications, BuildKit and buildx produce multi-platform images with cryptographic attestations, and Docker Hub, together with Docker Scout and the Docker Hardened Images catalog, provides the registry and security layer. Docker Swarm still ships inside the Engine as a lightweight orchestrator, and Chapter 11 gives it a fair hearing for small estates.

So the modern division of labor is: build and test with Docker locally and in CI, distribute through registries, run at scale on Kubernetes, and use Swarm or plain Compose when the estate is small and the operational budget is tight. Understanding what Docker alone does well - and where the boundary with Kubernetes starts - is precisely the kind of judgment this book is trying to sharpen.

## 1.6 When Containers Are the Wrong Tool

A mature engineer knows when not to reach for the tool. Containers add the most value for stateless services, workers, and anything with a twelve-factor shape: start fast, log to stdout, hold no local state that matters. They add friction when a workload needs a persistent, mutable filesystem with strong fsync semantics (databases are containerized constantly, but their data must live in volumes, and some still belong on bare metal), when you need a different kernel than the host, when strict compliance requires hardware-level tenancy, or when the software is licensed per physical or virtual machine in a way that does not recognize containers. Desktop applications with graphical UIs, kernel modules, and low-level daemons that expect to manage the whole host are also poor fits. Saying no early is cheaper than migrating badly later.

::: {.lab}
### Lab 1 - Map your engine {#lab1}

1. Install Docker if you have not yet (Chapter 2 walks you through it), then run `docker version` and note the Engine version, API version, and the Go version. Confirm the server API is at least 1.44.
2. Run `docker info` and find the storage driver line. On a fresh Engine v29 install it should indicate the containerd snapshotter; note what yours says.
3. Run `ps -ef | grep -E "containerd|dockerd"` on the host and identify the daemon, containerd, and shim processes for a running container. Start `docker run -d --name lab1 nginx` first so a shim exists.
4. Run `docker system info --format "{{.ServerVersion}} {{.DriverStatus}}"` and explain each field out loud. If you can narrate the CLI-to-runc chain without looking back at Table 1.2, you are ready for Chapter 2.
:::

**See also:** [Chapter 3](#ch3) to run your first container, [Chapter 5](#ch5) to build an image of your own, and [Chapter 11](#ch11) for the moment this single-host model stops being enough.
