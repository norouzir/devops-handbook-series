# Chapter 10 - Reusable Workflows and Platform Automation {#ch10}

## 10.1 Reusable Workflows: workflow\_call

A reusable workflow is an ordinary workflow file that declares `on: workflow_call` with typed inputs, secrets, and outputs, and is consumed by other workflows as a job-level `uses:`. It is the primary tool against YAML sprawl: the org's canonical CI - checkout, toolchain, test grid, SBOM, attestation - lives once in a platform repository, and twenty service repositories consume it with five lines each, upgrades land as single pull requests, and audits inspect one place. Callers pin the version (`uses: org/platform/.github/workflows/ci.yml@v3` or by SHA), pass `with:` and `secrets:` values, and receive declared `outputs:` through the `jobs.<id>.outputs` map of the calling job.

```yaml
# org/platform/.github/workflows/ci.yml
on:
  workflow_call:
    inputs:
      node-version:
        type: string
        default: '22'
      run-integration:
        type: boolean
        default: false
    outputs:
      image:
        value: ${{ jobs.build.outputs.image }}
    secrets:
      registry-token:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image: ${{ steps.img.outputs.name }}
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v5
        with: { node-version: '${{ inputs.node-version }}', cache: npm }
      - run: npm ci && npm test
```

```yaml
# caller in a service repository
jobs:
  ci:
    uses: org/platform/.github/workflows/ci.yml@v3
    with:
      run-integration: true
    secrets:
      registry-token: ${{ secrets.GITHUB_TOKEN }}
```

Two limits shape large graphs. A reusable workflow may call another reusable workflow up to four levels of nesting deep, and a single workflow run may reach at most 20 unique reusable workflows - both ceilings that push you toward broad, well-parameterized building blocks rather than a deep tree of micro-workflows. Reusable workflows run in the **caller's** context for triggers and permissions but can enforce their own `permissions:` block, which is the mechanism for the SLSA Build Level 3 isolation property mentioned in Chapter 8.

## 10.2 Organization-Wide Distribution

Reusable workflows called across repositories must live in a public repository or - the enterprise pattern - in an internal repository, callable by any repository in the organization that has access. The convention is a dedicated `org/platform` (or `.github`) repository containing workflows, composite actions, and their tests, protected by CODEOWNERS and consumed by SHA pinning through lockfiles. Version policy belongs to the platform team: publish `v<major>` tags, keep `main` deployable, and treat a breaking parameter change as a new major with a migration note. With the Require lockfile policy enabled, consumers upgrade through Dependabot pull requests that update both the reference and its locked commit together.

## 10.3 Chaining Runs and External Automation

Chapter 2 introduced `workflow_run` and `repository_dispatch`; platform automation is where they earn their keep. The `workflow_run` pattern 'CI on main succeeded, so run publish' keeps elevated credentials in a workflow that only ever runs from the default branch, decoupled from pull-request code. `repository_dispatch` is the inbound interface for everything that is not GitHub: the security scanner finishes a scan and dispatches `vuln-found`; the data warehouse completes a load and dispatches `dataset-ready`; the on-call tool dispatches `rollback` with a target digest. Combined with `workflow_dispatch` for humans and `schedule` for sweeps, these four triggers cover virtually every integration need without a bot server.

When workflows are not enough, the REST and GraphQL APIs and the `gh` CLI automate the platform itself: query run history for DORA-style metrics, cancel stuck runs fleet-wide, rotate runner registrations, or create environments programmatically. `gh run watch`, `gh run view --log-failed`, and `gh workflow run` are the three commands engineers should know from memory; the `gh actions-lock` extension joins that list now that lockfiles are GA.

## 10.4 Agentic Workflows on the Horizon

At GitHub Universe in October 2026, **GitHub Agentic Workflows** reached general availability: workflows in which an AI agent is a first-class participant, triggered by the same events and constrained by the same permissions model, reviewing changes, proposing fixes, and executing multi-step tasks inside the Actions runtime. The security model - least-privilege tokens, human approval gates via environments, lockfile-style pinning - matters more here, not less, because an agent with excessive permissions is a faster attacker if compromised. Treat agentic workflows as the newest consumer of every hardening practice in Chapter 12, and start with read-only agents on non-production repositories.

::: {.note}
**Note - multi-cloud compute**

Announced alongside Universe 2026, GitHub Actions can now spread hosted compute across multiple cloud providers for reliability. It is transparent to workflow YAML today - same labels, same billing model - but worth knowing when a regional incident makes runs queue oddly; the platform may be routing around a provider outage on your behalf.
:::

**See also:** [Chapter 4](#ch4) for the actions being composed, [Chapter 9](#ch9) for the deployment shape these workflows encode, and [Appendix B](#appB) for starter workflows to copy.
