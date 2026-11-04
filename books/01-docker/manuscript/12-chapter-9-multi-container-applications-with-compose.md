# Chapter 9 - Multi-Container Applications with Compose {#ch9}

Real applications are never one container: an API needs a database, a cache, maybe a queue. Compose is the tool that describes such stacks as code - one YAML file per project, one command to converge reality onto it. It ships as the `docker compose` CLI plugin you installed in Chapter 2, its specification is stable, and the `version:` field at the top of old files is history: current Compose ignores it and treats the file as the latest schema.

## 9.1 A Complete, Realistic Stack

The file below is the reference example for this chapter - a web API, its PostgreSQL database, and a Redis cache, with healthcheck-gated startup, a persistent volume, a private network, and configuration injected from the environment. Every element of it is explained in the sections that follow, and the lab rebuilds it.

```yaml
services:
  api:
    build: ./api
    image: myorg/api:1.4.0
    restart: unless-stopped
    environment:
      DATABASE_URL: postgres://app:${DB_PASSWORD}@db:5432/app
      REDIS_URL: redis://cache:6379
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8080/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10

  cache:
    image: redis:7-alpine
    restart: unless-stopped

volumes:
  pgdata:

networks:
  default:
    name: myapp-net
```

## 9.2 Services: build, image, environment

Each key under `services` is a container the project will converge. `build:` points at a directory (optionally with its own `dockerfile:` and `args:`) and Compose builds it - combine `build:` with `image:` to tag the result into your registry so production never builds locally. `environment:` accepts a map or a list; values that reference `${VAR}` are interpolated from the shell or from a `.env` file sitting next to the compose file, which is where host-specific values such as passwords belong (`.env` goes straight into your `.gitignore`; commit a `.env.example` instead). `restart: unless-stopped` mirrors Chapter 3's policy, and `ports:` uses the same `-p` semantics - including the loopback-only binding shown above for anything fronted by a proxy.

## 9.3 Startup Order: depends\_on and healthchecks

`depends_on` controls convergence order, and its two forms differ in exactly the way that matters. The list form waits only for the dependency to be started (created and running) - not healthy. The map form with `condition:` waits for the dependency to report healthy (per its healthcheck), to have exited successfully (`service_completed_successfully`, for migration jobs), or merely to have started. Always pair a database dependency with `service_healthy` and a healthcheck on the database; without it, your API crashes on boot at every cold start and your restart policy turns that into a flappy loop. For orchestrated deployments, `docker compose up --wait` extends the discipline to the whole stack: the command returns nonzero unless every service is healthy, which is precisely what a deploy script should demand.

## 9.4 Projects, Commands, and Daily Workflow

A Compose project is the set of resources named by the directory (or `COMPOSE_PROJECT_NAME` / `-p flag`), and all resource names are prefixed with it - which is why two checkouts of the same repository can run side by side. The daily command set is small and worth drilling until automatic:

```bash
docker compose up -d          # converge the stack (build if needed)
docker compose up -d --wait   # converge and gate on health
docker compose ps             # status with health column
docker compose logs -f api    # follow one service
docker compose exec api sh    # shell into a running service
docker compose pull           # refresh images from the registry
docker compose down           # stop and remove containers+networks
docker compose down -v        # ...and volumes - destructive, think twice
```

Two workflow habits prevent most Compose surprises. First, treat the file as code: review changes to it like any other pull request, because `docker compose up -d` applies diffs (recreated containers, new networks) exactly like a deploy. Second, remember that `down` and `up` preserve named volumes but not anything in the writable layers or in containers' anonymous volumes; experiments live in projects you `down -v` without ceremony.

## 9.5 Profiles, Overrides, and Secrets

Three composition features keep one file honest across environments. **Profiles** mark optional services (`profiles: ["debug"]`) that only start when their profile is activated (`docker compose --profile debug up`), which keeps tooling containers out of production files without a second file. **Override files** merge on top of the base: Compose automatically loads `compose.override.yaml`, and explicit stacks of `-f base.yml -f prod.yml` express environment deltas; put the 90 percent in the base and the deltas in thin overrides rather than forking whole files. **Secrets** give services files instead of environment variables: declare top-level secrets, source them from files outside the project, and read them from the mounted path inside the container - the application support varies, but the pattern (read from a file, never from the environment) is what Chapter 10 generalizes.

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt

services:
  api:
    secrets:
      - db_password
    # inside the container: /run/secrets/db_password
```

## 9.6 Development with watch

Compose `watch` closes the inner development loop without hammering rebuilds. Services declare `develop.watch` rules mapping host paths to actions: `sync` copies changes into the running container (no restart), `rebuild` triggers an image rebuild when tracked files change, and `sync+restart` combines both. For interpreted applications, a sync rule on the source directory plus a rebuild rule on dependency manifests gives the best of bind mounts and images - and avoids the cross-VM bind-mount penalty on Desktop by keeping the source inside the container:

```yaml
services:
  api:
    build: ./api
    develop:
      watch:
        - action: sync
          path: ./api/src
          target: /app/src
        - action: rebuild
          path: ./api/package.json
# docker compose watch   (not up) starts this mode
```

::: {.lab}
### Lab 9 - Three services, one file {#lab9}

1. Write a compose.yaml for api + db + cache modeled on Section 9.1 (any small image works as the api; a busybox sleep loop is fine for the lab), with a healthcheck on db and `depends_on: service_healthy`.
2. Create a `.env` with `DB_PASSWORD`, reference it via interpolation, and verify with `docker compose config` that interpolation resolved.
3. Bring the stack up with `--wait`, then break the db healthcheck and observe `up --wait` failing with a nonzero exit - that failure is your future deploy script's safety net.
4. Exercise the workflow: `ps`, `logs -f`, `exec`, `pull`, then `down` and `down -v`, explaining aloud what each removed and what would have survived.
:::

**See also:** [Chapter 7](#ch7) and [Chapter 8](#ch8) for the storage and network primitives a compose file wires together, and [Chapter 13](#ch13) for compose files in delivery.
