# Chapter 9 - Managing Multiple Environments {#ch9}

## 9.1 The Question Every Team Asks Wrong First

"How do I do multiple environments in Terraform?" is usually asked expecting a feature name, and the honest answer is a *design decision*: Terraform provides both **workspaces** and plain **directory layouts**, and the two answer different questions. The confusion dissolves once the questions are separated. *Where does state live per environment?* (isolation). *How does code promote between environments?* (flow). Workspaces answer the first within one configuration; directories answer both by making environments *separate roots* that share modules. Most production estates in 2026 use directories (or platform workspaces, [Chapter 13](#ch13)) for real environments and reserve CLI workspaces for genuinely parallel variants of one configuration.

## 9.2 CLI Workspaces: Parallel Variants, Not Environments

`terraform workspace new dev && terraform workspace select dev` switches between named *state files* stored under one backend (the `s3` backend keys them as `env:/dev/...`). The configuration stays identical; only `terraform.workspace` - an expression exposed to configuration - varies. That is the feature and its ceiling: environments that differ *only* in state and a few `terraform.workspace` conditionals are a good fit, but branching logic (`count = terraform.workspace == "prod" ? 3 : 1`) scatters environment differences through the code, and one state backend means one blast radius. The classic legitimate uses are ephemeral per-branch states in CI and preview variants; the classic misuse is three environments' worth of `if workspace ==` sprinkled across a hundred resources.

## 9.3 Directory Layouts: Environments as Composition Roots

The layout that scales makes each environment a thin root module whose only job is to bind inputs to shared modules ([Chapter 8](#ch8)):

```text
atlas-infra/
├── modules/               # shared, tested building blocks
│   ├── network/
│   ├── cluster/
│   └── web-service/
├── environments/
│   ├── dev/
│   │   ├── main.tf        # module "network" { ... }, module "web" { ... }
│   │   ├── backend.tf     # state key .../dev/...
│   │   └── terraform.tfvars
│   ├── staging/
│   └── prod/
└── .terraform-version
```

Environments are now *separate states with separate backends and separate IAM* - prod is a different role, different bucket path, often a different account - and promotion is *code flow*: a change to `modules/` merges through dev, then staging, then prod pull requests, each root re-planning the same module against its own inputs and state. Differences between environments live in the roots as *data* (sizes, counts, feature flags), not as logic - and anything genuinely different-by-design (prod-only WAF, dev-only debug containers) is visible in the root file where the difference is, not buried in a conditional three modules deep.

::: {.note}
**Best practice - make prod the reviewed promotion, not a checkout**

In the directory model, nobody "works in prod": engineers open PRs against dev, and the same module versions flow forward through staging to prod by merge order. The prod root's backend and provider roles ([Chapter 4](#ch4)) ensure that even a compromised laptop cannot apply to prod without both the credentials *and* the reviewed plan - the layout is itself a security control.
:::

## 9.4 The tfvars Strategy and the Precedence Trap

With directory roots, each environment carries its `terraform.tfvars` (committed, non-secret) plus any `ENV_override.tfvars` (generated or injected, secret). The precedence rules from [Chapter 5](#ch5) now have a production corollary: *implicit* files (`*.auto.tfvars`) load silently and should be banned by convention in favor of explicit `-var-file` flags in the pipeline - because a plan's correctness should not depend on which files happened to be in the directory when someone ran it. Environment parity is then enforceable by review: if the prod root references a module version dev has not exercised, the PR graph shows it; if prod needs a knob dev lacks, the missing input is a compile-adjacent error, not a Friday surprise.

## 9.5 Promotion Pipelines and the Cost of Symmetry

The promotion flow that teams converge on: PR to dev applies automatically on merge; dev to staging is a PR that bumps the shared module ref (or simply re-plans after the module commit lands, in monorepo); staging to prod is a PR that requires review and applies in a gated pipeline ([Chapter 12](#ch12)). Two discipline points keep it honest. First, *destroy protection follows the promotion*: `prevent_destroy` lifecycles and backend access policies are strictest on prod roots, and CI refuses `-destroy` plans on prod without a labeled override. Second, *asymmetry is normal and should be explicit* - dev may tolerate smaller replicas and no backups, but the farther an environment's *shape* drifts from prod, the less "staging passed" means. Parity is a dial, not a dogma; the dial's setting should be a documented decision, not an accident.

## 9.6 Choosing: A Decision Table

| Criterion | CLI workspaces | Directory roots |
|-----------|----------------|-----------------|
| State isolation | Shared backend, keyed by name | Fully separate backends/accounts possible |
| Code reuse | One configuration, `terraform.workspace` conditionals | Shared modules, per-env composition |
| Blast radius | One backend | Per-environment |
| Differences between envs | Logic in code (count/ternary) | Data in roots |
| Team-scale prod guardrails | Weak | Strong (IAM + pipeline) |
| Best for | Parallel variants, ephemeral previews | Real environments at team scale |

**See also:** [Chapter 8](#ch8) for the modules these roots compose, [Chapter 12](#ch12) for the pipeline that promotes them, and [Chapter 13](#ch13) for the platform alternative (HCP Terraform workspaces per environment).
