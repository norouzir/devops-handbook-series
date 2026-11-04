# Chapter 13 - Docker in CI/CD and Production Operations {#ch13}

Everything before this chapter is craft; this chapter is the factory. A Docker pipeline builds, tests, scans, publishes, and deploys images the same way every time, records what it produced, and leaves the host clean enough to do it again tomorrow. The pattern below is deliberately tool-shaped around GitHub Actions because it is the most common CI you will meet, but the skeleton transfers to GitLab CI, Jenkins, and anything else with an executor and secrets.

## 13.1 The Canonical Pipeline

Five stages, always in this order, each with a crisp gate. **Build**: construct the image with buildx, with cache imported from a backend so builds are seconds, not minutes. **Test**: run the unit and integration suites inside the container - tests against the image, not just the source tree, so what passes is what ships. **Scan**: Trivy or Scout blocks on CRITICAL/HIGH findings; this gate is policy, not advice. **Push**: publish to the registry with a meaningful tag, `--provenance` and `--sbom` attestations attached, and cache exported for the next run. **Deploy**: pull the exact digest on the target and converge, gated on healthchecks (Compose `--wait`, Swarm rolling updates, or a GitOps controller on Kubernetes). Every stage emits artifacts and logs to the pipeline, and no stage ever depends on untracked state on the runner - disposable builders plus cache backends (Chapter 6) are what make that honest.

## 13.2 A Reference GitHub Actions Workflow

The workflow below is a compact but complete build-scan-push for a multi-platform image. Read the flags against Chapter 6 - every one of them has a home in your head already:

```
name: build-and-push
on:
  push:
    tags: ["v*"]

jobs:
  ship:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          provenance: mode=max
          sbom: true
          tags: |
            ghcr.io/acme/app:${{ github.ref_name }}
            ghcr.io/acme/app:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: vulnerability gate
        run: |
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
            aquasec/trivy image --exit-code 1 \
            --severity CRITICAL,HIGH ghcr.io/acme/app:${{ github.ref_name }}
```

## 13.3 Caching Strategy in CI

CI runners are ephemeral, so cache must be imported and exported on purpose. Three backends cover the field: `type=gha` for GitHub Actions (fast, scoped to the repository), `type=registry` with a dedicated cache tag (works everywhere, survives runner pools, uses your registry storage), and `type=inline` (metadata embedded in the pushed image - minimal but free). Pick one per pipeline, use `mode=max` so intermediate stages cache, and keep the Dockerfile cache-friendly per Chapter 5 - no backend rescues a Dockerfile that copies source before dependencies. Remember also that cache mounts (Section 6.3) live in the builder, not the cache backend: on fresh CI builders they are cold every run, which is exactly why the manifest-first ordering still matters.

## 13.4 Tags, Digests, and Promotion

A tagging scheme is a promise about reversibility. The workable standard: immutable semver tags for releases (`1.4.0`, `1.4`, `1` as moving convenience tags), the git SHA for every build (traceability from container back to commit), and `latest` only as a human convenience that nothing automated consumes. Deployments then pin **digests** - `myorg/app@sha256:...` - because the digest is the only value that cannot change underneath you; your deploy artifact (compose file, stack file, or Kubernetes manifest) records it, and the change ticket cites it. Promotion between environments moves the same digest through dev, staging, and production gates rather than rebuilding per environment: one build, many deployments. If you cannot answer exactly what runs in production within one command, the tagging scheme is broken - fix it before the next incident fixes it for you.

## 13.5 Deploying with Compose in Production

For estates that run Compose on hosts rather than an orchestrator, the deployment loop is a short, auditable script - and its health gate is the part teams skip at their peril:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /srv/myapp

docker compose pull                 # fetch the pinned images
docker compose up -d --wait         # converge, gate on healthchecks
docker image prune -f               # drop dangling layers from this deploy

# rollback = previous tag in .env, then repeat pull + up -d --wait
```

`--wait` returns nonzero unless every service is healthy, so the script fails loudly instead of green-lighting a broken deploy; the rollback path is the same script pointing at the previous tag, and rehearsing it is a lab exercise below. Zero-downtime on a single host needs a proxy front (nginx, Traefik, Caddy) plus either blue-green project pairs or orchestration - Swarm and Kubernetes make the pattern native, and that is one more signal in the Table 11.1 decision. Whatever fronts the containers, keep the loop pull-converge-verify boring and identical on every host; the moment a host has a special deploy path, you have two production environments to remember.

## 13.6 Disk Hygiene, live-restore, and Upgrade Discipline

Production Docker hosts fail in boring ways, and three disciplines prevent most of them. **Disk hygiene**: schedule `docker system prune -f --filter until=168h` weekly on non-build hosts (never blanket `-a` on CI runners during working hours - Chapter 4), configure the builder's own garbage collection in daemon.json (`builder.gc` policy), rotate logs per Chapter 12, and alert on data-root usage at 80 percent. **live-restore**: keep it enabled (Chapter 2) so daemon restarts and upgrades do not take workloads down, and verify it works after every upgrade - it is the difference between a maintenance window of minutes and one of hours. **Upgrade discipline**: monthly engine patch cadence, release-note reading for major versions (v28 and v29 both changed defaults you rely on), digest-recorded deploys before and after, and one canary host before the fleet. None of this is glamorous; all of it is why some Docker fleets are quiet and others are on call.

## 13.7 The Production Readiness Checklist

Before a service earns production traffic, walk this list - it condenses Chapters 2 through 13 into one page, and Appendix B extends the Dockerfile half of it:

| Area | Requirement | Chapter |
| ----------- | -------------------------------- | ------- |
| Image | Multi-stage build, pinned base, non-root USER, HEALTHCHECK | 5, 6 |
| Supply chain | Scanned (Scout/Trivy), provenance and SBOM attached, digest-pinned deploy | 6, 10, 13 |
| Runtime | Memory/CPU limits, restart policy, --read-only and no-new-privileges where feasible | 3, 10 |
| Storage | Named volumes for state; backup and restore rehearsed | 7 |
| Networking | User-defined networks, loopback-only publishes behind a proxy, DOCKER-USER rules reviewed | 8 |
| Daemon | daemon.json baseline (logs, live-restore), rootless or userns-remap where applicable | 2, 10 |
| Observability | Log driver with rotation, cAdvisor/Prometheus metrics, health alerts | 12 |
| Operations | Deploy script with health gate, tested rollback, prune schedule, upgrade cadence | 13 |

: Table 13.1 - Production readiness checklist

::: {.lab}
### Lab 13 - The full loop {#lab13}

1. Set up the GitHub Actions workflow of Section 13.2 (or its GitLab equivalent) against a demo repository; watch build, attestations, and the Trivy gate run on a tag push.
2. Deploy the pushed image to a VM with the Section 13.5 script; break the healthcheck and confirm the script fails with a nonzero exit instead of reporting success.
3. Rehearse rollback: deploy tag v1, then v2, then roll back to v1 by editing the pinned tag and rerunning the script; time yourself - that number is your real recovery point.
4. Audit the host after a week of deploys: `docker system df`, then add the weekly prune cron and the builder.gc policy, and verify usage stabilizes.
:::

**See also:** [Chapter 6](#ch6) for the builds a pipeline runs, [Chapter 10](#ch10) for the scanning and signing steps to add.
