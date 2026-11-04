# Chapter 2 - Installing and Configuring Docker {#ch2}

Installation is where careers quietly diverge. Engineers who install Docker carelessly spend years fighting mystery behavior: a daemon pinned to the wrong data root, a distribution-packaged engine three years out of date, logs nobody configured consuming the whole disk. This chapter installs Docker the way operations teams do - from the official repositories, with a deliberate daemon configuration - and then verifies the result properly.

## 2.1 Choosing the Right Distribution of Docker

There are two products and picking the right one matters. **Docker Engine** is the open-source server for Linux hosts: it is what you install on servers, VMs, and CI runners, and it is managed with systemd. **Docker Desktop** is the developer product for Windows and macOS (and Linux desktops), which runs a trimmed Linux VM under the hood and adds a GUI, Kubernetes, and integrations. Production servers always run Docker Engine; Desktop is for workstations. Licensing differs as well - Desktop requires a paid subscription for larger professional organizations, while the Engine from the official repositories is free to use, so treat Desktop as a developer convenience, not a server component.

## 2.2 Installing Docker Engine on Linux

Always install from Docker's official apt or dnf repositories, never from the distribution's own `docker.io` or `docker` packages, which lag behind and carry different service assumptions. On Ubuntu and Debian the sequence below sets up the repository with its signing key and installs the engine plus the two CLI plugins you will use constantly - Compose and buildx. The commands are shown for Ubuntu 24.04; the equivalents for Debian, Fedora, RHEL, and SLES differ only in the repository URL and package manager.

```
# Ubuntu / Debian - official Docker repository
sudo apt-get update && sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

On RHEL, Rocky, or Fedora the same idea applies with dnf: install the `dnf-plugins-core` package, add `https://download.docker.com/linux/centos/docker-ce.repo` (for RHEL-family) or the Fedora repository, then `dnf install docker-ce docker-ce-cli containerd-io docker-buildx-plugin docker-compose-plugin` and start the service. After either path, add your daily user to the `docker` group with `sudo usermod -aG docker $USER`, then log out and back in. Be aware of what that membership means: it is effectively root access on that host, because the socket allows spawning containers with arbitrary host mounts. On multi-admin machines, treat group membership like sudo rights and audit it.

## 2.3 Rootless Mode

Rootless Docker runs both the daemon and the containers under an unprivileged user, using user namespaces so that the container's root maps to an unprivileged host user. The attack surface shrinks dramatically - a container breakout no longer lands on a root-owned daemon - and many compliance regimes now expect it for multi-tenant hosts. Install it with the bundled script and enable the systemd user unit:

```bash
sudo apt-get install -y uidmap dbus-user-session
curl -fsSL https://get.docker.com/rootless | sh
systemctl --user enable --now docker
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock
```

Rootless mode has trade-offs you must know before choosing it: port publishing below 1024 requires a sysctl tweak, overlay networking is more limited, and some storage backends behave differently. For single-purpose dedicated hosts, classic rootful Docker with a hardened daemon is still the norm; for shared build hosts and CI runners, rootless is increasingly the default recommendation. Chapter 10 covers the security model in depth.

## 2.4 Docker Desktop on Windows and macOS

On macOS, Desktop runs a Linux VM managed through Apple's Virtualization framework, with either the default VMM or, since late 2026, the optional Docker VMM; on Windows it runs either under WSL2 (preferred) or the Hyper-V backend. Two settings deserve immediate attention on a workstation. First, resource allocation: the VM's CPU and memory limits in Settings - Resources bound everything your containers can do, so size them honestly. Second, file sharing performance: bind mounts from the host into containers cross a VM boundary, and enabling VirtioFS on macOS or synchronized file shares on Windows is the difference between tolerable and painful development loops. Desktop also bundles a Kubernetes cluster, which Chapter 11 uses for local orchestration experiments.

## 2.5 The daemon.json File

