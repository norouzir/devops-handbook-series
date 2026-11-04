# Chapter 14 - Enterprise Adoption and Migration {#ch14}

## 14.1 Monorepos and Path-Based Orchestration

At small scale, one workflow per repository is fine. At monorepo scale, the design questions return with force: triggering the right pipelines for changed paths, keeping CI minutes proportional to the change rather than the repository, and giving each team a defensible slice of configuration to own. The standard toolkit: separate workflows per service area with `paths` filters at the trigger level, job-level path detection (`dorny/paths-filter` or a native changed-files step) for workflows that must always start but fan out conditionally, and shared reusable workflows so per-service YAML stays five lines instead of two hundred. The anti-pattern to avoid is the single mega-workflow with nested conditionals - it becomes the place where every team's concerns collide, and its required-check name blocks every merge for every team.

```yaml
# monorepo pattern: one thin workflow per service
name: api CI
on:
  pull_request:
    paths: ['services/api/**', 'libs/shared/**']
  push:
    branches: [main]
    paths: ['services/api/**', 'libs/shared/**']
jobs:
  ci:
    uses: org/platform/.github/workflows/node-service.yml@v3
    with:
      service-dir: services/api
```

## 14.2 Governance: Policy, Rulesets, and Ownership

Enterprise Actions governance has a concrete inventory. **Allowed actions policy** (org/enterprise) restricts which actions workflows may use - by verified creators, by pattern lists, or locally only. **Workflow lockfiles** with the **Require lockfile** policy (GA October 2026) make reviewed commits the executable truth for onboarded workflows. **Organization rulesets** gate changes to `.github/workflows/**` with required review - pair it with CODEOWNERS so platform changes need platform-team approval - and branch protections carry required checks and merge queues. **Reusable workflows from an internal platform repository** give centralized hardening a single place to live. The governance stack is additive, and the correct order of adoption is: token permissions first (cheap, immediate), pinning and lockfiles second, then rulesets and policies as the platform team's confidence grows.

Ownership is the part that technology cannot supply. Define who owns the platform repository, who approves new reusable workflows, who has access to production environments (and how reviewers are rotated), and how an action becomes 'blessed' for org-wide use. Write it down in the platform repo's README, and let rulesets and CODEOWNERS enforce it mechanically. Organizations that skip the ownership step usually end up with governance controls that everyone routes around.

## 14.3 Migrating from Established CI Systems

Migrations succeed when they are ported as contracts, not as YAML. Inventory what each legacy pipeline **delivers** - artifacts, environments, credentials, notifications, compliance evidence - and rebuild those contracts with Actions primitives, leaving cosmetic fidelity behind. The general playbook: freeze feature growth on the legacy system; pick a low-risk service as the pilot; stand up the platform repo with reusable workflows; migrate the pilot end to end including secrets and deployments; write the internal migration guide from its scars; then migrate by domain in dependency order, running both systems in parallel per service until cutover, and decommission deliberately.

| From | What maps well | What needs redesign |
| --------- | ---------------------- | ------------------- |
| Jenkins | Free-style scripts translate to `run:` steps; shared libraries to reusable workflows/composite actions | Plugin-dependent stages (credentials, publishers) map to actions or need rework; agent labels to runner labels; no direct Groovy equivalent - expect logic rewrites in scripts/actions |
| GitLab CI | Stages/jobs map to jobs and `needs`; artifacts and caches have close analogues | Pipeline-level `rules` logic becomes trigger filters plus `if:`; includes map to reusable workflows; child pipelines become `workflow_call` or `workflow_run` |
| CircleCI | Executors map to runner selection/containers; orbs to actions | Workspaces map to artifacts; caching keys translate but performance tuning is re-done; contexts map to environments/secrets |
| Azure DevOps | YAML stages/jobs/steps translate conceptually; variable groups to environments and secrets | Service connections become OIDC federation or environment secrets; templates become reusable workflows; classic pipelines usually need full redesign |

: Table 14.1 - Migration notes by source system

Credentials deserve their own sentence in every migration plan: every long-lived token mirrored from the old system is a liability imported unchanged. Prefer OIDC federation (Chapter 12) for cloud credentials from day one, scope `GITHUB_TOKEN` per job, and put deploy credentials in environments so the privilege boundary travels with the workflow. Teams that skip this step spend the next quarter discovering they have rebuilt their legacy secret sprawl in a new address space.

## 14.4 An Adoption Roadmap and Its Anti-Patterns

A ninety-day shape that works for most organizations: weeks one to three, foundations - token permissions, secrets audit, path-filtered pilot workflow, one dashboard. Weeks four to eight, platform - the internal repository of reusable workflows and composite actions, lockfile adoption in the pilot, OIDC for the pilot's cloud credentials. Weeks nine to twelve, expansion - migration wave one (two or three services), governance policies enabled at report-only level, cost review against Table 13.1. From there, migrate by domain, enable enforcement policies, and let the platform team own upgrades and deprecations - including the platform's own: runner versions, Node runtime changes, and image retirements now arrive on GitHub's schedule, and a team that owns its platform repo absorbs them in hours instead of discovering them in release week.

- **Copy-paste sprawl** - five hundred workflows cloned from each other; cured by reusable workflows and the discipline to review new ones.
- **Everyone's pipeline, no one's pipeline** - no ownership; cured by CODEOWNERS on workflow paths and a platform team with a roadmap.
- **Secret archaeology** - org-wide secrets readable everywhere; cured by environment scoping and an audit with an expiry date.
- **Required-check paralysis** - every check required, so breakage blocks all merges; cured by tiered gates and the merge queue.
- **Deprecation surprise** - runtime and image lifecycles treated as someone else's problem; cured by subscribing to the changelog and owning the platform repo.

The through-line across these three volumes: Docker standardized what software is packaged as, Kubernetes standardized where it runs, and GitHub Actions - or the CI/CD platform of your choice - is where the daily discipline lives that makes those two standards trustworthy. A pipeline is a product with users, an owner, a budget, and a roadmap. Teams that treat it that way ship more, page less, and spend their engineering time on the product rather than on the plumbing. The appendices that follow are the working desk reference; keep them within reach, and automate something today.

**See also:** [Chapter 10](#ch10) for the platform patterns that scale across organizations, [Chapter 12](#ch12) for the governance that makes adoption stick, and [Chapter 13](#ch13) for the cost conversation that follows.
