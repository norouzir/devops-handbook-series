# Appendix B - Dockerfile Best-Practice Checklist {#appB}

Review Dockerfiles against this list; each item is one actionable sentence with its rationale. Items marked with an asterisk are the ones reviewers most often waive and later regret.

- Pin the base image to a specific version tag (never `latest`); use a digest for release builds so rebuilds are reproducible.
- Prefer minimal bases - alpine, slim, distroless, or Docker Hardened Images - to cut size and CVE count in one move.
- Put `.dockerignore` in place on day one; exclude VCS, dependency caches, build outputs, and anything secret-shaped.
- Order instructions from least to most frequently changing; copy dependency manifests and install before copying source.
- Combine related RUN steps with && and clean package caches inside the same layer (or use BuildKit cache mounts).
- Use multi-stage builds; ship only compiled artifacts and runtimes in the final stage.
- Use exec form for CMD and ENTRYPOINT so your process is PID 1 and receives signals directly.
- Run as a non-root USER created explicitly in the image; never ship UID 0 without a documented reason.\*
- Add a HEALTHCHECK that probes real functionality, with a start\_period that forgives boot time.
- Never bake secrets into layers or ENV; use BuildKit secret mounts for build-time credentials.\*
- Declare default ENV values so the image runs with zero configuration, and document every override.
- Set STOPSIGNAL when the application expects a signal other than SIGTERM.
- Prefer COPY over ADD except for auto-extracting local tar files.
- Label images (org.opencontainers.image.\* metadata) so ownership and source are queryable in the registry.
- Attach provenance and SBOM attestations at push time and let the scanner consume them.
- Keep the Dockerfile lint-clean under buildx build checks; treat warnings as review findings.
- Test the image, not just the code: run the container in CI and hit its health endpoint before pushing.\*
- Record the built digest in the deploy artifact; tags are for humans, digests are for audits.
