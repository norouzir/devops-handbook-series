# Appendix B - Command Quick Reference {#appB}

One screen per tool, commands exactly as used in the chapters. Region and repository names follow the book's conventions (`acme/shopnow`); substitute your own.

## Gitleaks (Chapter 2)

```bash
gitleaks detect --source . -v          # scan full git history
pre-commit run gitleaks --all-files    # baseline scan via pre-commit
```

## Vault (Chapter 2)

```bash
vault server -dev                                   # dev server (learning only)
vault status                                        # health/unseal check
vault secrets enable -path=shopnow kv-v2            # versioned KV engine
vault kv put shopnow/dev/db password='...'          # write a secret
vault kv get -field=password shopnow/dev/db         # read one field
vault kv rollback -version=1 shopnow/dev/db         # restore a version
vault policy write shopnow-app shopnow-app.hcl      # install a policy
vault token create -policy=shopnow-app -ttl=1h      # scoped token
vault auth enable approle                           # machine auth
vault write auth/approle/role/shopnow token_policies=shopnow-app token_ttl=1h
vault read auth/approle/role/shopnow/role-id        # role-id (not secret)
vault write -f auth/approle/role/shopnow/secret-id  # one-time secret-id
vault write auth/approle/login role_id=... secret_id=...
vault auth enable jwt                               # OIDC (GitHub Actions)
vault write auth/jwt/role/shopnow-ci role_type=jwt \
  bound_subject='repo:acme/shopnow:environment:production' token_policies=shopnow-app
vault secrets enable database                       # dynamic credentials
vault read database/creds/shopnow-readonly          # fresh DB user, 1h TTL
```

## Semgrep (Chapter 4)

```bash
semgrep scan --config auto                    # rules by language
semgrep scan --config p/owasp-top-ten         # focused ruleset
semgrep scan --config p/owasp-top-ten --error --severity ERROR   # CI gate
```

## Trivy (Chapters 5, 10, 14)

```bash
trivy image shopnow:latest -s HIGH,CRITICAL                       # scan an image
trivy image --ignore-unfixed --exit-code 1 -s CRITICAL image      # CI gate
trivy image --format sarif --output trivy.sarif image             # for GitHub upload
trivy config --severity HIGH,CRITICAL --exit-code 1 infra/        # IaC gate
trivy kubernetes cluster --report summary                         # cluster view
```

## Cosign / Syft / gh attestations (Chapter 6)

```bash
cosign sign --yes ghcr.io/acme/shopnow@sha256:bc1f...e9
cosign verify \
  --certificate-identity-regexp='^https://github.com/acme/shopnow/' \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  ghcr.io/acme/shopnow@sha256:bc1f...e9
cosign attest --yes --predicate shopnow.spdx.json --type spdxjson <image@digest>

syft ghcr.io/acme/shopnow@sha256:bc1f...e9 -o spdx-json > shopnow.spdx.json
syft ghcr.io/acme/shopnow -o cyclonedx-json

gh attestation verify ghcr.io/acme/shopnow -R acme/shopnow
```

## Checkov (Chapter 10)

```bash
checkov -d infra/ --framework terraform --hard-fail-on CRITICAL
checkov -f tfplan --framework terraform_plan --hard-fail-on CRITICAL
checkov -d infra/ --skip-check CKV_AWS_20          # explicit suppression
```

## Kyverno (Chapter 8)

```bash
helm install kyverno kyverno/kyverno -n kyverno --create-namespace
kubectl apply -f 01-verify-signatures.yaml        # install policies
kubectl get policyreports -A                      # audit-mode findings
kubectl get clusterpolicies                       # installed policies
kyverno apply 02-baseline-policies.yaml --resource pod.yaml    # test in CI
```

## NetworkPolicy verification (Chapter 9)

```bash
kubectl run tmp --rm -it --image=busybox --restart=Never -- nc -zv shopnow 8080
kubectl get networkpolicy -n shopnow-prod
```

## ZAP baseline (Chapter 11)

```bash
zap-baseline.py -t https://staging.shopnow.example -r zap-report.html
# in CI: zaproxy/action-baseline with fail_action: true
```

## kube-bench (Chapter 14)

```bash
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml
kubectl logs -n kube-bench job.batch/kube-bench
```

## GitHub Actions hardening (Chapter 3)

```bash
rg -n "uses:" .github/workflows/          # which actions; SHA-pinned?
rg -Ln "permissions:" .github/workflows/  # workflows inheriting defaults
rg -n "pull_request_target" .github/workflows/
gh attestation verify <artifact> -R acme/shopnow
```
