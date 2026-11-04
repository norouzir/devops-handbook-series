# Chapter 3 - Hardening CI/CD: Least-Privilege GitHub Actions {#ch3}

## 3.1 The Crown Jewel Problem

A CI platform occupies a unique position in the threat model: it is a machine that automatically downloads code from many sources and executes it with production credentials attached. That is the honest description of GitHub Actions, and it is why pipeline security is not one control but a posture. The **tj-actions/changed-files compromise (March 2025)** is the canonical modern example: a widely used third-party action had its version tags rewritten to point at a commit that dumped the runner's process memory - environment variables, `GITHUB_TOKEN`, any secrets in scope - into the build logs of every workflow that referenced it. Every downstream pipeline *asked for* that code by tag, the tag was trusted, and the runner did the rest. The lesson generalizes beyond one action: **anything the workflow executes becomes part of your security perimeter**, and everything the workflow can touch becomes exfiltration scope.

This chapter hardens the four surfaces that define that perimeter: the workflow's own token, the third-party code it executes, the credentials it uses to deploy, and the runner it executes on. All examples run against the `shopnow` repository's existing pipelines from the GitHub Actions book - same workflows, new constraints.

## 3.2 The GITHUB_TOKEN: Least Privilege by Default

Every workflow receives an automatic **`GITHUB_TOKEN`**, a scoped installation token whose default permissions are set per repository and per organization. The single highest-leverage setting in GitHub Actions security lives in the repository settings: **default workflow permissions: read repository contents and packages**. With that default, a compromised workflow can read the code but cannot push commits, publish packages, or mutate releases. Workflows that genuinely need more then declare it - as narrowly as possible:

```yaml
# .github/workflows/shopnow-ci.yml
permissions:
  contents: read          # the whole-workflow baseline

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      # ... build and test with no write powers at all

  publish:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write     # only this job may push images
    steps:
      - uses: actions/checkout@v7
      # ... docker build & push to ghcr.io
```

Job-level permissions override the workflow level, so the published job gets exactly `packages: write` and the test job never does. The audit habit: grep your repository for `permissions:` and treat any workflow without the key as a finding - the token silently inherits the default, and the default is only as safe as the last person who touched the settings page.

::: {.warn}
**Watch out - pull_request_target runs privileged code from forks**

`pull_request_target` executes in the context of the *base* repository, with access to its secrets and a mutable `GITHUB_TOKEN` - and it checks out pull-request code. A workflow that combines both (checkout the fork's code, then run it, then use a secret) lets any internet stranger execute code inside your privileged environment by opening a pull request. The safe pattern is to keep unprivileged `pull_request` workflows for untrusted code and reserve `pull_request_target` for label/comment-triggered steps that never execute the fork's scripts.
:::

## 3.3 Third-Party Actions: Pin to the Commit SHA

`uses: owner/action@v4` is a *floating* reference: whoever controls the repository can move the tag to any commit, which is precisely the tj-actions failure mode. The mitigation is **SHA pinning** - reference the exact commit, with a version comment for humans:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v7.0.0
- uses: step-security/harden-runner@0634a2670c59f64b4a01f0f96f84700a4088b9f0 # v2.12.0
```

Pinning converts "trust the tag forever" into "trust this exact code, reviewed once" - and Dependabot then opens pull requests that bump the pinned SHA when new releases appear, restoring update flow without restoring the floating reference. The organizational complement is the **allowed actions policy** (Settings → Actions → General → Actions permissions): a public repository may consume only actions from an approved allowlist, which converts a supply-chain free-for-all into an inventory. The TJ-SAP public blocklists of poisoned actions exist; the allowlist is what actually scales.

## 3.4 OIDC: Deploy Without Stored Credentials

The highest-value stored credentials in most repositories are the cloud keys in Actions secrets - a static AWS access key, a Vault AppRole secret-id, or a service-account JSON blob, all of which are readable by every privileged workflow and leakable by any of [Chapter 3](#ch3)'s failure modes. **OIDC federation** removes the class of problem rather than individual instances: the workflow requests a short-lived identity token from GitHub, the cloud (or Vault, per [Chapter 2](#ch2)) trusts GitHub's issuer, and the deployment authenticates as *the repository and environment* - no stored secret, nothing to leak, automatic expiry. The mechanics differ per cloud but the pattern is identical, and each cloud book's CI/CD chapter built it for its platform: `aws-actions/configure-aws-credentials` for AWS, `azure/login` for Azure, `google-github-actions/auth` for GCP. The security-grade details that matter everywhere: bind the role to the **environment** claim (so only the production environment's required reviewers can assume production roles), scope trust to the exact repository and ref pattern, and keep token TTLs short.

## 3.5 Runners and Runtime Visibility

GitHub-hosted runners are ephemeral VMs: each job starts fresh and is destroyed after, which caps blast radius by design. **Self-hosted runners** trade that isolation for control - and inherit the threat: a runner that persists between jobs accumulates state, and one that hosts `pull_request` workflows from forks is an unauthenticated code-execution service. The rules that make self-hosted safe: never expose them to fork pull requests, run one runner per job in a disposable container or VM image, and isolate runners that touch production credentials in a dedicated repository and network zone. For visibility on any runner, **StepSecurity's `harden-runner`** (pinned above) watches outbound traffic and process trees during the job and flags or blocks exfiltration endpoints - it is the closest thing the platform has to aEDR for CI, and it would have surfaced the tj-actions dump in real time.

## 3.6 Environments and Deployment Gates

The final hardening layer is the one humans feel: **GitHub Environments**. A workflow job with `environment: production` can require reviewer approval, restrict to protected branches, and hold its own (fewer, better-scoped) secrets. The deploy job that ships `shopnow` to the cluster waits for a named maintainer on every run to `main`; the OIDC role it assumes is bound to the environment's subject claim, so the reviewer's approval is not ceremonial - it is the second factor in the deployment authorization. This is [Chapter 1](#ch1)'s "every control is automated or it does not exist" made precise: the automated pipeline carries the change to the door, and the gate decides whether the door opens.

::: {.lab}
### Quick Check - Audit Your Own Workflows

Run three commands against any repository you maintain: `rg -n "uses:" .github/workflows/` (which actions, and are they SHA-pinned?), `rg -Ln "permissions:" .github/workflows/` (which workflows inherit default token permissions?), and `rg -n "pull_request_target" .github/workflows/` (does any privileged workflow execute fork code?). Anything the audit surfaces is a concrete, ranked to-do list - and the answer to all three should be boring.
:::

**See also:** [Chapter 2](#ch2) for the Vault OIDC role these workflows authenticate to; [Chapter 4](#ch4) for the scanners that gate the pull requests themselves; the GitHub Actions book's enterprise chapter for organization-wide policy at scale.
