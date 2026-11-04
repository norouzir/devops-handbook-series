# Chapter 7 - The Secured Build Pipeline: Putting It Together {#ch7}

## 7.1 One Workflow, Every Control

Part I built the controls one at a time: secrets scanning, least-privilege tokens, SAST, dependency review, image minimization, vulnerability gating, signing, SBOM, and provenance. Each was introduced against a toy slice of pipeline; this chapter assembles them into the single workflow that `shopnow` actually ships with, because the controls are only real when they run together, in the same build, on every push to `main`. Read it top to bottom - the order is the argument:

```yaml
# .github/workflows/shopnow-secure-publish.yml
name: secure-publish
on:
  push:
    branches: [main]

permissions:            # Chapter 3: the workflow-wide floor
  contents: read
  packages: write
  id-token: write       # OIDC for cosign signing + cloud/Vault federation
  attestations: write
  security-events: write

jobs:
  quality-gates:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v7.0.0

      - name: Secrets gate (Chapter 2)
        uses: gitleaks/gitleaks-action@ff98106e4c1b76b283176d0f40e630ba6c47438a # v2.x
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: SAST gate (Chapter 4)
        run: semgrep scan --config p/owasp-top-ten --error --severity ERROR

      - name: Trivy IaC/config gate (Chapter 10 preview)
        run: |
          trivy config --severity CRITICAL --exit-code 1 .

  build-sign-attest:
    needs: quality-gates
    runs-on: ubuntu-latest
    environment: production      # Chapter 3: reviewer gate on main
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v7.0.0

      - name: Build image
        run: |
          IMAGE=ghcr.io/${{ github.repository }}
          docker build -t "$IMAGE:${{ github.sha }}" .
          docker push "$IMAGE:${{ github.sha }}"
          echo "IMAGE_DIGEST=$(docker buildx imagetools inspect \
            "$IMAGE:${{ github.sha }}" --format '{{json .Manifest.Digest}}' | tr -d '"')" \
            >> "$GITHUB_ENV"

      - name: Vulnerability gate (Chapter 5)
        run: |
          trivy image --ignore-unfixed --exit-code 1 --severity CRITICAL \
            ghcr.io/${{ github.repository }}@${{ env.IMAGE_DIGEST }}

      - name: SBOM (Chapter 6)
        run: |
          syft ghcr.io/${{ github.repository }}@${{ env.IMAGE_DIGEST }} \
            -o spdx-json > shopnow-${{ github.sha }}.spdx.json
          cosign attest --yes --predicate shopnow-${{ github.sha }}.spdx.json \
            --type spdxjson ghcr.io/${{ github.repository }}@${{ env.IMAGE_DIGEST }}

      - name: Sign (Chapter 6)
        run: |
          cosign sign --yes \
            ghcr.io/${{ github.repository }}@${{ env.IMAGE_DIGEST }}

      - name: Provenance (Chapter 6)
        uses: actions/attest-build-provenance@17372516f96e6ba28a5b4249a0f5f9f72ac9d53a # v2.x
        with:
          subject-name: ghcr.io/${{ github.repository }}
          subject-digest: ${{ env.IMAGE_DIGEST }}

  deploy:
    needs: build-sign-attest
    runs-on: ubuntu-latest
    environment: production
    permissions:
      id-token: write
      contents: read
    steps:
      - name: Verify before deploy (Chapter 6 enforcement)
        run: |
          cosign verify \
            --certificate-identity-regexp='^https://github.com/${{ github.repository }}/' \
            --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
            ghcr.io/${{ github.repository }}@${{ env.IMAGE_DIGEST }}

      - name: Deploy via OIDC (Chapter 3 + Vault from Chapter 2)
        run: ./deploy.sh    # kubectl/helm with credentials minted from OIDC, never stored
```

## 7.2 The Anatomy of the Gate

Three properties make this workflow more than the sum of its steps. **Every gate fails closed**: gitleaks, Semgrep, Trivy, and cosign verify all exit non-zero on a finding, and the job graph (`needs:`) means nothing reaches the registry or the cluster through a failed gate - there is no "override" flag, and the emergency override is the reviewed PR that fixes the finding. **Credentials are minted, never stored**: the only secret reference in the file is the automatic `GITHUB_TOKEN`, and its permissions are scoped per job; deployments ride OIDC from [Chapter 3](#ch3), Vault tokens from [Chapter 2](#ch2) are thirty-minute leases, and the signing key from [Chapter 6](#ch6) exists for roughly the duration of one `cosign sign` call. **Every artifact is self-describing**: what leaves this pipeline is an image digest with a signature, an SBOM attestation, and build provenance attached - exactly the identity the admission controllers of Part II will demand.

::: {.warn}
**Watch out - a gate that runs after the push is not a gate**

The step order above is load-bearing: vulnerability scanning runs against the *digest of the pushed image*, but the deploy job cannot run until build-sign-attest succeeds - and cosign verification in `deploy` fails closed on an unsigned or re-tagged image. If you ever find a variant of this pipeline that pushes to a production registry *before* the gates, or deploys from a tag rather than a digest, the pipeline's security is a comment on a slide, not a property of the system. Gates that cannot stop the release are reports; put them before the push or make the admission controller (Chapter 8) stop it instead.
:::

## 7.3 Operating the Pipeline Day to Day

A pipeline this strict changes daily work in ways worth setting expectations for. A red build now has a *type*: a gitleaks failure means rotate-and-remove (never delete-only), a Semgrep ERROR means the code pattern needs fixing or an explicit, commented suppression, a Trivy CRITICAL means a base-image bump is usually the one-line fix, and a cosign failure at deploy means someone pushed an unidentifiable image - treat it as an incident, not an inconvenience. The mean-time-to-green discipline matters: gates that stay red for days train the team to expect red, and a red-tolerant team has no gate at all. Expect the pipeline to *cause* the occasional Friday-afternoon scramble early on; the point of [Chapter 13](#ch13) is that the scramble gets shorter each time, and the postmortem feeds policy back into this same workflow.

The controls also compose with the rest of the series. The Kubernetes book's GitOps chapter (Argo CD watching an overlay repository) plugs in as an alternative `deploy` job that syncs from the environment repo instead of running `deploy.sh` inline - signing verification moves to the cluster either way. The observability books pick up where this workflow ends: the deploy event, the admission decisions, and the Falco alerts of [Chapter 12](#ch12) all land in the same Prometheus and Elasticsearch the series already runs. Security is not a separate pipeline; it is a set of invariants on the pipeline that already existed.

**See also:** [Chapter 8](#ch8) begins Part II by making the cluster refuse what this pipeline would never ship anyway - defense in depth if Part I holds, the last line of defense if it does not; [Appendix C](#appC) holds the complete starter files from Part I, ready to copy.
