# Appendix D - Troubleshooting Guide {#appD}

Organized by symptom, the way problems actually arrive. Each entry: what you see, what it usually means, the fix, and the chapter that owns the context.

## Secrets and Vault

**`gitleaks` flags a line I know is not a secret** - Test fixtures, example keys, and documentation snippets trip the default rules. Add the path to the `[allowlist]` in `.gitleaks.toml` with an owner and review date ([Chapter 2](#ch2)); never weaken the rule globally for one file.

**A secret is already in the git history and gitleaks keeps finding it** - Deleting the file in a later commit does not remove history. Remediation order: rotate the credential *first*, then rewrite history (`git filter-repo`), then force-push and have every clone re-fork ([Chapter 2](#ch2)). The rotation is the fix; the rewrite is hygiene.

**`vault kv put` returns `permission denied`** - Your token's policy does not cover the path, or covers it for different capabilities. `vault token lookup` shows the attached policies; check the path globs against the exact path - `shopnow/data/dev/*` is the KV v2 data API, and forgetting the `data/` segment is the most common policy bug ([Chapter 2](#ch2)).

**GitHub Actions fails Vault auth with `permission denied` on JWT login** - The role's `bound_subject` does not match the token's `sub` claim. Echo the claim (`echo $ACTIONS_ID_TOKEN_REQUEST_TOKEN` style debugging or Vault's audit log) and align the binding exactly - repository, environment, ref ([Chapter 2](#ch2), [Chapter 3](#ch3)).

## CI hardening

**Workflow fails with `Resource not accessible by integration`** - The `GITHUB_TOKEN` lacks a permission the step needs. Declare the narrowest permission that works at the job level (`packages: write` for pushes, `security-events: write` for SARIF uploads) rather than widening the repo default ([Chapter 3](#ch3)).

**A third-party action stops working or behaves differently overnight** - Floating `@vN` tags moved. Pin to the commit SHA, let Dependabot propose updates, and consult the public poisoned-action blocklists before re-pinning ([Chapter 3](#ch3)).

**Self-hosted runner job hangs or flakes** - State from a previous job (caches, processes, mounted volumes) survived. One runner per job, disposable container images, and never fork PRs on production runners ([Chapter 3](#ch3)).

## Scanning

**Trivy reports thousands of findings and CI goes permanently red** - Baseline, then gate. Run once with full output, accept the unfixed (`--ignore-unfixed`), gate only on CRITICAL, and grow `.trivyignore` explicitly with review dates ([Chapter 5](#ch5)).

**The same CVE stays after rebuilding** - The base image digest is pinned and stale. Bump the pinned digest (the Dependabot docker PR exists for this) and rebuild; findings in OS packages are fixed by *rebuild events*, not edits ([Chapter 5](#ch5)).

**Semgrep ERROR fails the build on something that is not exploitable** - Suppress the finding explicitly with a reason at the finding site, or narrow the rule's paths; a blanket `--exclude` for the whole ruleset defeats the gate ([Chapter 4](#ch4)).

**Dependency review passes but Dependabot still flags the dependency** - They answer different questions: review checks what a PR *introduces*, alerts cover the whole resolved tree. The dependency was already vulnerable on `main`; fix-forward with a version bump PR ([Chapter 4](#ch4)).

## Admission and cluster

**`kubectl apply` fails with `admission webhook ... denied the request`** - This is the policy working; the message names the rule and the required fix. Fix the manifest per the message. If the message is unclear, that is a policy bug - improve the `message` field ([Chapter 8](#ch8)).

**Everything fails after a policy deploy, including fixes** - The admission webhook's `failurePolicy: Fail` is denying all writes while Kyverno itself is unhealthy. Use cluster-admin access to remove the ValidatingWebhookConfiguration, restore Kyverno, and re-apply policies one namespace at a time ([Chapter 8](#ch8)).

**NetworkPolicy exists but pods still talk freely** - No policy-capable CNI is enforcing. Verify with the positive/negative `nc -zv` test from a scratch pod; install Calico or Cilium if the cluster cannot enforce ([Chapter 9](#ch9)).

**Falco fires constantly on the same benign pattern** - The rule needs a scoping exception (a labeled debug pod, a known system path). Tune the rule's condition with the exception, contribute the change to the rule file, and track the false-positive rate - do not lower the severity until the tuning is done ([Chapter 9](#ch9), [Chapter 12](#ch12)).

## Signing and artifacts

**`cosign verify` fails with `no matching signatures`** - The digest changed after signing (a tag was moved, or the image was re-pushed). Verify by digest, not tag; if the digest genuinely changed, the tamper-test of [Lab 4](#ch5) just caught a real drift - treat as an incident ([Chapter 6](#ch6), [Chapter 8](#ch8)).

**Keyless signing fails in CI with no OIDC token** - The workflow lacks `id-token: write` in `permissions`. It is the only prerequisite for keyless signing and attestations ([Chapter 6](#ch6), [Chapter 7](#ch7)).

## Incidents and compliance

**A page arrives and the runbook step cannot be executed** - The runbook is stale; fix it after the incident as a dated action item, and add the drill cadence ([Chapter 13](#ch13), [Chapter 15](#ch15)). This entry existing in an appendix is the reminder to test runbooks before they are needed.

**kube-bench FAILs that cannot be fixed** - Managed control planes own some node settings. Document each as compensated or accepted with a reason in the evidence store; auditors accept documented risk, not silence ([Chapter 14](#ch14)).

**See also:** the tool-specific troubleshooting sections in the cloud and platform books; [Appendix A](#appA) for which tool owns which question.
