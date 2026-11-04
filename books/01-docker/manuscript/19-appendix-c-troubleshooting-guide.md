# Appendix C - Troubleshooting Guide {#appC}

The failures below cover the overwhelming majority of real Docker tickets. Each section is symptom, likely causes, and the fix path in the order that rules causes out fastest.

## C.1 The disk is full (or the daemon is unhealthy)

Symptoms: builds fail with no space left on device, containers die with write errors, `docker` commands hang. Diagnose with `df -h /var/lib/docker` and `docker system df -v`. The usual culprits, in order: unbounded json-file logs (fix: set log-opts, recreate containers, Appendix C.7), dangling images and build cache (fix: `docker image prune -f`, `docker builder prune -f`), and stopped containers with fat writable layers (fix: `docker container prune`). Then schedule the Chapter 13 hygiene so it stays fixed. If the data root is on a small root partition, move it: set `data-root` in daemon.json, stop the daemon, migrate with rsync, start - or reinstall with the data root on dedicated storage.

## C.2 Port already allocated

`Error starting userland proxy: listen tcp4 0.0.0.0:8080: bind: address already in use` means exactly that. Find the holder with `ss -lntp | grep 8080` (or `lsof -i :8080`): it is usually another container (`docker ps --filter publish=8080`), a host service, or a stale proxy process from a crashed container. Fix by choosing a different host port, stopping the conflicting container, or - for services that should not be public anyway - binding to loopback (`-p 127.0.0.1:8080:80`) and putting a proxy in front. On busy shared hosts, Compose files with explicit host ports collide constantly; switch to dynamic ports or a single front proxy.

## C.3 Containers cannot reach each other by name

Embedded DNS resolves names only within user-defined networks - on the default bridge it never works. Check membership: `docker network inspect NET` must list both containers. Then check the target actually listens on 0.0.0.0 inside the container (an app bound to 127.0.0.1 is unreachable even to its neighbors). Verify resolution from the client with `getent hosts db`; if the image is minimal, install iproute2/iputils first. Compose users: service names are the DNS names, and the default network is per-project - a service from another project is intentionally invisible.

## C.4 Permission denied on bind mounts

The container sees a directory it cannot read or write while the host can. On SELinux hosts (RHEL family) the label is the cause: append `:z` or `:Z` to the mount (`-v /data:/data:Z`). Elsewhere compare UIDs - a container running as an arbitrary non-root user (good!) often needs the host directory chowned to that UID or a group with matching GID. Rootless Docker adds one layer: paths must be accessible to the user running the daemon. Resist `chmod -R 777` as a fix; it trades a permission error for a security finding.

## C.5 The container exits immediately (or restarts forever)

`docker ps -a` shows Exited (0) or a flapping restart policy. Exit 0 with a foreground container usually means the main command finished - the classic is an image whose CMD starts a daemon that forks and exits; fix the command to stay in the foreground or run the orchestrator-recommended entrypoint. Nonzero exits: read `docker logs` first, then `docker inspect --format '{{.State.ExitCode}} {{.State.Error}}'`. On flapping under `--restart always`, check boot-time dependencies (database not yet ready - Chapter 9's `service_healthy` pattern) and OOM kills (`OOMKilled: true`, raise limits or fix the leak).

## C.6 Image pull fails: rate limits, auth, and mirrors

`toomanyrequests` on a shared IP means Docker Hub's anonymous pull window is exhausted: authenticate (`docker login` with an access token), route through a pull-through mirror in daemon.json, or pre-pull in CI. 401/403 on private images is credential scope - check `docker login` for the right registry (auths are per-registry in `~/.docker/config.json`) and that the token has pull scope. certificate signed by unknown authority on internal registries means the host lacks the registry's CA (install it system-wide) or the registry is plain HTTP (add it to insecure-registries only if you own the network path). Behind corporate proxies, also configure the daemon's proxy environment - the CLI's proxy is not enough for pulls.

## C.7 Logs are missing, huge, or unreadable

No logs at all: the app writes to files inside the container instead of stdout - fix the application or symlink its log path to /dev/stdout in the image. Logs vanish after rotation: `--tail` and `-f` only see current files; for durable history you need a shipping driver (Chapter 12). Disk filling: see C.1. `docker logs` unsupported on this container: the driver is a shipping one or none; read logs at the destination, or run a sidecar agent. And remember the timezone: timestamps in logs are usually UTC - compare like with like before declaring an outage window.

## C.8 Cannot connect to the Docker daemon

`Cannot connect to the Docker daemon at unix:///var/run/docker.sock` - work the ladder: is the service running (`systemctl status docker`)? What does the journal say (`journalctl -u docker -n 50`)? Are you in the docker group (or is DOCKER\_HOST pointing at the right socket, as in rootless setups)? After a failed daemon.json edit, the fix is usually visible in the journal's JSON parse error - validate with `dockerd --validate --config-file /etc/docker/daemon.json`. With live-restore enabled, running containers survive daemon downtime; without it, they die with it - one more reason the Chapter 2 baseline exists.

## C.9 Build cache bloat and slow builds

Builds creep and the builder eats gigabytes. Inspect with `docker buildx du`, prune stale cache with `docker buildx prune -f --keep-storage 5g`, and fix the structural causes: a polluted build context (`.dockerignore`), dependency layers above source copies (Chapter 5), and cache mounts that never hit because instructions changed wording between builds. On CI, confirm the cache backend is actually being imported (`cache-from` present, hit lines in the log) - a silently ignored backend flag is the most common cause of pipelines that rebuild the world on every commit.

## C.10 Graceful shutdown does not happen

Containers receive SIGKILL 10 seconds after `stop` instead of draining. Work the chain: does PID 1 forward signals (`docker exec N ps -o pid,cmd -p 1` - a shell wrapping the app does not, so run the app directly or add `--init`)? Does the app handle SIGTERM at all (test with `docker exec N kill -TERM 1` and watch the logs)? Is the grace period simply too short for the workload (`docker stop -t 30`)? Then encode the finding: exec-form ENTRYPOINT in the Dockerfile, `stop_grace_period` in Compose, `-t` in scripts - and keep the Chapter 3 staging drill in the release checklist so regressions surface before production traffic finds them.
