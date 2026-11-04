# Chapter 5 - Container Image Security: Minimal Bases and Trivy {#ch5}

## 5.1 The Image Is the Attack Surface

Everything in a container image is attack surface that ships to production. The image the Docker book built to *learn* on - `FROM ubuntu`, one `apt-get install` per tool "just in case", a curl left in the final layer - contains hundreds of OS packages, each with its own CVE backlog, each installed forever because layers never shrink. The **XZ Utils backdoor** from [Chapter 1](#ch1) is the sharpest illustration of why that matters: xz was a build-time dependency of essentially nothing in most images, yet it sat installed in countless production containers as dead weight, one supply-chain compromise away from being executed. An image you do not need packages in is an image you do not need to patch, scan, and worry about. Minimalism here is not aesthetic; it is the control.

## 5.2 Building Less Image: Multi-Stage and Distroless

The Docker book covered multi-stage builds as a size optimization; this chapter applies the same technique as a security one. The pattern is identical - one build stage with compilers and package managers, one final stage with only the artifact - and the payoff doubles: the final image contains no build tooling for an attacker to exploit and dramatically fewer packages to patch:

```dockerfile
# --- build stage: everything ugly is allowed here ---
FROM golang:1.25 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/shopnow ./cmd/server

# --- final stage: distroless, non-root, nothing else ---
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/shopnow /shopnow
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/shopnow"]
```

**Distroless** base images contain no shell, no package manager, and no utilities - just the language runtime and the OS libraries the binary links against. The tradeoffs are honest and manageable: debugging means ephemeral sidecars (`kubectl debug` from the Kubernetes book) rather than `kubectl exec sh`, because there is no `sh` to exec. The **`nonroot`** variant plus the explicit `USER` directive completes the control: a compromised process in the pod runs as a random high UID with no shell, no tooling, and write access to nothing - which converts an entire class of container-escape primers (download payload, execute, plant persistence) into a dead end. `.dockerignore` (never ship `.git`, `.env`, test fixtures, or CI configs into any stage) and digest-pinned base images (`FROM ...@sha256:...` for the builds that matter) round out the build-time discipline; the Docker book's Dockerfile checklist appendix is the full reference.

::: {.note}
**Best practice - the base image is a dependency, so track it like one**

A pinned `FROM golang:1.25@sha256:...` is reproducible, but it also rots: when the base image's maintainers patch a CVE and publish a new digest, your pin keeps building the old, vulnerable one. The fix is automation, not attention: Dependabot's `docker` ecosystem (from [Chapter 4](#ch4)) opens a pull request when the base image digest moves, and the CI pipeline rebuilds `shopnow` on that PR. Images do not patch themselves; they get *rebuild* events, and those events belong in the same review loop as code changes.
:::

## 5.3 Trivy: One Scanner for Everything the Image Contains

**Trivy** has become the default open-source scanner across the series' ecosystem for a simple reason: one binary scans container images, filesystems, git repositories, lockfiles, Kubernetes manifests, and Terraform code, against consolidated vulnerability, secret, and misconfiguration databases. In this chapter it scans images; [Chapter 10](#ch10) reuses it for IaC. Install per platform, then scan:

```bash
trivy image shopnow:latest --severity HIGH,CRITICAL
trivy image --ignore-unfixed --exit-code 1 --severity CRITICAL shopnow:latest
trivy image --format sarif --output trivy.sarif shopnow:latest   # for code-scanning upload
```

The flag discipline is the whole methodology. `--ignore-unfixed` reports only vulnerabilities with an actual fixed version available (upstream-unfixed findings otherwise bury the actionable ones). `--exit-code 1 --severity CRITICAL` is the CI gate - the scan fails the build exactly when the policy says it must, which is the "gate on severity, report on the rest" principle from [Chapter 1](#ch1) made mechanical. Scanners produce false positives; `.trivyignore` accepts them *explicitly*, one `CVE-ID` per line with a comment holding the reason and review date, so an accepted risk is a reviewed artifact rather than a shrug.

## 5.4 Registry Hygiene and the Rebuild Reflex

Scanning belongs at three moments, and they are cheap because they share one database. **At build**: the gate above, before anything is pushed. **At rest**: the registry or a scheduled scanner re-scans published images daily, because CVEs are discovered *after* images ship - yesterday's clean image ages into a vulnerable one without changing a byte. **At admission**: the cluster re-checks on deploy, which is [Chapter 8](#ch8)'s job. GitHub Container Registry pairs with the dependency-review flow natively, and Trivy's scheduled GitHub Actions run (a weekly `cron` workflow from the GitHub Actions book) covers the at-rest scan for private registries.

The companion habit is the **rebuild reflex**: images are cattle, not pets, and the production pattern is to rebuild and redeploy `shopnow` on every base-image update and every CVE fix, not to patch running containers. An environment where any instance can be killed and replaced at any time from a fresh, scanned image (the Kubernetes book's deployments) is an environment where patching is a pipeline run rather than a change window.

::: {.lab}
### Lab 3 - Shrink the Image, Clean the Scan {#lab3}

1. Build the *before* image: `docker build` the legacy `shopnow` Dockerfile (single-stage `FROM ubuntu:latest`, `apt-get install curl git vim build-essential` plus the app). Record size (`docker images`) and run `trivy image shopnow:legacy --ignore-unfixed -s HIGH,CRITICAL --summary`. Note the package count and CRITICAL/HIGH numbers.
2. Rebuild with the multi-stage distroless Dockerfile from this chapter (adapt the build stage to `shopnow`'s actual language from the Docker book). Record size again - expect roughly an order of magnitude drop - and confirm `USER nonroot` is in the final stage.
3. Scan the new image with the CI gate flags. If CRITICAL findings remain, read them: they are in the base image's OS packages, so fix by moving the base image to the current digest (simulate the Dependabot PR) and rescan. Target: zero CRITICAL, zero HIGH with `--ignore-unfixed`.
4. Prove the hardening: `docker run --rm shopnow:hardened sh` must fail with `exec: "sh": executable file not found` (distroless), and `id` inside the running process must show a non-root UID. The controls are real only when they are demonstrated.
5. Add the Trivy gate step to `shopnow`'s publish workflow from the GitHub Actions book: install Trivy, scan the built image with `--exit-code 1 --severity CRITICAL --ignore-unfixed`, and only then push. Commit `.trivyignore` with one deliberately accepted finding to practice the explicit-acceptance flow.
:::

**See also:** [Chapter 6](#ch6) gives the clean image a verifiable identity - signing and an SBOM; [Chapter 8](#ch8) enforces the scan at admission; the Docker book's best-practice checklist holds the full Dockerfile reference this chapter builds on.
