# Chapter 4 - Images and Registries {#ch4}

Images are the currency of the container world: the artifact you build once and run everywhere. This chapter opens the image format, explains how layers make pulls cheap and tags fragile, and then treats registries as what they are in production - critical infrastructure with rate limits, access control, and retention policy.

## 4.1 What an Image Actually Is

An OCI image is a small pile of JSON and tarballs. Layers are read-only tar archives of filesystem changes; the config blob is a JSON document recording the entrypoint, environment, and layer order; the manifest lists the layers and config by their content hashes; and an index (manifest list) maps platforms to manifests. When you run a container, the runtime stacks the layers into a root filesystem using the overlay mechanism and adds one thin writable layer on top. Every layer is content-addressed by its SHA-256 digest, which is why two images that share a base layer store it once locally and pull it once over the wire - and why `docker pull` output shows some layers as Already exists.

The copy-on-write detail has operational consequences. Containers only write to their own thin layer, so ten nginx containers share one image on disk. Reads into lower layers are nearly free; writes allocate space in the writable layer and never disappear unless you remove the container. Anything valuable written there is therefore both slow and doomed - which is exactly the motivation for volumes in Chapter 7.

## 4.2 Tags versus Digests

A tag (`nginx:1.27-alpine`) is a mutable pointer that a publisher can move at any time; a digest (`nginx@sha256:...`) pins the exact manifest bytes and can never change silently. Production discipline follows from this asymmetry: tags are for humans and development, digests are for deployment records and audits. When your deploy pipeline records what it shipped, it should record the digest, not the tag, because that is the only value that answers the question exactly what is running months later. Chapter 13 bakes this into the CI/CD pipeline.

```bash
docker pull nginx:1.27-alpine          # mutable tag
docker pull nginx@sha256:8a68...c3e    # immutable content

# find the digest you actually pulled
docker images --digests nginx

# a tag is a label on a digest; several tags may share one image ID
docker tag nginx:1.27-alpine registry.example.com/ops/nginx:candidate
```

## 4.3 Multi-Architecture Images

Modern images are almost always multi-architecture: one tag maps through an OCI index to a set of per-platform manifests for `linux/amd64`, `linux/arm64`, and friends. When you pull `nginx:1.27-alpine`, the client and registry negotiate the platform matching your host transparently. This is why the same command works identically on an x86 server and an Apple Silicon laptop, and it is also why you occasionally need to be explicit - `docker pull --platform linux/amd64 alpine` fetches a foreign platform deliberately, which is a daily occurrence on build farms preparing images for other targets. Chapter 6 shows how such images are built in one pass with buildx.

## 4.4 Docker Hub in Practice

Docker Hub remains the default public registry, and it rate-limits anonymous pulls by source IP in rolling six-hour windows - low enough that shared CI egress IPs hit the ceiling regularly. Authenticate to raise the ceiling, mirror through a pull-through cache behind your proxy, or route production through your own registry. Create access tokens in Hub settings and use them instead of your account password in CI, with least-privilege scopes (read-only for pullers). The operational failure mode to recognize: `toomanyrequests: You have reached your pull rate limit` appearing suddenly on a fleet - usually the first symptom that some automation is re-pulling far more than you assumed.

| Registry | Typical role | Auth model |
| ------------ | ----------------------- | --------------- |
| Docker Hub | Public images, official bases | Account plus access tokens |
| GHCR (GitHub) | Images next to their source code | GitHub token with package scopes |
| ECR / ACR / GCR | Cloud-native private registries | Cloud IAM roles |
| Distribution / Harbor | Self-hosted registry (Harbor adds scanning, signing, retention) | Local users, OIDC, robot accounts |

: Table 4.1 - Registries a DevOps engineer meets

## 4.5 Running a Private Registry

A private registry is a two-minute exercise that pays off in every lab in this book, and the `registry:2` image is the reference implementation of the OCI distribution specification. Run it, mark it as trusted for your tests, and push to it exactly as you would to Hub:

```bash
docker run -d --name registry --restart unless-stopped \
  -p 5000:5000 -v registry-data:/var/lib/registry registry:2

docker tag nginx:1.27-alpine localhost:5000/ops/nginx:candidate
docker push localhost:5000/ops/nginx:candidate
docker pull localhost:5000/ops/nginx:candidate

# browse the catalog and tags it now stores
curl -s localhost:5000/v2/_catalog
curl -s localhost:5000/v2/ops/nginx/tags/list
```

For anything beyond a lab, put TLS in front (or run the registry behind an authenticating proxy), enable garbage collection for deleted manifests, and set retention policy - registries grow without limit otherwise. Harbor wraps the same core with vulnerability scanning, image signing, and project-level RBAC, which is why it appears in regulated environments.

## 4.6 Managing Local Images

Daily image hygiene is six commands. `docker images` (or `docker image ls`) lists what is cached, with `--filter dangling=true` isolating orphaned layers. `docker image history nginx:1.27-alpine` reconstructs how the image was assembled layer by layer - the fastest way to understand why an image weighs what it does. `docker image inspect` exposes config and metadata. `docker save` and `docker load` move images as tarballs across air gaps. `docker image prune` reclaims space from dangling layers, and `docker image prune -a` removes everything without a tag or an associated container - powerful and indiscriminate, so keep it out of production crons unless you enjoy long re-pulls. Under the containerd image store of Engine v29 these commands behave identically, but content is stored content-addressed, so expect `du` on the data root to show a different layout than the legacy graph drivers.

::: {.warn}
**Watch out**

Untagged images are not necessarily garbage: a tag pushed to a registry does not pin the local cache, and mid-build dangling layers may be exactly what a running build is about to use. Never schedule aggressive `docker image prune -a` on build nodes during working hours; the CI cache misses it causes are far more expensive than the disk it frees.
:::

::: {.lab}
### Lab 4 - Own your registry {#lab4}

1. Run a local registry on port 5000 as shown above, then pull `alpine:3.20`, tag it as `localhost:5000/lab/alpine:owned`, and push it.
2. Delete the local image (`docker rmi localhost:5000/lab/alpine:owned`), then pull it back from your registry and confirm the catalog endpoint lists it.
3. Record digests: run `docker images --digests` and explain which value would end up in a production change ticket.
4. Inspect before and after: compare `docker system df` numbers, then create five dangling images by rebuilding a tiny Dockerfile and clean them with `docker image prune`.
:::

**See also:** [Chapter 5](#ch5) to build the images you have been pulling, [Chapter 6](#ch6) for BuildKit's cache and multi-platform builds, and [Chapter 13](#ch13) for registries inside a pipeline.
