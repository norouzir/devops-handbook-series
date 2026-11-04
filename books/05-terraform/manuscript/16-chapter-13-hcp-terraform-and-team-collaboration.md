# Chapter 13 - HCP Terraform and Team Collaboration {#ch13}

## 13.1 From CLI Tool to Platform

Everything through [Chapter 12](#ch12) runs Terraform as a CLI orchestrated by your CI. **HCP Terraform** (the 2024 rebrand of Terraform Cloud) is the alternative venue: HashiCorp's hosted platform where the *runs* themselves execute remotely - state lives in managed workspaces, plans and applies run on HashiCorp-operated (or self-hosted agent) workers, and locking, run history, approvals, policy, and drift detection are features rather than plumbing. Its self-hosted sibling, **Terraform Enterprise**, delivers the same product for estates that cannot use SaaS. The CLI remains the authoring surface - you still write HCL locally, still `fmt` and `validate` - but the word *workspace* now means something specific: **a unit of Terraform execution with its own state, variables, and run queue**, typically mapped one-to-one to an environment root ([Chapter 9](#ch9)).

## 13.2 Workspaces, VCS-Driven Runs, and the Remote Workflow

The platform's core loop mirrors Chapter 12's pipeline with the plumbing removed: connect a repository, map directories to workspaces, and HCP Terraform runs speculative plans on PRs (posted as comments) and applies on merge - the run queue serializes writes per workspace, eliminating the concurrency guardrails you built by hand. The CLI joins via the `cloud` block (successor lineage of `terraform { backend "remote" }`), after which `terraform plan` and `apply` execute *remotely* with results streamed back; `terraform login` handles the token. Variables live in the platform (with a secret vault tier), environments map to variable sets, and the OIDC dynamic-credentials story ([Chapter 10](#ch10)) is native - no cloud keys stored anywhere.

```hcl
terraform {
  cloud {
    organization = "atlas"
    workspaces { name = "prod-network" }
  }
}
```

The team-visible features are where the platform earns its keep against raw CI: **remote runs** (execution environment is uniform - no laptop drift), **run approvals** (a named team must approve the apply, with the plan attached), **drift detection** (scheduled health checks per workspace), and **audit** (every run, variable access, and approval is an event). For organizations past a handful of teams, those features convert [Chapter 12](#ch12)'s pipeline from a product you maintain into a product you configure.

## 13.3 Governance Surface: Projects, RBAC, Policies, Run Tasks

The governance stack layers on the workspace model. **Projects** group workspaces for RBAC (team "network-admins" owns project *platform*; team "payments" owns project *payments*), and permissions range from read through plan, apply, and admin. **Policy enforcement** (Sentinel, commercial tiers) embeds [Chapter 11](#ch11)'s policy-as-code directly in the run pipeline with enforcement modes: *advisory* (warn), *soft-mandatory* (a privileged actor can override), *hard-mandatory* (no override) - and policy sets scope to projects or workspaces, which is how "payments workspaces may never create public buckets" stops being a review comment. **Run tasks** (HCP Terraform Plus tiers) inject third-party services into the run lifecycle - an Infracost task annotating the plan, a Vault task brokering dynamic credentials, a scanner task gating between plan and apply. The pattern across all three: governance moves from *pipeline code you maintain* to *platform configuration you delegate*.

## 13.4 Stacks: Orchestration Above Workspaces

The 2024-2026 platform headline is **Stacks** - HCP Terraform's orchestration layer for infrastructure that spans many coordinated units. A Stack writes Terraform components (ordinary modules) plus a `tfcomponent.hcl` that declares **deployments** - instances of the stack with their own inputs, state, and lifecycle - and orchestrates them as one unit: create dev, promote the same components to staging, promote to prod, with the platform wiring outputs of one component into inputs of the next across deployments. The documented envelope (roughly 20 deployments, 100 components, 10,000 resources per stack) marks its target: *product-level* infrastructure - "our SaaS platform in 12 regions for 4 tenants" - rather than one team's VPC. Stacks run exclusively on HCP Terraform, which makes them the clearest architectural fork between the CLI world (composition roots, [Chapter 9](#ch9)) and the platform world; this book treats them as the destination for estates whose orchestration code has outgrown the roots, not as a starting point.

```text
Stack: atlas-platform
├── components/
│   ├── network/          # ordinary Terraform module
│   ├── cluster/
│   └── observability/
└── deployments: dev → staging → prod   # orchestrated promotion
```

## 13.5 The Execution Choice: Cloud, Agents, and OpenTofu Interplay

Three operational notes complete the picture. *Execution*: remote runs execute on HashiCorp's workers by default; **agents** (self-hosted runners) extend the platform into private networks and are the standard answer for on-prem providers - the platform queues, your agent executes. *Cost model*: HCP Terraform bills per resource under management on commercial tiers; the free tier covers small teams' real needs, and the resource count metric is worth watching during consolidation. *OpenTofu*: the platform executes HashiCorp Terraform; OpenTofu estates run their own CI path ([Chapter 12](#ch12)) or Atlantis - a decision some organizations weight when choosing venue, and one [Chapter 14](#ch14) revisits as a coexistence strategy rather than a loyalty test.

::: {.note}
**Best practice - move the apply gate first**

Teams migrating from raw CI to HCP Terraform succeed when they move the scarce goods first: the run queue, locking, and approvals. Keep CI for fmt/validate/tests on day one, point applies at platform workspaces, and migrate plan comments and drift jobs last. Migrating everything in one weekend produces two half-pipelines and one very long incident retro.
:::

**See also:** [Chapter 12](#ch12) for the pipeline this platform replaces, [Chapter 9](#ch9) for the workspace-per-environment mapping, and [Chapter 11](#ch11) for how policy slots into remote runs.
