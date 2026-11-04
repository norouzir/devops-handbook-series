# Chapter 10 - Securing Docker in Production {#ch10}

Docker security is layered defense, and each layer is cheap to add at build time and expensive to retrofit after an incident. This chapter walks the layers in the order you should adopt them: shrink the running surface, constrain the process, harden the image supply chain, and guard the daemon - the actual crown jewel of every host.

## 10.1 The Threat Model in One Page

Be honest about what a container does and does not isolate. A container isolates processes by namespaces and constrains them by cgroups on a shared kernel; it is not a VM. The realistic threats, in order of frequency: an application vulnerability lets an attacker run code inside the container and pivot from there; a leaked credential baked into an image or an environment grants access to a registry, a database, or a cloud account; a published port exposes something that was never meant to be public; and the Docker socket is mounted or the API is exposed, which converts any container-side foothold into host root. Every practice in this chapter maps to one of those four. When you evaluate a new hardening idea, ask which of the four it addresses - if the answer is none, it is decoration.

## 10.2 Rootless Mode and User Namespace Remapping

The single highest-leverage host-level change is removing real root from the container runtime path. Rootless mode (Chapter 2) runs the daemon and all containers as an unprivileged user with user namespaces mapping container root to that user; a breakout lands on an unprivileged account with no daemon socket. For hosts that must keep classic rootful Docker, `userns-remap` in daemon.json achieves the container-side half: container UID 0 maps to an uncommitted host range (typically 65536+), so a container-root file write is an unprivileged user's write on the host. Both modes have integration edges - bind mounts need ownership adjustments, and some images assume real root - so adopt them deliberately: rootless for build runners and multi-tenant hosts, userns-remap where rootful is contractual.

## 10.3 Capabilities, Seccomp, and Mandatory Access Control

By default, containers run with a trimmed but generous set of Linux capabilities. The professional baseline is to drop everything and add back only what the application proves it needs:

```bash
docker run -d --name hardened \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:rw,size=64m --tmpfs /run:rw,size=32m \
  -p 8080:8080 myorg/api:1.4.0
```

Three flags in that command deserve narration. `--cap-drop=ALL --cap-add=NET_BIND_SERVICE` keeps only the ability to bind port 80 inside the container (and even that is unnecessary when the app listens on 8080 and the proxy fronts it). `--security-opt no-new-privileges` blocks any process inside from gaining extra privileges via setuid binaries - the cheapest flag with the highest return in this chapter. `--read-only` with tmpfs scratch directories makes the root filesystem immutable, which both blocks persistence-by-attacker and forces you to discover exactly which paths your app genuinely needs to write. Below the capability layer, every container runs under Docker's default seccomp profile (blocking dozens of risky syscalls) and, on Ubuntu and Debian hosts, under AppArmor; RHEL-family hosts apply SELinux labels. Leave the default profiles on - `--privileged` and `--security-opt seccomp=unconfined` belong in throwaway test VMs only, and a `--privileged` container in production should page someone.

## 10.4 Image Security: Scanning, SBOMs, and Minimal Bases

Most container CVEs are found, not prevented - so the pipeline must find them first. Docker Scout is the native tooling: `docker scout cves myorg/api:1.4.0` analyzes an image against vulnerability databases and suggests base-image upgrades (`docker scout recommendations`), and when builds carry attestations (Chapter 6) it can map findings to exact packages and layers. Trivy is the standard open-source alternative with a robust CLI for CI gates (`trivy image --exit-code 1 --severity CRITICAL,HIGH image`). Pair scanning with three supply-side habits: prefer minimal bases (alpine, distroless, or Docker Hardened Images, which Docker curates with reduced CVE counts and maintained upgrades), pin bases and dependencies to specific versions so upgrades are deliberate events, and rescan on a schedule - images that were clean at build time age badly.

```bash
docker scout cves myorg/api:1.4.0
docker scout sbom myorg/api:1.4.0        # what exactly is inside
trivy image --exit-code 1 --severity CRITICAL,HIGH myorg/api:1.4.0
```

## 10.5 Supply Chain: Provenance, Signing, and Registry Access

Knowing what is in an image is half the job; knowing where it came from and that nobody tampered with it is the other half. Build with `--provenance=mode=max` so the image carries a signed statement of its build materials, attach `--sbom=true`, and have a policy engine or Scout consume both downstream. The classic Docker Content Trust (Notary v1) signing flow is deprecated - the ecosystem direction is Sigstore-style signing with cosign, which registry operators (including Harbor and the cloud registries) verify natively. On the access side: registry credentials in CI are machine tokens with the narrowest scopes (read-only pullers, per-repo pushers), human accounts use SSO with 2FA, and pulls in production reference digests so what you verified is provably what runs.

## 10.6 Secrets: Never in the Environment of Record

Secrets leak through three Docker-specific channels, and each has a correct channel instead. Build-time secrets (package tokens, registry pulls) use BuildKit secret mounts - never ARG, never COPY (Chapter 6). Runtime secrets belong in files injected by the platform - Compose secrets, Swarm secrets, Kubernetes Secrets mounted as volumes - or fetched at boot from a secret manager (Vault, cloud secret stores); environment variables are the convenient last resort that ends up in `docker inspect`, in crash dumps, and in `docker history` of images that baked them. And images must never carry secrets at all, which is a review rule and a scanner rule (`docker history` plus a secret-pattern grep belongs in your CI). The habit that makes all three stick: every credential has an owner and a rotation story, and rotation is rehearsed quarterly, because an unrotated leaked credential is just a slower breach.

## 10.7 The Docker Socket and the Daemon

The daemon socket is root on the host wearing a Unix socket costume: anything that can talk to it can mount your filesystem into a container and read it. Treat every integration that wants it as a privileged grant: CI agents on dedicated, disposable runners; monitoring sidecars only with tightly-scoped socket proxies (which filter allowed API paths) or better, with the metrics and events interfaces meant for them; and development tools on workstations where the developer already has root. TCP exposure of the API (2375/2376) without mutual TLS is an automatic incident in any audit - the scans find it in minutes. If a vendor integration insists on the socket, put the proxy in front, log the API calls, and keep the grant on the shortest possible leash with a named container, read-only mounts, and a review date.

::: {.lab}
### Lab 10 - Harden a container end to end {#lab10}

1. Run your Chapter 5 image plainly, then run it with `--cap-drop=ALL --read-only --tmpfs /tmp --security-opt no-new-privileges`; record what breaks and add back the minimum.
2. Scan it: `docker scout cves` (or `trivy image`) and note the top findings; switch the base to a slimmer alternative, rebuild, and compare the report.
3. Prove a leak: put a fake token in an ENV-based build, run `docker history` and `docker image inspect` and find it; then repeat with a BuildKit secret mount and show it is gone.
4. Audit the host: run `ss -lntp | grep -E "2375|2376"` (must be empty), check `docker context ls`, and verify who is in the `docker` group - write down any grant you cannot justify.
:::

**See also:** [Chapter 2](#ch2) for the daemon configuration this hardens, [Chapter 11](#ch11) for the cluster-level controls that replace part of it.
