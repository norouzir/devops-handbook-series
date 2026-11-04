# Chapter 6 - Signing, Provenance, and SBOM: Cosign, Syft, and SLSA {#ch6}

## 6.1 "What Exactly Is Running?" - Artifact Identity

Everything so far in Part I makes the pipeline produce a *clean* image. This chapter makes it produce an image you can **prove** things about: that it came from your build system, that no one modified it after signing, and that its exact contents are enumerated somewhere queryable. Those three proofs are signing, provenance, and the SBOM - and they exist because the questions they answer arrive at the worst times: "are we vulnerable to this new CVE?" needs the SBOM, "did anything ship that wasn't built by CI?" needs signing, and "which build produced the binary running in prod?" needs provenance. An organization without artifact identity answers these questions by archaeology; with it, by query.

The Sigstore stack provides the cryptography without the key ceremony that historically killed signing adoption. **Cosign** signs container images and other artifacts; **keyless signing** binds the signature to an OIDC identity (a GitHub Actions workflow, or your own email) and stores two receipts: a short-lived signing certificate from **Fulcio** (the certificate authority) and a transparency-log entry in **Rekor** (the tamper-evident public record). No long-lived private key is created, stored, or stealable - the thing being protected *is* the pipeline identity that [Chapter 3](#ch3) already hardened.

## 6.2 Signing and Verifying with Cosign

Install cosign, then sign by digest - tags are mutable pointers, digests are the content, and a signature on a tag signs whatever the tag happens to point at later, which is nothing at all:

```bash
cosign sign --yes ghcr.io/acme/shopnow@sha256:bc1f...e9   # keyless: uses CI OIDC identity
cosign verify \
  --certificate-identity-regexp='^https://github.com/acme/shopnow/' \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  ghcr.io/acme/shopnow@sha256:bc1f...e9
```

`cosign verify` re-derives the whole chain: the signature was made by a Fulcio certificate issued to the OIDC identity `https://github.com/acme/shopnow/.github/workflows/publish.yml@refs/heads/main`, the certificate chains to the Sigstore root, and the transparency log entry exists and is consistent. In a GitHub Actions workflow, the `id-token: write` permission (the OIDC token mint from [Chapter 3](#ch3)) is the only prerequisite. The identity regexp is the policy: it accepts signatures from *this repository's workflows* and rejects everyone else's, which turns "the image exists in the registry" into "the image was built by our CI and has not changed since it was signed."

## 6.3 The SBOM: Your Dependency Inventory, Machine-Generated

A **software bill of materials (SBOM)** is a structured, machine-readable inventory of everything an artifact contains - OS packages, language dependencies, direct and transitive. **Syft** generates one from any image or directory in the two standard formats (SPDX and CycloneDX):

```bash
syft ghcr.io/acme/shopnow@sha256:bc1f...e9 -o spdx-json > shopnow.spdx.json
syft ghcr.io/acme/shopnow -o cyclonedx-json | jq '.components | length'
```

The SBOM earns its keep the day the next Log4Shell hits. The vulnerable-question workflow becomes: `grep` the SBOMs (or query a tool that indexes them) for `log4j-core`, receive the list of affected services in minutes, and act - versus the 2021 reality of grepping source trees, guessing at transitive dependencies, and hoping. Trivy from [Chapter 5](#ch5) actually *consumes* SBOMs too, so one artifact feeds both the inventory and the scanner. Keep SBOMs with their images (they are versioned artifacts like any other) and regenerate per build - an SBOM for a tag is an SBOM for whatever the tag points at next.

## 6.4 SLSA Provenance: The Build's Own Receipt

**SLSA** (Supply-chain Levels for Software Artifacts) grades how much of the build process can be trusted and verified, from level 1 (build scripted, provenance exists) through level 3 (hardened, isolated build whose provenance cannot be forged by the source repo alone). The practical takeaway for a GitHub Actions pipeline is that GitHub generates **artifact attestations** natively: the `actions/attest-build-provenance` action records a signed statement binding the artifact digest to the exact workflow run, commit, and build environment, visible with `gh attestation verify`:

```yaml
permissions:
  id-token: write
  attestations: write
  contents: read
  packages: write
steps:
  - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v7.0.0
  # ... build & push, capture IMAGE_DIGEST
  - uses: actions/attest-build-provenance@17372516f96e6ba28a5b4249a0f5f9f72ac9d53a # v2.x
    with:
      subject-name: ghcr.io/acme/shopnow
      subject-digest: ${{ env.IMAGE_DIGEST }}
```

A downstream consumer then runs `gh attestation verify ghcr.io/acme/shopnow -R acme/shopnow` and receives cryptographic proof that the bytes came from this repository's build. Combined with the cosign signature and the SBOM, the artifact now carries three linked, verifiable statements: *who built it, what is in it, and that it has not changed since*.

::: {.note}
**Best practice - verify where it is cheap, enforce where it is final**

Verification is only useful if something acts on the result, and the right enforcement point is **admission**: the Kubernetes cluster refusing to run unsigned images (Kyverno's `verifyImages` rule, previewed here and built in [Chapter 8](#ch8)) means a manually pushed or tampered image is not merely detectable - it is unschedulable. Layer cheaper checks earlier (a verify step in the deploy workflow, a registry policy) so failures surface in seconds at the push, but let the admission policy be the hard floor.
:::

::: {.lab}
### Lab 4 - Sign, Inventory, and Tamper-Test the Artifact {#lab4}

1. Build and push `shopnow` from [Lab 3](#ch5) to GHCR; capture the digest (`docker buildx imagetools inspect` or the workflow output).
2. Generate the SBOM: `syft <image>@<digest> -o spdx-json > shopnow.spdx.json`, then count components and grep it for the top three runtime dependencies. Keep the file versioned next to the build.
3. Sign keyless from a workflow run (locally, `cosign sign` uses your OIDC identity interactively; in CI it is automatic). Then `cosign verify` with the identity regexp scoped to your repository.
4. Tamper-test: build a trivially modified image (one env var in the Dockerfile), push it to the *same tag*, and re-run verify against the original digest. The signature check must fail - demonstrate it, do not trust it.
5. Add `actions/attest-build-provenance` to the publish workflow and run `gh attestation verify` against the pushed image. You now hold all three proofs; record the three commands in the runbook from [Chapter 13](#ch13).
:::

**See also:** [Chapter 7](#ch7) assembles signing, SBOM, and scanning into the single publish pipeline; [Chapter 8](#ch8) enforces the signature at admission; SLSA's project documentation owns the moving details of the levels and attestations format.
