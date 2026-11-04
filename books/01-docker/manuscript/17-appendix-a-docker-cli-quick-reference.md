# Appendix A - Docker CLI Quick Reference {#appA}

The commands below are the working set this book used, grouped the way memory works: by object. Flags shown are the ones worth memorizing; `docker <command> --help` is the honest full reference.

| Command | Purpose |
| --------------------- | ----------------------------- |
| docker run -d --name N -p H:C -e K=V IMG | Create and start, detached, named, published, configured |
| docker ps -a / docker ps --filter name=X | List containers (all / filtered) |
| docker exec -it N sh | Open a shell in a running container |
| docker logs -f --tail 100 N | Follow recent output |
| docker stats / docker top N | Resource snapshot / process tree |
| docker stop -t 20 N / docker kill N | Graceful stop (SIGTERM then SIGKILL) / immediate SIGKILL |
| docker rm N / docker rm -f N | Remove (stopped) / force-remove running |
| docker restart N / docker pause N | Restart / freeze all processes |
| docker inspect --format '{{...}}' N | Extract any field with Go templates |
| docker events --since 1h | Daemon audit tape |

: Table A.1 - Container lifecycle

| Command | Purpose |
| --------------------- | ----------------------------- |
| docker pull / push NAME[:TAG] | Fetch / publish an image |
| docker images --digests | Local images with immutable digests |
| docker image history IMG | Layer-by-layer build receipt |
| docker image inspect IMG | Config, metadata, platform |
| docker save IMG -o f.tar / docker load -i f.tar | Move images as archives |
| docker tag IMG TARGET | Retag for another registry |
| docker image prune [-a] [-f] | Reclaim dangling (or all untagged) layers |

: Table A.2 - Images and registries

| Command | Purpose |
| --------------------- | ----------------------------- |
| docker volume create/inspect/ls/Prune | Manage volumes (prune needs -f) |
| docker network create --driver bridge NAME | Create a user-defined bridge |
| docker network connect/disconnect NET N | Attach/detach a running container |
| docker network inspect NET | Members, addresses, options |
| docker system df -v | Full disk accounting |
| docker system prune -f --filter until=168h | Scheduled hygiene, age-bounded |
| docker info / docker version | Effective config / component versions |

: Table A.3 - Storage, networking, system

| Command | Purpose |
| --------------------- | ----------------------------- |
| docker compose up -d [--wait] | Converge the stack (gate on health) |
| docker compose ps / logs -f SVC | Status with health / follow a service |
| docker compose exec SVC sh | Shell into a service container |
| docker compose pull / down [-v] | Refresh images / tear down (+volumes) |
| docker compose config | Render and validate the merged file |
| docker buildx build --platform A,B --push | Multi-platform build and publish |
| docker buildx build --secret id=I,src=F | Mount a build secret |
| docker buildx bake | Execute a multi-target build plan |
| docker buildx imagetools inspect IMG | Manifest list and attestations |

: Table A.4 - Compose and buildx
