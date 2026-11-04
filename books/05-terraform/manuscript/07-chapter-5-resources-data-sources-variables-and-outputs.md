# Chapter 5 - Resources, Data Sources, Variables, and Outputs {#ch5}

## 5.1 Resources: The Objects Terraform Owns

A `resource` block declares an object Terraform creates, tracks, updates, and destroys. Every resource type's schema comes from its provider ([Chapter 4](#ch4)), and the Registry documents it: required and optional arguments, computed attributes, and timeouts. What the Registry cannot teach is the *behavior model*, which is uniform across all providers and is the part worth internalizing:

- **Create, read, update, delete** map to plan's `+`, refresh, `~`, and `-`. The plan shows, attribute by attribute, which changes apply in place (`~`) and which force *replacement* (`-/+`) - the distinction between "patch the instance" and "rebuild the instance", and the single most important line in any plan to read twice.
- **Immutability varies per attribute.** Most string attributes update in place; things like instance disk-image or container image frequently force replacement. The provider schema's *ForceNew* markers encode this, and the plan renders it as `-/+`.
- **Explicit dependencies override inference.** Terraform automatically orders operations when one resource references another's attribute (`networks_advanced.name = docker_network.app.name` implies the network exists first). When there is no reference but there *is* a real dependency - a database that must exist before an app that merely stores its address in config - `depends_on = [docker_network.app]` makes it explicit.

Inside `resource`, the `lifecycle` block tunes the behavior model. The four arguments that matter in daily work: `create_before_destroy = true` flips replacement order so the new object is created before the old is destroyed (zero-downtime swaps; see [Chapter 14](#ch14)); `prevent_destroy = true` makes any plan containing this resource's destruction fail immediately (attach it to databases and clusters); `ignore_changes = [image]` excludes attributes from plans (the standard escape hatch for objects another system mutates, like auto-tagging); and `replace_triggered_by` ties replacement to another resource or expression changing.

```hcl
resource "docker_container" "db" {
  name  = "atlas-db"
  image = "postgres:17-alpine"

  lifecycle {
    prevent_destroy       = true
    create_before_destroy = true
    ignore_changes        = [restart]
  }
}
```

## 5.2 Data Sources: Reading What You Do Not Own

A `data` block *fetches* information about an object that something else manages - an AMI chosen by query, the current client's identity, an existing VPC, a TLS certificate from a secret manager. Data sources are read-only and evaluated during planning, which makes them the bridge between Terraform-managed infrastructure and the rest of the world:

```hcl
data "docker_registry_image" "nginx" {
  name = "nginx:1.27-alpine"
}

resource "docker_image" "nginx" {
  name          = data.docker_registry_image.nginx.name
  pull_triggers = [data.docker_registry_image.nginx.digest]
}
```

The distinction to hold onto: if Terraform creates it, it is a `resource`; if Terraform only *needs to know about* it, it is a `data` source. A common anti-pattern is wrapping objects Terraform itself created elsewhere in data sources to "find" them - that hides real dependencies from the graph. Cross-stack references should flow through outputs and remote state ([Chapter 7](#ch7)) or through modules ([Chapter 8](#ch8)), not through data-source queries that can silently match the wrong object.

## 5.3 Input Variables: The Configuration's API

`variable` blocks declare the inputs a configuration or module accepts. Each has a name, an optional `type` constraint, an optional `default`, a `description`, and - the two that matter in production - `validation` blocks and the `sensitive` flag:

```hcl
variable "container_port" {
  type        = number
  description = "Port nginx listens on inside the container."
  default     = 80

  validation {
    condition     = var.container_port > 0 && var.container_port < 65536
    error_message = "container_port must be a valid TCP port."
  }
}

variable "image_tag" {
  type      = string
  sensitive = false
}
```

Values arrive from four places, in ascending precedence: `default`, then `terraform.tfvars` and `*.auto.tfvars` files, then `--var-file` flags, then `-var` flags on the command line, with environment variables `TF_VAR_name` slotting in for CI. The `validation` block is the quiet workhorse: it turns "why did the plan fail?" into a sentence at the right place, and since Terraform 1.9 validation expressions may reference other objects - which enables cross-field validation like "if `env` is `prod`, `min_size` must be >= 2". `sensitive = true` does not encrypt anything; it suppresses the value from plan/apply *display* ([Chapter 10](#ch10) explains what that does and does not protect).

## 5.4 Locals: Computed Values with One Definition

`locals` are named expressions evaluated within the configuration - the place for values that are derived rather than input: concatenated names, tag maps applied everywhere, CIDR math, the map that drives a `for_each`. The rule is one definition, many uses: a naming local used in fifty resources changes in one line, and every plan that follows shows the same rename rippling correctly. Resist the temptation to make locals that merely alias a variable (`local.name = var.name`); indirection without transformation is noise.

```hcl
locals {
  owner     = "platform"
  project   = "atlas"
  common_tags = {
    Project = local.project
    Owner   = local.owner
    Managed = "terraform"
  }
}
```

## 5.5 Outputs: The Configuration's Return Values

`output` blocks declare values that outlive the configuration: printed after `apply`, queryable with `terraform output`, consumable by other stacks via remote state, and - in modules - the module's public interface ([Chapter 8](#ch8)):

```hcl
output "web_endpoint" {
  description = "Local URL of the web container."
  value       = "http://localhost:${docker_container.web.ports[0].external}"
}

output "database_password" {
  value     = random_password.db.result
  sensitive = true
}
```

Outputs should be a deliberate, small set - values another team or stack genuinely consumes - not a mirror of every attribute. Every output printed by `apply` is also a value stored in state and shown in plans; `sensitive` applies here as it does for variables.

## 5.6 The Dependency Graph, Visually

Everything above composes into a directed acyclic graph that Terraform builds automatically from references: resources are nodes, references are edges, and the plan/apply engine walks it in dependency order, executing independent branches *in parallel* (bounded by `-parallelism`, default 10). The graph is inspectable - `terraform graph | dot -Tsvg > graph.svg` renders it with Graphviz - and it is the honest answer to "why did Terraform destroy X because I changed Y?": X depended on Y, and the plan said so in the diff you did not read. Reading plans as graph decisions rather than line edits is the mental shift that separates confidence from luck.

**See also:** [Chapter 3](#ch3) for the expression syntax inside all of these blocks, [Chapter 6](#ch6) for the workflow that evaluates them, and [Chapter 10](#ch10) for what `sensitive` really protects.
