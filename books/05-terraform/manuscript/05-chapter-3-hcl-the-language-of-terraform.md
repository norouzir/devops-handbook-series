# Chapter 3 - HCL: The Language of Terraform {#ch3}

## 3.1 Blocks, Arguments, and Identifiers

HCL (HashiCorp Configuration Language) is a purpose-built declarative language: JSON-adjacent in structure, but designed for humans writing infrastructure. Everything in a Terraform configuration is built from one syntactic idea - *blocks* containing *arguments* and nested blocks. A block starts with a type and optional labels, opens with `{`, holds arguments of the form `name = expression`, and closes with `}`:

```hcl
resource "docker_container" "web" {          # type: resource; labels: docker_container, web
  name  = "atlas-web"                        # argument: literal string
  image = "nginx:1.27-alpine"

  ports {                                    # nested block (repeatable)
    internal = 80
    external = var.external_port             # argument: expression
  }
}
```

Three families of blocks organize everything you will ever write: *configuration* blocks (`terraform`, `provider`, `variable`, `output`, `module`, `locals`, `moved`, `import`, `removed`, `check`), *resource* blocks (`resource`, `data`, `ephemeral`, `action`), and *meta* blocks nested inside resources (`lifecycle`, `provisioner`, `connection`, and provider-specific ones like `ports`). Labels matter more than they look: `docker_container.web` is the resource's *address*, the exact string you will use in `terraform state`, in `terraform plan -target`, and in cross-references everywhere else. Identifiers (block and argument names) accept letters, digits, underscores, and dashes; everything else is a string in quotes.

Comments are `#` or `//` for single lines and `/* */` for blocks; files are UTF-8 and conventionally formatted by `terraform fmt`, which enforces the community style (two-space indent, aligned `=`, normalized quotes) and ends most formatting arguments before they start. Run `terraform fmt -check` in CI from day one ([Chapter 12](#ch12) wires it in).

## 3.2 Types, Literals, and Strings That Compute

The value types cover the usual suspects: `string`, `number` (integers and floats are one type), `bool`, and the two collection families - `list`/`set`/`tuple` (ordered) and `map`/`object` (keyed). Literals look like most languages: `"nginx:alpine"`, `3`, `true`, `[80, 443]`, `{ name = "web", port = 80 }`. Heredocs handle multi-line strings, which you will mostly meet in templated configs:

```hcl
user_data = <<-EOF
  #!/bin/bash
  echo "hello from ${var.region}"
EOF
```

The `${...}` interpolation is HCL's most used feature and its most misunderstood: inside a string, `${}` evaluates an expression and splices the result in, and the surrounding *string becomes a template*. `$${` escapes a literal `${` (you need this constantly in shell scripts and kubeconfig templates), and `%{ if }/%{ for }` directives add conditionals and loops inside templates - though anything beyond trivial logic belongs in a `templatefile()` ([Appendix B](#appB)) rather than inline.

## 3.3 Expressions: References, Operators, and the Type Conversion Rules

An argument's value is an *expression*, and the simplest expressions are references: `var.name` (input variables), `local.name` (locals), `resource_type.label.attribute` (managed resources), `data.type.label.attribute` (data sources), `module.label.output`, and `each.key`/`count.index` inside iteration. Reference chains can traverse deeply: `docker_container.web.networks_advanced[0].name` or `aws_subnet.main[*].id`. The operators are the familiar arithmetic, comparison, and logical set (`+ - * / %`, `== != < >`, `&& || !`), with ternary as the only conditional: `condition ? a : b`.

The subtlety that trips everyone once: Terraform's implicit conversion rules. A `list` of one thing is not a `list` when it needs to be a scalar, `"80"` is happily a number where a number is required, and `set(string)` silently rejects a list with duplicates. When types get contentious, convert explicitly - `tolist()`, `toset()`, `tonumber()`, and the full conversion function family in [Appendix B](#appB) - because explicit conversions document intent and fail at the right place.

## 3.4 Iteration: `for` Expressions, `for_each`, `count`, and `dynamic`

HCL has no loops in the imperative sense; it has *expressions that transform collections*, and four meta-arguments that turn one block into many:

```hcl
locals {
  services = { web = 80, api = 8080, metrics = 9090 }

  # for expression over a map: transform values
  names = { k = upper(v) for k, v in local.services }

  # for expression over a list with a filter
  high = [for port in values(local.services) : port if port > 1000]
}

resource "docker_container" "svc" {
  for_each = local.services                # map -> one resource per key
  name     = "atlas-${each.key}"
  image    = "nginx:1.27-alpine"

  ports {
    internal = each.value
    external = each.value
  }
}
```

The rules of thumb, in order of preference: use `for_each` with a map or set whenever the instances have *identity* (adding `cache` to the map creates one resource, removing it destroys one - the others are untouched); reserve `count` for "N of an identical thing" where identity is positional (`count = 3` creates indexes 0-2, and inserting into the middle of the list *shifts* every subsequent resource, which is why `count` on named things causes accidental destruction); use `for` expressions to build the collections that feed them; and use `dynamic` blocks when a *nested* block itself must repeat:

```hcl
resource "docker_container" "web" {
  name  = "atlas-web"
  image = "nginx:1.27-alpine"

  dynamic "labels" {
    for_each = var.extra_labels            # map of label -> value
    content {
      label = labels.key
      value = labels.value
    }
  }
}
```

::: {.warn}
**Watch out - `count` on things with names**

`count` identifies instances by index. Renaming or reordering the driving list makes Terraform believe every shifted resource must be destroyed and recreated - a plan that starts with `-/+ aws_instance.api[1]` and ends with a retrospective. If instances have names, keys, or identities, they get `for_each`; if a `count` list ever changes shape, a `moved` block ([Chapter 14](#ch14)) must walk Terraform across the rename.
:::

## 3.5 Functions and the Splat Operator

Terraform ships a standard library of functions - string manipulation (`upper`, `join`, `split`, `format`, `regex`), collections (`merge`, `zipmap`, `flatten`, `chunklist`), encoding (`jsonencode`, `yamlencode`, `base64encode`), date and crypto (`timeadd`, `sha256`), filesystem (`file`, `templatefile`), and CIDR math (`cidrsubnet`, the workhorse of network code). Functions are pure - no I/O, no randomness (deliberately: randomness would break plan determinism; random values come from the `random` provider) - and they are evaluated at plan time wherever their inputs are known. [Appendix B](#appB) is the cookbook; the two you will use weekly are `merge` for layered maps and `flatten` for the nested-structure-into-resource-list move.

The splat operator `[*]` is the idiomatic shortcut for "extract an attribute from every element": `aws_subnet.main[*].id` is `for s in aws_subnet.main : s.id`. It handles nulls gracefully (returns an empty list rather than erroring), which makes it the default choice for fan-out references.

## 3.6 The Type System as Documentation

Every `variable` and `output` accepts a `type` constraint, and writing it is the cheapest documentation you will ever add: `type = string`, `type = number`, `type = bool`, or compound types like `list(object({ name = string, port = number }))`. Constraints do two jobs: they fail fast at plan time with a readable error instead of three layers deep in a provider, and they turn the variable declaration into the module's contract ([Chapter 8](#ch8) leans on this hard). `any` exists for genuinely polymorphic inputs, and `optional()` in object types defines keys with defaults - the difference between a module that tells you what it wants and one that shrugs.

**See also:** [Chapter 5](#ch5) for how variables, locals, and outputs fit the resource model, [Appendix B](#appB) for the function cookbook, and [Chapter 8](#ch8) for turning all of this into reusable modules.
