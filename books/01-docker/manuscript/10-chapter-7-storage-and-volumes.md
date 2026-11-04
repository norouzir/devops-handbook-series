# Chapter 7 - Storage and Volumes {#ch7}

Containers are disposable by design, which makes storage the discipline of deciding precisely what survives their disposal. Every serious data-loss incident with Docker reduces to the same sentence: someone confused the writable container layer with durable storage. This chapter draws the boundary and gives you the tools to place every kind of data on the correct side of it.

## 7.1 Where Data Can Live

A container sees three kinds of storage. The **image layers** are read-only and shared by every container from that image. The **writable layer** is created per container; it holds everything the process writes that is not redirected elsewhere, it disappears when the container is removed, and it is slower than the host filesystem because of the copy-on-write machinery. Everything else is a **mount**: a volume, a bind mount, or a tmpfs mount placed into the container's filesystem tree at a chosen path. The engineering decision is always the same - identify the paths your process writes to that must survive, and mount them explicitly. Modern images help by declaring VOLUME paths, but you should not rely on declarations; know your data.

## 7.2 Volumes: The Default for Durable Data

A volume is a directory on the host, under `/var/lib/docker/volumes/`, that Docker creates and manages, mounted into a container at a chosen path. Named volumes survive container removal, can be moved between containers, are backed up as ordinary directories, and can be delegated to drivers for network storage. This is the correct home for databases, queues, uploads, and every other stateful payload:

```bash
docker volume create pgdata
docker run -d --name pg \
  -v pgdata:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=lab postgres:16-alpine

# the --mount long form says the same thing, more explicitly
docker run -d --name pg2 \
  --mount type=volume,source=pgdata2,target=/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=lab postgres:16-alpine

# inspect where it lives and what it holds
docker volume inspect pgdata
```

An anonymous volume (`-v /var/lib/postgresql/data` with no name) is created when you remove a container only if you use `docker rm -v` or it goes stale as a dangling volume - which is why anonymous volumes are discouraged outside of image defaults: they are easy to orphan and hard to attribute. Label volumes as you create them and prefer names that include the service and purpose (`pgdata`, `cache-redis`) - six months from now, `docker volume ls` should read like a map, not a puzzle.

## 7.3 Bind Mounts: Host Directories Into Containers

A bind mount maps an existing host directory (or file) into the container at a chosen path. It is the tool for development - edit on the host, see the change live in the container - and for injecting configuration files you manage outside Docker. It is rarely the tool for databases in production: semantics and permissions are exactly the host's, and the container can then depend on host paths that containers were supposed to abstract away.

```
# development: live-edit source into the container
docker run -d --name dev \
  -v "$PWD":/app \
  -w /app node:20-alpine npm run dev

# read-only configuration injection
docker run -d --name web \
  --mount type=bind,src=/etc/web/nginx.conf,dst=/etc/nginx/nginx.conf,readonly \
  nginx:1.27-alpine
```

::: {.warn}
**Watch out**

On SELinux systems a bind mount into a container needs a label change: append `:z` (shared among containers) or `:Z` (private to this container) to the `-v` path. The symptom of forgetting it is `permission denied` inside the container while everything looks fine on the host - Appendix C lists it as a classic.
:::

## 7.4 tmpfs and the Decision Table

A tmpfs mount creates an in-memory filesystem for the lifetime of one container - ideal for sensitive scratch data that must never touch disk and for high-churn ephemeral writes that would wear or pollute the writable layer (`--tmpfs /run --tmpfs /tmp:rw,size=64m`). Choosing between the four kinds of storage is mechanical once you name the requirement:

| Requirement | Correct choice | Why |
| ----------------- | ------------- | -------------------- |
| Database or queue data | Named volume | Survives containers, easy backup, driver-capable |
| Live-edit source during development | Bind mount | Host edits are instantly visible |
| Config file managed outside Docker | Bind mount (read-only) | Host remains the source of truth |
| Secrets needed briefly at runtime | tmpfs or secret mount | No trace on disk after container exit |
| Cache scratch space | tmpfs or writable layer | Cheap, disposable, no durability needed |

: Table 7.1 - Choosing storage by requirement

## 7.5 Backing Up, Restoring, and Moving Data

Volumes are ordinary host directories, and their backup story is a one-liner pattern worth memorizing: run a throwaway container sharing the volume and stream a tar archive through it. The same pattern restores, and a variant copies data between volumes - which is also how you migrate a workload to a new volume or a new host:

```
# backup
docker run --rm -v pgdata:/data -v "$PWD":/backup alpine \
  tar czf /backup/pgdata-$(date +%F).tgz -C /data .

# restore into a fresh volume
docker volume create pgdata-restored
docker run --rm -v pgdata-restored:/data -v "$PWD":/backup alpine \
  sh -c "cd /data && tar xzf /backup/pgdata-2026-10-15.tgz"

# copy between volumes
docker run --rm -v src:/from -v dst:/to alpine \
  sh -c "cd /from && cp -a . /to"
```

For the databases behind real services, prefer the database's own consistent dump (pg\_dump, mysqldump, snapshot tooling) over filesystem tars of a live data directory; the tar pattern is for files, cold copies, and pre-verified consistency situations. Knowing both, and when each is legitimate, is part of the job.

## 7.6 Cleanup and the containerd Snapshotter

Storage hygiene is a scheduled task, not an emergency response. `docker volume ls -f dangling=true` lists volumes no longer referenced by any container - review before deleting, because a dangling database volume is still your data. `docker volume prune` removes all dangling volumes (add `--filter label!=keep` to protect labeled ones), `docker system df -v` shows who is consuming the data root, and the full accounting lives in `docker system prune` which you will meet again in Chapter 13 as a scheduled cron with explicit filters. On Engine v29 fresh installs the containerd snapshotter manages layer storage content-addressed; the container-level story in this chapter is unchanged, but tools that poke directly at `/var/lib/docker` internals (old backup scripts, bespoke cleanup scripts) need reworking, because that layout is now the snapshotter's business.

::: {.lab}
### Lab 7 - Make data survive {#lab7}

1. Start Postgres with a named volume as shown above, create a table with one row, then `docker rm -f pg`, recreate the container on the same volume, and prove the row survived.
2. Repeat the experiment without a volume and watch the data vanish - write down the exact commands for your runbook.
3. Bind-mount a host directory into an nginx container and edit index.html on the host; confirm the change live with curl.
4. Backup and restore: archive pgdata with the tar pattern, restore into pgdata-restored, start a new container on it, and verify the table. Finish with `docker system df -v` and prune the leftovers.
:::

**See also:** [Chapter 9](#ch9) for volumes inside a multi-container application, [Chapter 10](#ch10) for the ownership and permission rules that make mounts safe, and [Appendix C](#appC) when a bind mount comes up empty.
