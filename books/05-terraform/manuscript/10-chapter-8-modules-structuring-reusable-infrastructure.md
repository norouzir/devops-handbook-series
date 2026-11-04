# Chapter 8 - Modules: Structuring Reusable Infrastructure {#ch8}

## 8.1 A Module Is a Directory With a Contract

Every Terraform configuration is already a module - the *root module*, the directory you run `terraform` in. A *child module* is any directory referenced from another: a folder containing `.tf` files whose `variable` blocks are its inputs and whose `output` blocks are its return values. That is the entire formalism, and its smallness is the point: the contract is the same language you already write, and the discipline is entirely in how you draw the boundaries.

```text
modules/
└── web-service/
    ├── versions.tf     # required_providers (constraints, not configs)
    ├── variables.tf    # the contract: image, replicas, ports, env
    ├── main.tf         # the objects: container, network attach, labels
    └── outputs.tf      # the returns: endpoint, container ids
```

```hcl
module "atlas_web" {
  source   = "./modules/web-service"
  image    = "nginx:1.27-alpine"
  replicas = 2
  env      = "lab"
}

output "endpoint" {
  value = module.atlas_web.endpoint
}
```

A module call *instantiates* the child's graph into the caller's graph: resources inside the module get addresses prefixed `module.atlas_web.` (visible in `state list` and plans), inputs are bound to `var.*` inside, outputs flow back as `module.atlas_web.<name>`. Modules compose - a module may call other modules - and the same module may be called many times, including with `for_each` (one service per entry) or `count` (N clones).

## 8.2 Sources: Local, Registry, Git

The `source` argument has a small grammar worth knowing whole. Relative paths (`./modules/web-service`) give monorepo modules - versioned with the code that uses them, refactored atomically. Registry addresses (`hashicorp/consul/aws`, or your organization's private registry namespace) give published, semantically versioned modules with documentation rendered on the Registry page. Git sources (`git::https://...//modules/web-service?ref=v1.4.0`) give any-repo reuse without publishing infrastructure, and the double-slash marks the subdirectory. HTTP archives and S3 buckets round out the list. The policy that scales: **pin everything** - registry modules to an exact or pessimistic version, git modules to a tag or SHA. Unpinned sources make `init` a lottery, and a module that moved under you is a plan you did not review.

For teams, the Registry question is *when to publish*: monorepo-relative modules serve a single estate perfectly; the Registry earns its overhead when multiple repositories consume the same building blocks and need independent versioning. Most organizations start relative and promote the stable few.

## 8.3 Designing the Interface: What Makes a Good Module

The craft of modules is interface design, and the rules converge quickly. Modules should *own a coherent thing* - "a web service with its container, its network attachment, and its healthcheck" is a module; "all networking" and "all containers" are folders. Inputs should be *the few knobs that vary between call sites*, with sane defaults for the rest: a module with forty variables is a configuration with extra steps. Outputs should be *what callers genuinely consume* - endpoint, IDs - not a firehose. And the module should *hide its providers*: declare `required_providers` with constraints, accept provider *configurations* via `configuration_aliases` when the caller must choose ([Chapter 4](#ch4)), and never hardcode credentials or regions.

```hcl
# modules/web-service/variables.tf - the contract, documented and validated
variable "image" {
  type        = string
  description = "Container image, including tag."
}

variable "replicas" {
  type        = number
  description = "Number of container instances."
  default     = 1

  validation {
    condition     = var.replicas >= 1 && var.replicas <= 10
    error_message = "replicas must be between 1 and 10."
  }
}

variable "ports" {
  type = list(object({
    internal = number
    external = number
  }))
  description = "Port mappings to publish."
  default     = []
}
```

::: {.note}
**Best practice - refactor into modules when the second consumer exists, not the first**

Premature module extraction freezes an interface before the variation is known. Write it flat, see the real shape of duplication, then extract with confidence - using `moved` blocks ([Chapter 14](#ch14)) to re-address existing infrastructure into the module without recreation. The `moved` block works across module boundaries: `moved { from = docker_container.web  to = module.atlas_web.docker_container.web }` adopts the old object into the new structure with zero destroy.
:::

## 8.4 Composition Patterns That Recur

Three shapes cover most estates. The *layered stack*: a foundation module (network, clusters) consumed by service modules through outputs and remote state ([Chapter 7](#ch7)) - layers change slowly, services change fast. The *golden module*: one vetted module per platform primitive ("our RDS", "our EKS cluster") encoding the organization's guardrails as defaults, consumed by teams who should not re-derive them - this is where policy-as-code ([Chapter 11](#ch11)) and golden modules agree. The *composition root*: a thin root module per environment that only binds inputs to modules - no raw resources - so an environment file reads like a bill of materials ([Chapter 9](#ch9) builds this). Against these, two anti-patterns recur and are worth naming: the *mega-module* that owns a platform's universe (slow plans, wide blast radius, interface churn), and the *wrapper-only module* that adds one `resource` and a pass-through variable (call the resource; the wrapper adds a hop, not a boundary).

## 8.5 Versioning and the Upgrade Path

Published modules carry semver tags; consumers pin and upgrade deliberately. Inside a monorepo, module "versions" are just commits - refactors are atomic across callers, and the upgrade path is a pull request rather than a release note. Either way, the mechanics of changing a consumed module are the same as any other plan: read the diff. Module authors owe consumers *stable outputs and additive changes*; module consumers owe themselves `-upgrade`-free init (lock files pin module versions too, alongside providers) and a habit of reading module changelogs like provider changelogs. When an interface *must* break, the author's `moved` blocks and variable defaults should carry callers across the gap where possible - the difference between an upgrade and a rewrite.

## 8.6 Lab 4: Build a Module, Call It Twice

::: {.lab}
### Lab 4 - Extract, contract, compose {#lab4}

1. From the Chapter 6 project, extract a `modules/web-service` module: move the container resources, define `image`, `env`, and `ports` as validated inputs, and output the endpoint. Wire the root to call it, add the `moved` block that re-addresses the existing container into the module, and verify the plan is **zero changes** - the module extraction must not touch infrastructure.
2. Give the module a second consumer: call it again as `module.atlas_api` with a different image and port. Plan, read the diff (two new objects, old one untouched), apply, and confirm both endpoints work.
3. Publish-shape check: `terraform fmt -recursive`, then `terraform validate` from *inside* the module directory (modules must validate standalone), then try calling the module with `replicas = 0` and read the validation error - your contract speaking.
4. Exercise `for_each` at the composition root: a locals map of three services driving `module "svc" { for_each = ... }`, then plan/apply and inspect `terraform state list` to see the `module.svc["web"]` addressing that [Chapter 3](#ch3)'s identity rules predicted.
5. Tear down cleanly with `terraform destroy`, and note in the module's README (yes, write it) what the interface is - a module whose contract lives only in code is a module whose next caller will guess.
:::

**See also:** [Chapter 9](#ch9) for environments built from module compositions, [Chapter 11](#ch11) for testing modules, and [Chapter 14](#ch14) for `moved`-based refactoring at estate scale.
