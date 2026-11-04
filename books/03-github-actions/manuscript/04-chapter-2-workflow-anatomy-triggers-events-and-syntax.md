# Chapter 2 - Workflow Anatomy: Triggers, Events, and Syntax {#ch2}

## 2.1 Where Workflows Live and What They Are

A workflow is a YAML file placed under `.github/workflows/` in the repository root. The filename does not matter to the platform - only the directory does - but the `name:` field inside the file becomes the title under the Actions tab, so choose something you will recognize in a dropdown six months from now. Workflow files are versioned with the code they build, which is the philosophical heart of Actions: the pipeline is code, reviewed in pull requests, reverted in reverts, and blameable with `git log`. Any commit that adds or edits a workflow file only takes effect for events occurring after that commit lands on the default branch (for most event types), a subtlety that explains many 'why did my change not apply?' mysteries.

Every workflow must contain two top-level keys: `on`, declaring the events that trigger it, and `jobs`, declaring the work. A top-level `permissions:` block, which you should consider mandatory, scopes the automatic `GITHUB_TOKEN`. Optional keys - `name`, `run-name`, `env`, `defaults`, `concurrency` - refine naming, default environment variables, and queueing behavior. The full grammar is large, but a working mental model needs only about a dozen keys, which Appendix A compresses into a reference table.

## 2.2 Anatomy of a Complete Workflow

```yaml
name: Service CI
run-name: 'CI for ${{ github.ref_name }} by @${{ github.actor }}'

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      verbose:
        description: 'Enable verbose logging'
        type: boolean
        default: false

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

defaults:
  run:
    shell: bash

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
      - name: Install dependencies
        run: npm ci
      - name: Build
        if: ${{ inputs.verbose != true }}
        run: npm run build
      - name: Build (verbose)
        if: ${{ inputs.verbose == true }}
        run: npm run build -- --verbose
```

Read it top to bottom: the workflow reacts to three event types; it runs at most one run per branch at a time, canceling superseded runs; every step defaults to bash; and the single job is capped at 15 minutes. The `if:` conditions show the expression language at work - `inputs.verbose` refers to a `workflow_dispatch` input, and expressions are always wrapped in `${{ }}`. This is the vocabulary of the next five chapters; nothing else about workflow syntax is conceptually new.

::: {.note}
**Best practice - name runs for humans**

`run-name` is interpolated per run and appears in the Actions list and status checks. Putting the branch, actor, and dispatch inputs into `run-name` makes triage dramatically faster in busy repositories than a wall of identical titles.
:::

## 2.3 Push and Pull Request Triggers

`push` and `pull_request` are the workhorse events. Both accept `branches` and `branches-ignore` filters, `tags` filters, and `paths` and `paths-ignore` filters evaluated against changed files. Use them to keep monorepo pipelines quiet: a workflow that only touches `services/api/` should not run for a documentation typo under `docs/`. The `pull_request` event deserves special care: by default it fires for `opened`, `synchronize`, and `reopened` activity types, and it runs against the **merge commit** of the pull request, which is exactly what you want to test. It also runs the workflow from the pull request's head branch, with a read-only token and no access to repository secrets - a deliberate security boundary that Chapter 12 examines in detail.

```yaml
on:
  pull_request:
    branches: [main]
    paths:
      - 'services/api/**'
      - '.github/workflows/api-ci.yml'
    types: [opened, synchronize, reopened]
```

Two classic traps live here. First, `branches:` on a `pull_request` filter matches the **base** branch, not the head branch - filtering by head branch requires an `if` condition with `startsWith(github.head_ref, 'feature/')`. Second, on very active repositories a push to `main` plus the merge of the pull request that caused it produces two near-identical runs; a `concurrency` group with `cancel-in-progress` (Section 2.7) is the standard cure.

The third common workhorse is `push` with tags for release builds. Tag triggers fire on tag creation only, not on later force-updates, and combine well with `workflow_dispatch` for rebuilds. If you need to react to releases rather than raw tags, the `release` event carries activity types such as `published` and `prereleased` and is generally the better signal for publishing automation.

## 2.4 Manual and External Triggers

