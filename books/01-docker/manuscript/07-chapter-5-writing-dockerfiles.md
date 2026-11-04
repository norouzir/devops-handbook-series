# Chapter 5 - Writing Dockerfiles {#ch5}

The Dockerfile is where most of your engineering judgment about Docker lives. It is a short program whose output is a production artifact, and every line has a cost in build time, image size, or attack surface. This chapter covers the instructions that matter, the caching behavior that governs build speed, and the multi-stage pattern that separates build-time dependencies from runtime surfaces.

## 5.1 The Build Context and .dockerignore

Every build starts by sending the build context - the directory you point at - to the builder. Everything in it is eligible to be copied, which is why builds from a polluted directory are slow and why secrets in the context have a way of ending up in images. The `.dockerignore` file, placed next to the Dockerfile, prunes the context: version control directories, dependency caches, build outputs, local configuration, and anything secret-shaped (`*.env`, `*.pem`, `id_rsa*`) belong in it from day one. Think of it as the container-world equivalent of `.gitignore`, with worse consequences for forgetting it.

```
# .dockerignore - a sane starting point
.git
.gitignore
node_modules/
__pycache__/
*.pyc
build/
dist/
.env*
*.pem
*.key
Dockerfile*
docker-compose*.yml
README.md
```

## 5.2 The Instructions That Matter

Half of Dockerfile fluency is knowing the instruction set precisely; the other half is knowing which form of each instruction to use. The table below is the working set - everything else is either deprecated (`MAINTAINER`), niche (`ONBUILD`), or so rare you can learn it when you meet it.

| Instruction | Purpose | Notes that matter |
| --------- | -------------------- | --------------------- |
| FROM | Base image; AS name labels a stage | Pin tags, prefer slim bases; FROM scratch for static binaries |
| RUN | Execute commands in a new layer | Shell form by default; chain with && and clean caches in the same layer |
| CMD | Default command for the container | Overridable at docker run; usually exec form |
| ENTRYPOINT | Fixed executable; CMD becomes its default args | The pair defines image behavior; see 5.3 |
| COPY | Copy files from context into the image | What you want 95 percent of the time |
| ADD | COPY plus tar extraction and remote URLs | Use only for local tar auto-extraction |
| ENV | Persistent environment variables | Visible at runtime; do not bake secrets here |
| ARG | Build-time only variable | Scopes to the stage; reachable in FROM since 17.05 |
| WORKDIR | Sets working directory (and creates it) | Use absolute paths; avoids RUN cd chains |
| USER | User for subsequent RUN/CMD | Create the user explicitly; never ship as root |
| EXPOSE | Documents intended ports | Documentation only - publishing is -p |
| VOLUME | Declares a mount point | Forces anonymous volumes; often omitted in favor of Compose |
| HEALTHCHECK | Periodic health probe | Paired with orchestrators and compose --wait |
| STOPSIGNAL | Signal sent on stop | Default SIGTERM; some apps need SIGINT or SIGQUIT |
| SHELL | Changes the shell for shell-form RUN | Handy for fail-fast pipelines on Windows images |

: Table 5.1 - Dockerfile instructions in daily use

## 5.3 CMD, ENTRYPOINT, and the Two Forms

Shell form (`RUN npm install`) wraps your command in `/bin/sh -c`, which is convenient but means signals arrive at the shell, not your process - the PID 1 problem from Chapter 3 begins here. Exec form (`CMD ["nginx", "-g", "daemon off;"]`) runs the binary directly so it becomes PID 1 and receives SIGTERM itself; prefer exec form for CMD, ENTRYPOINT, and long-running processes. The CMD/ENTRYPOINT partnership follows one pattern in 90 percent of images: ENTRYPOINT is the program, CMD is its default arguments, and `docker run image --help` replaces only the CMD. That is why `docker run alpine:3.20 ls -la` works - `/bin/sh` is the entrypoint, `ls -la` the argument.

