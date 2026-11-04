# Appendix C - Starter Configurations {#appC}

Copy-paste starters for the files every secured repository needs on day one. Each is the minimal complete version of a file built across Part I; production versions add team-specific paths and owners.

## 1. `.pre-commit-config.yaml` - secret hook (Chapter 2)

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.3
    hooks:
      - id: gitleaks
```

## 2. `.gitleaks.toml` - explicit allowlist (Chapter 2)

```toml
[extend]
useDefault = true

[allowlist]
  description = "Accepted false positives - each with owner and review date"
  paths = [
    '''testdata/.*''',        # synthetic fixtures, no real creds (owner: ci-team, 2026-09)
  ]
```

## 3. `.github/dependabot.yml` - updates with groups (Chapter 4)

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule: { interval: weekly }
    groups:
      minor-and-patch:
        update-types: ["minor", "patch"]
  - package-ecosystem: github-actions
    directory: /
    schedule: { interval: weekly }
  - package-ecosystem: docker
    directory: /
    schedule: { interval: weekly }
```

## 4. `.github/workflows/security-gates.yml` - the Part I floor (Chapters 2-7)

```yaml
name: security-gates
on:
  push: { branches: [main] }
  pull_request:

permissions:
  contents: read
  security-events: write
  packages: write
  id-token: write
  attestations: write

jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v7.0.0

      - name: Secrets gate
        uses: gitleaks/gitleaks-action@ff98106e4c1b76b283176d0f40e630ba6c47438a # v2.x
        env: { GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }

      - name: SAST gate
        run: semgrep scan --config p/owasp-top-ten --error --severity ERROR

      - name: IaC gate
        run: trivy config --severity HIGH,CRITICAL --exit-code 1 .
```

## 5. Vault policy `shopnow-app.hcl` (Chapter 2)

```hcl
path "shopnow/data/dev/*" {
  capabilities = ["read"]
}
path "shopnow/metadata/*" {
  capabilities = ["list"]
}
```

## 6. Kyverno starter policy set (Chapter 8)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: shopnow-baseline
spec:
  validationFailureAction: Audit      # flip to Enforce after a clean week
  background: true
  rules:
    - name: require-nonroot-and-limits
      match:
        any: [{ resources: { kinds: [Pod], namespaces: ["shopnow-*"] } }]
      validate:
        message: "Containers must run non-root and declare CPU/memory limits."
        pattern:
          spec:
            containers:
              - securityContext: { runAsNonRoot: true }
                resources: { limits: { "?*": "?*" } }
    - name: require-image-tag-not-latest
      match:
        any: [{ resources: { kinds: [Pod], namespaces: ["shopnow-*"] } }]
      validate:
        message: "Images must be digest- or semver-tagged, never :latest."
        pattern:
          spec:
            containers:
              - image: "*:*@* | !*latest*"
```

## 7. Default-deny NetworkPolicy (Chapter 9)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny-all, namespace: shopnow-prod }
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

## 8. Hardened pod securityContext (Chapter 9)

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    seccompProfile: { type: RuntimeDefault }
  containers:
    - name: app
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: { drop: ["ALL"] }
```

## 9. Ingress security headers (Chapter 11)

```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/limit-rps: "20"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "Content-Security-Policy: default-src 'self'";
      more_set_headers "Referrer-Policy: strict-origin-when-cross-origin";
```

## 10. Compliance evidence cron (Chapter 14)

```yaml
on:
  schedule:
    - cron: "0 6 * * 1"
jobs:
  collect:
    runs-on: ubuntu-latest
    permissions: { id-token: write, contents: read }
    steps:
      - run: ./scripts/kube-bench-collect.sh
      - run: kubectl get policyreports -A -o json > evidence/admission.json
      - run: ./scripts/access-review.sh > evidence/access.csv
      - run: ./scripts/evidence-upload.sh
```

**See also:** each file's chapter for the full walkthrough; [Appendix B](#appB) for the commands that operate them; the GitHub Actions book's starter-workflows appendix for the deploy halves these gates attach to.
