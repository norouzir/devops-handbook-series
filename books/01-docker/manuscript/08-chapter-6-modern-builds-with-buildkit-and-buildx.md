# Chapter 6 - Modern Builds with BuildKit and buildx {#ch6}

The build engine you use daily is BuildKit, reached through the `buildx` CLI plugin. It replaced the classic builder years ago and its capabilities - parallel execution, content-addressable caching, secret mounting, cross-platform builds, and cryptographic attestations - are now the professional baseline. This chapter turns you from someone who runs `docker build` into someone who controls it.

## 6.1 What BuildKit Changes

BuildKit converts the Dockerfile into a dependency graph and executes independent stages in parallel, skips stages whose outputs are not needed, and caches results by content rather than by line order alone. Practical symptoms of the difference: `RUN` steps that do not contribute to the requested target never run, unchanged dependency installs are skipped outright, and output is a tidy stream of progress rather than a scroll of everything. With Engine v29 the containerd image store and BuildKit are the default pairing, which also unlocks exporting images directly to registry formats and OCI layout directories.

## 6.2 Builders and Drivers

buildx manages named **builders**. The default `docker` driver builds inside the daemon and is fine for everyday work, but it cannot do multi-platform exports or advanced cache backends. The `docker-container` driver runs BuildKit in a dedicated container - create it once, and use it whenever you need full features:

```bash
docker buildx ls                       # list builders
docker buildx create --name multi --driver docker-container --use
docker buildx inspect --bootstrap multi
docker buildx build --load -t lab6:latest .
docker buildx rm multi
```

Two driver behaviors to internalize: images built in a docker-container builder live in that builder's cache and are NOT in your local image list until you add `--load`, and CI systems typically create a fresh builder per job (the GitHub Actions integration does exactly that) so cache must be imported and exported deliberately - Section 6.7 covers how.

## 6.3 Cache and Bind Mounts in RUN

Package managers leave caches that Dockerfiles used to clean manually. BuildKit instead lets a RUN declare an ephemeral cache mount that persists between builds but never enters the image - faster builds and smaller images at once:

```
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends curl

RUN --mount=type=cache,target=/root/.npm \
    npm ci

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -o /out/app ./cmd/app
```

Bind mounts (`--mount=type=bind,source=...`) serve the inverse need: exposing files from the context at a precise path for one instruction without copying them into a layer. Together the two mounts remove most of the old folklore about cleaning caches and reordering instructions for size.

## 6.4 Build Secrets and SSH Mounts

Never bake credentials into a layer - not as ENV, not in a RUN, not in a copied file, because every layer is extractable from the image forever. BuildKit's secret mount streams a value into the build at the exact instruction that needs it, exists only in that step's filesystem, and leaves no trace:

```
RUN --mount=type=secret,id=npm_token \
    NPM_TOKEN="$(cat /run/secrets/npm_token)" npm install

# supply it at build time - the token never lands in a layer
docker buildx build --secret id=npm_token,env=NPM_TOKEN .
docker buildx build --secret id=npm_token,src=./npm_token.txt .
```

The same pattern carries SSH agents (`--mount=type=ssh`) so builds can clone private repositories or fetch private modules using your forwarded agent rather than copied keys. In CI, the platform's secret store injects these values - GitHub Actions exposes them through the build-push action's secrets input - which closes the loop without any credential ever appearing in the image or the build log.

## 6.5 Heredoc Syntax

Modern Dockerfiles may embed multi-line payloads with heredocs, which turns many awkward RUN chains into readable blocks and lets you generate config files without a separate COPY:

```
COPY <<EOF /etc/app/config.yaml
log:
  level: info
listen:
  port: 8080
EOF

RUN <<EOT
set -eux
useradd --system --no-create-home app
install -d -o app /var/lib/app
EOT
```

## 6.6 Multi-Platform Builds

One command produces a manifest list covering several architectures. Under the hood buildx runs cross-compilation or QEMU emulation for the foreign platforms; Go and Rust cross-compile natively and are fast, while emulated apt and npm builds are usable but slow. The professional pattern is to cross-compile inside a single platform and vary only the final stage:

```dockerfile
FROM --platform=$BUILDPLATFORM golang:1.23 AS build
ARG TARGETOS TARGETARCH
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod \
    GOOS=$TARGETOS GOARCH=$TARGETARCH CGO_ENABLED=0 \
    go build -o /out/app ./cmd/app

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/app /app
ENTRYPOINT ["/app"]
```

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t registry.example.com/ops/app:1.4.0 --push .
```

::: {.note}
**Best practice**

Multi-platform pushes require a registry that accepts manifest lists (all of them do) and, in the docker-container driver, an explicit `--push` or `--load` per platform. Build for the platforms you actually run; every extra platform is build time and cache you maintain forever.
:::

## 6.7 Attestations and Cache Backends

Two features make builds auditable and fast in CI. Attestations attach signed metadata to pushed images: `--provenance` records how the image was built (sources, materials, build invocation) and `--sbom` attaches a software bill of materials that Chapter 10's scanners consume. Cache backends externalize the cache so builders - especially disposable CI builders - can import it: `--cache-to type=gha --cache-from type=gha` in GitHub Actions, or `type=registry` with a dedicated cache tag for any CI system, with `type=inline` embedding cache metadata in the pushed image itself. Pick one backend per pipeline and stick to it; mixing them silently degrades hit rates.

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --provenance=mode=max --sbom=true \
  --cache-to type=gha,mode=max \
  --cache-from type=gha \
  -t ghcr.io/acme/app:1.4.0 --push .
```

## 6.8 Bake and Build Checks

Two conveniences round out the builder. `docker buildx bake` reads a `docker-bake.hcl` file describing multiple build targets, their inputs, platforms, and outputs, and executes them as one optimized plan - the professional answer when a repository ships several images that share stages. Build checks, enabled by default in current buildx, run static analysis of the Dockerfile during build and flag issues such as unpinned base images, missing cleanup, and inconsistent platform usage, so simple review mistakes die at build time rather than in image scanning later.

::: {.lab}
### Lab 6 - Build like a pipeline {#lab6}

1. Create a docker-container builder (`docker buildx create --name lab6 --driver docker-container --use`) and build a multi-stage Dockerfile with `--load`; confirm the image appears with `docker images`.
2. Add a cache mount for your language's package manager, rebuild twice, and compare the second run's build time.
3. Inject a fake secret via `--secret id=token,src=./token.txt`, use it in a RUN, then run `docker history` on the result and verify the secret appears nowhere.
4. Build for `linux/amd64,linux/arm64` with `--push` to your local registry from Chapter 4, then run `docker buildx imagetools inspect localhost:5000/lab/app:latest` and study the manifest list and provenance attestation.
:::

**See also:** [Chapter 5](#ch5) for the Dockerfile syntax these builds consume, [Chapter 13](#ch13) for caching that spans pipeline runs, and [Appendix B](#appB) before you ship a multi-stage image.