Almost every meaningful daemon setting lives in `/etc/docker/daemon.json`, a JSON file applied at startup; in rootless mode it lives under `~/.config/docker/daemon.json`. Resist the urge to paste random snippets from the internet - the file below is a solid production baseline, and the table explains each key. Changes require a daemon restart, so plan them like any other service change.

```json
{
  "data-root": "/var/lib/docker",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "live-restore": true,
  "default-address-pools": [
    { "base": "172.17.0.0/16", "size": 24 },
    { "base": "172.18.0.0/16", "size": 24 }
  ],
  "registry-mirrors": ["https://<your-mirror>.example.com"],
  "insecure-registries": [],
  "metrics-addr": "127.0.0.1:9323"
}
```

| Key | What it controls | Operational note |
| ------------- | -------------------- | ----------------- |
| data-root | Where images, containers, and volumes live | Put it on dedicated storage; moving it later means a migration, not a rename |
| log-driver / log-opts | Default logging driver and rotation | Set max-size and max-file now; Appendix C shows what happens if you do not |
| live-restore | Containers keep running during daemon restarts/updates | Strongly recommended; required by most ops runbooks |
| default-address-pools | Subnets allocated to user-defined networks | Change it when corporate ranges collide with 172.17.x |
| registry-mirrors | Pull-through mirrors tried before Docker Hub | Common behind corporate proxies and in rate-limited CI |
| insecure-registries | Registries allowed over plain HTTP | Leave empty unless you own the network path |
| metrics-addr | Prometheus endpoint for daemon metrics | Bind to localhost and scrape; see Chapter 12 |

: Table 2.1 - daemon.json keys that matter in operations

## 2.6 Verifying, Upgrading, and Version Discipline

Verify an installation with three commands and read all three outputs. `docker version` should show client and server agreeing on an API version of at least 1.44 - Engine v29 dropped compatibility with older clients, so a mismatch here is the first thing to check after upgrades. `docker info` prints the effective configuration, storage backend, logging driver, and plugin list; make a habit of diffing it after config changes. Finally `docker run --rm hello-world` exercises the full path: registry DNS, TLS, pull, layer unpacking, and container start.

Upgrades deserve the same discipline as any other service update. Read the release notes for the major jumps (v28 and v29 both changed defaults), upgrade the packages with apt or dnf during a maintenance window, and rely on `live-restore` to keep workloads alive across the daemon restart. Pin versions in infrastructure-as-code by installing specific packages such as `docker-ce=5:29.0.*`, and hold unattended-upgrades back for the docker packages so a routine nightly patch never surprises you with a behavior change. A DevOps engineer upgrades Docker deliberately, on schedule, with a rollback path - never as a side effect of an OS patch.

::: {.warn}
**Watch out**

Never expose the Docker API on TCP without mutual TLS, and never bind 0.0.0.0:2375 for convenience. A decade of scans shows open Docker APIs are among the fastest routes from an exposed port to a root shell and a cryptominer. If you need remote access, use SSH to the host or an authenticated, TLS-protected socket.
:::

::: {.lab}
### Lab 2 - Install and shape the daemon {#lab2}

1. Install Docker Engine from the official repository on a Linux VM (or confirm an existing install came from there with `apt policy docker-ce`).
2. Write a daemon.json containing `log-opts` with `max-size: 10m` and `max-file: 5`, enable `live-restore`, and restart Docker with `sudo systemctl restart docker`.
3. Run `docker run --rm hello-world`, then run `docker info` and verify that the logging driver shows max-size 10m and that live-restore is enabled.
4. Deliberately break the file by removing a comma, restart Docker, watch it fail, read `journalctl -u docker --no-pager | tail -20`, fix it, and recover. Practicing the failure once in a lab is what makes the real one boring.
:::

**See also:** [Chapter 3](#ch3) for the first commands against a fresh install, [Chapter 10](#ch10) for daemon and socket hardening, and [Appendix C](#appC) when the daemon refuses to start.
