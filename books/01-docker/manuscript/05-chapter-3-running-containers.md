# Chapter 3 - Running Containers {#ch3}

Everything a container does in its lifetime - starting, being observed, being limited, being stopped - happens through a handful of commands. The skill to build in this chapter is not memorizing flags but understanding the lifecycle: what the daemon does on `run`, what your process sees as PID 1, what happens on `stop`, and why containers die the way they die. Get this chapter right and the rest of Docker becomes pattern recognition.

## 3.1 The Anatomy of docker run

`docker run` is really three commands in one: `docker create` (prepare a container filesystem from an image), `docker start` (boot it), and `docker attach` (only if you asked for foreground). The image below is the reference example this chapter returns to - an nginx web server, detached, named, port-mapped, resource-limited, and with a restart policy:

```bash
docker run -d \
  --name web \
  --restart unless-stopped \
  -p 8080:80 \
  -e NGINX_ENTRYPOINT_QUIET_LOGS=1 \
  --memory 512m --cpus 1.0 --pids-limit 200 \
  nginx:1.27-alpine
```

Read the flag groups as sentences: `-d` detaches, `--name` fixes the generated name (always do this in anything but throwaway experiments), `-p 8080:80` publishes the container port 80 on host port 8080, `-e` injects configuration, and the resource flags cap memory, CPU, and process count via cgroups. If the image is not present locally, the daemon pulls it first - which is why the first run is slower and why Chapter 4 on registries matters before any of this works offline.

## 3.2 Foreground, Detached, and Interactive Usage

Three invocation styles cover every situation. Foreground with a pseudo-terminal, `docker run -it --rm alpine sh`, gives you a throwaway shell that disappears cleanly on exit thanks to `--rm` - the classic debugging pattern. Detached mode with `-d` is how services run; inspect them with `docker logs` and `docker ps` instead of staring at a console. The hybrid is `docker run -d -it` for processes that insist on a TTY, and `docker exec -it web sh` to open an additional shell inside a running container. Keep one principle in mind: the container lives and dies with its main process (PID 1). When that process exits, the container exits, no matter how many other processes are still inside.

## 3.3 Signals, PID 1, and Graceful Shutdown

`docker stop web` sends SIGTERM to PID 1 and, after a grace period (`-t`, default 10 seconds), escalates to SIGKILL. Graceful shutdown therefore depends entirely on what your main process does with SIGTERM. Two classic problems bite engineers here. First, applications written as shell scripts or poorly-written wrappers may not forward signals to their children, so the child keeps running while PID 1 dies and the container gets SIGKILLed mid-request; the fix is an init process such as `tini` or `--init`, which forwards signals and reaps zombies. Second, processes that ignore SIGTERM get terminated hard after the grace period - tune `-t` upward for apps with long shutdown work such as draining connections.

```
# the pattern: docker stop = SIGTERM, wait, SIGKILL
docker stop -t 30 web        # give a slow-draining app 30 seconds

# inspect what your PID 1 actually is
docker exec web ps -o pid,ppid,cmd -p 1

# run the same container with a minimal init to forward signals
docker run -d --name web-init --init nginx:1.27-alpine
```

::: {.note}
**Best practice**

Treat SIGTERM handling as a feature you test, not assume. In staging, send `docker stop` to a container under load and watch request logs: connections should drain, not reset. The Dockerfile-side companion of this story (STOPSIGNAL, ENTRYPOINT discipline) is in Chapter 5.
:::

## 3.4 Restart Policies

A restart policy tells the daemon what to do when a container exits, and choosing among the four options is a deliberate availability decision. `no` (the default) never restarts; `on-failure[:N]` restarts on nonzero exits up to N times; `always` restarts every exit including daemon restarts; `unless-stopped` behaves like `always` but respects a manual stop across daemon restarts. For services, `unless-stopped` is the pragmatic default: it survives reboots and crashes but still lets a human stop a misbehaving container without the daemon fighting back. Restart policies are not health management - a process can hang forever inside a healthy-looking container. The bridge from process supervision to actual availability is the HEALTHCHECK mechanism (Chapters 5 and 9) plus orchestrators once you truly need self-healing at fleet scale.

## 3.5 Observing Containers: logs, stats, top, inspect

Four commands answer almost every live question. `docker logs -f --tail 100 web` follows recent output - remember this is whatever the container wrote to stdout and stderr, shaped by the logging driver (Chapter 12). `docker stats` renders a live CPU, memory, and network table and is the fastest way to spot a runaway neighbor; `docker stats --no-stream` gives a single snapshot suitable for scripts. `docker top web` shows the process tree as the host sees it, which is how you notice that a container is running five processes when its image promised one. `docker inspect web` is the source of truth for configuration, and its `--format` flag turns it into a scriptable extractor:

```bash
docker inspect --format '{{.State.Status}} oom={{.State.OOMKilled}} exits={{.State.ExitCode}}' web
docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' web
docker events --since 10m --until 0s --filter container=web
```

The exit code deserves special attention because it is your first diagnostic. 125 means the daemon itself failed to run the container (bad flags, missing image), 126 a command inside could not be invoked, 127 a command was not found, and anything else is your application's own exit code. `docker ps -a` with its status column - Up, Exited (0), Exited (137) - is a tape of recent history, and Exit 137 almost always means SIGKILL, either from `docker kill`, from the grace period expiring, or from the kernel OOM killer because you under-provisioned memory.

## 3.6 Resource Limits and the OOM Killer

Unlimited containers are a shared-host hazard: one leaky process degrades every neighbor. Set limits by default - `--memory` for the hard ceiling, `--memory-swap` (defaulting to twice the memory limit) for the total of RAM plus swap, `--cpus` as a fraction of available cores, and `--pids-limit` to cap process explosions. When a container crosses its memory ceiling, the kernel OOM killer terminates it and the container shows Exited (137) with `OOMKilled: true` in inspect. That is the system working as designed, but it is also a signal to right-size the limit or fix the leak; silently raising limits is how you end up rebuilding the host. On cgroup v2 hosts the accounting is per-container and precise, so trust `docker stats` when capacity planning and set limits in Compose files and pipeline manifests rather than ad hoc on the command line.

::: {.lab}
### Lab 3 - Lifecycle drill {#lab3}

1. Run `docker run -d --name web --restart unless-stopped -p 8080:80 --memory 512m --cpus 1 nginx:1.27-alpine`, then verify with `docker ps` and `curl localhost:8080`.
2. Kill PID 1 with `docker exec web kill 1` and watch the container exit and restart thanks to the policy; explain the new container start count in `docker inspect --format '{{.RestartCount}}' web`.
3. Run a memory hog (`docker run --rm --memory 100m polinux/stress --vm 1 --vm-bytes 250M`) and observe the exit code 137; confirm OOMKilled with `docker inspect` on a detached copy.
4. Practice graceful versus hard shutdown: `docker stop -t 2 web`, then `docker kill web`, and compare the exit codes. Write down which one you would allow against production and why.
:::

**See also:** [Chapter 4](#ch4) for where these images actually come from, [Chapter 7](#ch7) for the data that outlives the container, and [Chapter 8](#ch8) for how containers reach each other.