`workflow_dispatch` turns any workflow into a button. Inputs accept strings, booleans, numbers, and - since the current platform generation - `choice` dropdowns and `environment` inputs. Dispatch inputs arrive in the `inputs` and `github.event.inputs` contexts, and the run is bound to the ref you pick (a branch or a tag) in the UI or API. `gh workflow run deploy.yml -f environment=staging` is the CLI form you will type most often. Manual triggers are how teams implement 'run this migration now' and 're-run the release build against this tag' without granting engineers write access to CI configuration.

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        type: choice
        options: [staging, production]
        default: staging
      image_tag:
        description: 'Image tag to deploy'
        required: true
```

`repository_dispatch` is the inbound webhook: an authenticated API call - `POST /repos/{owner}/{repo}/dispatches` with a token that has the `repo` scope - triggers workflows that listen for its `event_type`. It is the standard bridge from external systems such as artifact scanners, ticket systems, or partner pipelines: the external system fires the dispatch, and your workflow receives the payload in `github.event.client_payload`. Treat the payload as untrusted input, exactly like pull-request titles; Chapter 12 shows why that sentence matters.

## 2.5 Scheduled Workflows

`schedule` accepts standard cron expressions in UTC and is the natural home for nightly sweeps: dependency audits, slow end-to-end suites, data reindexing, and certificate-expiry checks. Three operational realities bite everyone once. First, scheduled workflows run only from the default branch, so feature branches cannot have their own timers. Second, GitHub explicitly delays scheduled runs during periods of high load - cron is 'at least this often, eventually', not a precise scheduler, and clocks in non-production brains should not be set tighter than five-minute granularity. Third, long-lived repositories have schedules disabled automatically after 60 days of repository inactivity, which surprises teams whose nightly job silently stopped during a holiday freeze.

```yaml
on:
  schedule:
    - cron: '30 3 * * 1-5'   # 03:30 UTC, weekdays only
```

::: {.warn}
**Watch out - cron is UTC, always**

Cron fields are evaluated in UTC with no timezone support. A team in Tehran specifying `0 9 * * *` gets 12:30 local time in summer and 11:30 in winter. Compute the offset deliberately, and prefer a comment stating the intended local time so the next editor knows what to preserve.
:::

## 2.6 Chaining Runs: workflow\_run and merge\_group

`workflow_run` lets one workflow react to the completion of another: 'after CI succeeds on main, run the publish workflow'. It fires in the context of the default branch, with write-qualified tokens available, which is precisely why the security guidance recommends using it - instead of `pull_request_target` - to grant elevated privileges to workflows that need to act on untrusted branch content. The `merge_group` event exists for the merge queue: when a repository requires linear history at scale, GitHub batches pull requests into a merge group and lets you run final verification against the prospective merge result before anything touches `main`. Both events are Part II material in spirit, but you should recognize their names now because they show up in every mature setup.

The remaining event family is the webhook set: `issues`, `issue_comment`, `check_run`, `deployment_status`, `create`, `fork`, `discussion`, and roughly a dozen more. They let repository automation live in workflows rather than in separately hosted bots. The pattern to remember is uniform: declare the event, filter by activity type, and treat every field of `github.event` as attacker-controlled if it originates outside your collaborators.

## 2.7 Skipping, Canceling, and Queueing Runs

Commit messages containing `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`, or `[actions skip]` suppress push and pull\_request runs - useful for pure documentation bumps made by bots that would otherwise double the load. `concurrency` groups give you explicit control over what happens when runs pile up: runs sharing a group queue instead of running simultaneously, and `cancel-in-progress: true` replaces the queued run with the newest one. Group keys are arbitrary strings, conventionally built from refs or deploy targets: `group: cd-${{ github.ref_name }}` serializes deployments per branch, while `group: cd-production` serializes production globally.

::: {.note}
**Best practice - cancel CI, serialize CD**

For CI on pull requests, cancel superseded runs aggressively; nobody reads the logs of a commit that was already superseded. For deployments, serialize per environment and never cancel mid-deploy - a canceled run at the wrong moment is an outage story. Express that policy once per workflow in the `concurrency` block rather than in team folklore.
:::

**See also:** [Chapter 3](#ch3) for the jobs this syntax declares, [Chapter 5](#ch5) for expressions and contexts, and [Appendix A](#appA) as the syntax reference you will keep open.
