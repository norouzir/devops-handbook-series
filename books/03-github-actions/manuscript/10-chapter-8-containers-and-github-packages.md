# Chapter 8 - Containers and GitHub Packages {#ch8}

## 8.1 GitHub Container Registry

GHCR (`ghcr.io`) stores OCI images and other package types adjacent to the repository, with visibility (private/public) and permissions manageable per package and inherited by default from the repository. Workflows authenticate with the `GITHUB_TOKEN` and the `packages: write` permission - no personal access token needed for in-repo pushes, which removes the classic token-rotation chore. Images pushed from a repository appear under its Packages tab, link back to the committing workflow, and can be pulled by dependents using the same credential model or, for public packages, anonymously.

```yaml
name: Build and push image
on:
  push:
    branches: [main]
permissions:
  contents: read
  packages: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}:latest
```

## 8.2 docker/build-push-action and Buildx

The Buildx-based action is the standard builder frontend, and the `docker/setup-buildx-action` + `docker/setup-qemu-action` pair unlocks multi-platform builds: one workflow line (`platforms: linux/amd64,linux/arm64`) produces a manifest-listed image that serves both architectures. Build caching should live in the registry rather than the actions cache for container work: `cache-from: type=gha` is fine for small projects, but `type=registry` with `cache-to: type=inline` (or a dedicated cache image) makes cache hits available to any runner, including self-hosted fleets. Build secrets - tokens needed during `RUN` but not wanted in layers or history - flow through BuildKit mounts (`RUN --mount=type=secret`), not `ARG`.

```
- uses: docker/setup-qemu-action@v3
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    context: .
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/${{ github.repository }}:v1.4.2
    cache-from: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache
    cache-to: type=inline
    provenance: mode=max
    sbom: true
    secrets: |
      MY_TOKEN=${{ secrets.MY_TOKEN }}
```

## 8.3 Tagging and Release Discipline

Tags are policy, and the policy should be boring. A workable default: immutable SHA tags always; `latest` only on default-branch builds (and preferably not at all for services consumed by other teams); semver tags built from Git tags via `docker/metadata-action`; and environment channels (`staging`, `production`) expressed as **deploy-time selections of immutable digests**, never as mutable image tags that drift. Promote by digest - `docker pull image@sha256:...` - so what you tested in staging is byte-identical to what production runs, and record the digest in the deployment record for audit.

::: {.warn}
**Watch out - repository name case**

GHCR image references must be lowercase. `${{ github.repository }}` preserves the repository's case, and a capital letter in an org or repo name produces a push error at the worst moment. Normalize with an expression step (`echo "repo=${GITHUB_REPOSITORY,,}" >> "$GITHUB_ENV"`) before composing image tags.
:::

## 8.4 Supply-Chain Metadata: SBOM and Provenance

BuildKit emits signed provenance and SBOM attestations natively when `provenance:` and `sbom:` are enabled, and the `actions/attest-build-provenance` action does the same for non-container artifacts, generating Sigstore-backed attestations that establish SLSA v1.0 Build Level 2 - with reusable-workflow-based builds reaching Build Level 3. Consumers verify with `gh attestation verify`, binding an artifact to the repository, workflow, and commit that produced it. Publishing these metadata records costs seconds per build and is increasingly a customer and compliance requirement rather than a nice-to-have; Chapter 12 develops the full verification and policy story.

## 8.5 Dependabot and Container Hygiene

Dependabot understands Dockerfiles and workflow files: it opens update pull requests for base image bumps and action version bumps (regenerating lockfile entries where workflows are onboarded), and groups updates by configuration. Combine it with the registry's own signals - stale `latest` tags, images with unpatched base layers, packages nobody pulled in a year - and container hygiene becomes a background process instead of a quarterly fire drill. The configuration lives in `.github/dependabot.yml`; the two ecosystems to enable for this book's scope are `github-actions` and `docker`.

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    groups:
      actions-minor:
        update-types: [minor, patch]
  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
```

**See also:** [Chapter 9](#ch9) for deploying the images you just pushed, [Chapter 12](#ch12) for signature and provenance checks, and the *Docker for DevOps Engineers* volume for the Dockerfile those builds start from.