```
# the standard pattern: fixed program, replaceable arguments
ENTRYPOINT ["/app/server"]
CMD ["--config", "/etc/app/config.yaml"]

# docker run myapp            -> /app/server --config /etc/app/config.yaml
# docker run myapp --dev      -> /app/server --dev
```

## 5.4 Layer Caching and Instruction Ordering

BuildKit caches each instruction's result keyed by the instruction text and the content involved. A layer is invalidated when its input changes, and every later layer is invalidated with it - so the shape of a fast Dockerfile is always the same: least-frequently-changing instructions first, dependency manifests before source code, source before anything build-specific. A Node project that copies `package.json` and installs before copying the rest changes only the final cheap layers when you edit application code. The same logic explains why `RUN apt-get update && apt-get install -y --no-install-recommends pkg && rm -rf /var/lib/apt/lists/*` lives in one RUN: splitting it across lines bakes the package index into a layer forever, no matter what you delete later.

```
# order = cache strategy
COPY package.json package-lock.json ./
RUN npm ci --omit=dev          # invalidated only when dependencies change
COPY src/ ./src/               # invalidated on every code edit - cheap layers only
RUN npm run build
```

## 5.5 Multi-Stage Builds

Multi-stage builds are the single most valuable Dockerfile technique: compile in a fat stage that has compilers and toolchains, then copy only the artifacts into a minimal final stage that ships. The result is a small image with a small attack surface, and the build cache still benefits from every stage. A static Go binary needs nothing more than `FROM scratch` at the end; interpreted stacks land on `alpine` or a slim Debian; hardened environments use distroless images that contain only the runtime and nothing to log into.

```dockerfile
# build stage: heavy toolchain
FROM golang:1.23 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download            # cached unless dependencies change
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app ./cmd/app

# runtime stage: minimal surface
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
USER nonroot:nonroot
ENTRYPOINT ["/app"]
```

::: {.note}
**Best practice**

Name stages with AS and reference them in COPY --from. Run `docker image history <image>` after each size-focused change: the layer list is an honest receipt of what you shipped, and build dependencies that sneak into the final stage show up there immediately.
:::

## 5.6 Healthchecks, Users, and Small Non-Negotiables

A production-grade Dockerfile carries a handful of non-negotiables that teams should enforce in review. Declare a `HEALTHCHECK` whose probe reflects real service health rather than process liveness. Create and switch to an application user (`USER app`) so the container does not run as UID 0. Set `ENV` defaults that make the image runnable with zero configuration. Pin base image tags to a specific version and plan base updates deliberately, ideally driven by automated PRs from a dependency bot. Finally, prefer `COPY` over `ADD` except for auto-extracting local tars, and never `COPY` secrets - the next chapter shows the proper mechanism.

```
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

RUN addgroup -S app && adduser -S app -G app
USER app
```

## 5.7 Bootstrapping with docker init

For greenfield projects, `docker init` inspects the repository and generates a sensible Dockerfile, `.dockerignore`, and Compose file for the detected language and framework. Treat its output as a first draft to review with this chapter's checklist in hand - the generated files are deliberately conservative and will not know your specific caching needs or your distroless policy. Used that way, it removes the blank-page problem without removing the thinking.

::: {.lab}
### Lab 5 - Build it lean {#lab5}

1. Write a Dockerfile for a small web service in the language of your choice, applying manifest-first ordering and a non-root USER.
2. Build and record the size: `docker build -t lab5:v1 .` then `docker images lab5`. Run `docker image history lab5:v1` and find the heaviest layer.
3. Convert the build to multi-stage with a minimal runtime stage, rebuild as `lab5:v2`, and compare sizes and histories.
4. Add a HEALTHCHECK, then prove caching works: touch a source file, rebuild, and observe which layers say CACHED and why the dependency layers do not rebuild.
:::

**See also:** [Chapter 6](#ch6) for the builder that executes these instructions, [Appendix B](#appB) as a review checklist, and [Chapter 10](#ch10) for the security half of image design.
