# Chapter 12 - CI/CD for Terraform {#ch12}

## 12.1 The Automation Model: Plan on PR, Apply on Merge

Terraform's workflow ([Chapter 6](#ch6)) automates into a two-gate pipeline that has become the industry default: on every pull request, the pipeline runs the cheap gates ([Chapter 11](#ch11)) and posts a **speculative plan** as a PR comment - reviewers approve a diff, not a description; on merge to the protected branch, the pipeline **applies** against the shared backend with the same gates re-run and binding. The invariants from Chapter 6 hold unchanged and now become properties of the platform: one place where state lives, every change reviewed as a plan, and - the new one - **no human laptops applying to shared infrastructure**. The pipeline's identity, not an engineer's, is what assumes the cloud role ([Chapter 10](#ch10) federation), which is what makes the audit trail complete: every change traces to a merged commit.

## 12.2 A Worked Pipeline: GitHub Actions

The workflow below is the complete skeleton for one environment root ([Chapter 9](#ch9)'s directory model), using OIDC federation and a saved-plan apply:

```yaml
name: terraform-dev
on:
  pull_request:
    paths: ["environments/dev/**", "modules/**"]
  push:
    branches: [main]
    paths: ["environments/dev/**", "modules/**"]

permissions:
  id-token: write      # OIDC federation to cloud role
  contents: read
  pull-requests: write # post the plan comment

env:
  TF_VERSION: "1.17.0"
  WORKDIR: environments/dev

jobs:
  check:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: ${{ env.WORKDIR }} } }
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with: { terraform_version: "${{ env.TF_VERSION }}" }
      - run: terraform fmt -check -recursive
      - run: terraform init -input=false
      - run: terraform validate
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/ci-terraform-dev
          aws-region: eu-central-1
      - name: plan
        run: |
          terraform plan -input=false -out=tfplan -detailed-exitcode || echo "exit=$?" >> $GITHUB_OUTPUT
        id: plan
      - name: post plan summary
        if: github.event_name == 'pull_request'
        run: terraform show -no-color tfplan > plan.txt

  apply:
    if: github.event_name == 'push'          # merge only
    needs: check
    runs-on: ubuntu-latest
    environment: dev                          # protection rules gate here
    defaults: { run: { working-directory: ${{ env.WORKDIR }} } }
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with: { terraform_version: "${{ env.TF_VERSION }}" }
      - run: terraform init -input=false
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/ci-terraform-dev
          aws-region: eu-central-1
      - run: terraform apply -auto-approve -input=false
```

The design decisions inside it matter more than the YAML. Concurrency for the apply job must be `group: terraform-${{ github.ref }}` with cancel-in-progress *false* - two applies racing one state is the corruption scenario [Chapter 7](#ch7) exists to prevent. The `environment:` gate is where branch protection and required reviewers live for prod roots ([Chapter 9](#ch9)'s promotion). `plan -detailed-exitcode` distinguishes "no changes" (exit 0) from "changes" (2) from "error" (1), letting pipelines skip empty applies. And the PR plan is *speculative* - computed, shown, discarded - while the merge apply re-plans fresh: the reviewed plan and the executed plan are the same only when the pipeline re-computes against a moved base, which is exactly the honesty Chapter 11 demanded.

::: {.warn}
**Watch out - the merge race**

A PR approved on a plan from Tuesday can be merged Thursday *after* another change landed. The re-planned apply catches the difference - unless the pipeline skips re-planning and applies the stale artifact. Either re-plan on merge (the pattern above) or apply only the exact saved plan with a pipeline that fails if the base commit moved. Never neither.
:::

## 12.3 Terraform-Specific Pipeline Hygiene

Four habits separate sustainable pipelines from fragile ones. **Pin the binary** via the version file ([Chapter 2](#ch2)) so CI and laptops agree; **init with `-input=false`** everywhere so no pipeline ever waits on a prompt that cannot come; **cache `.terraform/providers`** (the lock file makes the cache verifiable) to keep runs fast; and **plan files and logs are sensitive** ([Chapter 10](#ch10)) - upload them as artifacts with short retention, and never paste raw plans into public comments. For monorepos, path filters scope runs to the roots whose inputs changed (`dorny/paths-filter` or the native `paths:` above), and a scheduled **drift job** - `terraform plan -detailed-exitcode` nightly per root, alerting on exit 2 - turns drift ([Chapter 14](#ch14)) from folklore into a dashboard.

## 12.4 The Automation Platforms: When to Move Past Raw CI

Raw CI is the right tool until coordination becomes the bottleneck: many roots needing one queue per state, plan comments becoming stale, per-PR credentials sprawl, and the growing sense that the workflow file *is* a product you now maintain. The dedicated automation layer exists for exactly that stage. **Atlantis** (open source, self-hosted) turns PR comments into workflow: `atlantis plan` and `atlantis apply` per PR, one lock per project, policy checks via OPA or Terraform Policy - a strong fit for teams that want the model without a SaaS dependency. **Terrateam** and similar GitHub-native products offer the same shape with less hosting. **HCP Terraform** ([Chapter 13](#ch13)) is the platform endgame: VCS-driven runs, remote execution, per-workspace policy with enforcement modes, drift detection, and the run queue - worth its cost precisely when the estate is many teams, many roots, and compliance needs the audit trail to be a feature rather than a log query.

The migration path is additive, not disruptive: keep the repos and layout, move the *apply* gate into the platform first (its run queue and locking are the scarce goods), leave CI on fmt/validate/tests, and delete the homegrown plan-comment plumbing last.

## 12.5 Lab 5: A Pipeline Against a Disposable Target

::: {.lab}
### Lab 5 - Plan on PR, apply on merge, with gates {#lab5}

1. Put the Chapter 8 two-module project on GitHub in a fresh repo, with the environment layout from [Chapter 9](#ch9) and a pinned `.terraform-version`.
2. Write the pipeline from Section 12.2, adapted: replace the AWS credential step with `AWS_ACCESS_KEY_ID=minioadmin` style environment variables pointing the S3 backend at a local MinIO container (`docker run -d -p 9000:9000 minio/minio` + `mc` to create the bucket), so the full remote-state-and-locking story runs on your laptop's CI runner.
3. Open a PR that changes one module input; verify the pipeline posts a plan summary and the gates (fmt, validate) run - then push a `fmt`-breaking change and watch the gate fail before any plan.
4. Merge and watch the apply job run against the protected branch; inspect the run queue behavior by opening a second PR and confirming applies serialize (concurrency group) rather than race.
5. Add the scheduled drift job (cron, nightly) and force drift by `docker stop`-ing a managed container; confirm the morning run flags exit 2, then repair it the [Chapter 6](#ch6) way and note which direction you chose.
6. Bonus: add OPA or Terraform Policy to the PR plan, with one rule ("no container publishes privileged ports"), and confirm a violating PR is gated with a readable message.
:::

**See also:** [Chapter 13](#ch13) for the platform that replaces this plumbing at scale, [Chapter 14](#ch14) for the drift job's day job, and [Appendix A](#appA) for the flag reference the pipeline leans on.
