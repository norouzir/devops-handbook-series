# Appendix B - HCL Functions and Expression Cookbook {#appB}

## B.1 The Families at a Glance

| Family | Workhorses | Typical job |
|--------|-----------|-------------|
| String | `upper`, `lower`, `join`, `split`, `format`, `trimspace`, `regex`, `replace` | Naming, labels, parsing |
| Collection | `merge`, `flatten`, `zipmap`, `keys`, `values`, `length`, `contains`, `chunklist` | Building maps and lists for `for_each` |
| Encoding | `jsonencode`, `jsondecode`, `yamlencode`, `base64encode`, `urlencode` | Configs, policies, user-data |
| Conversion | `tostring`, `tonumber`, `tolist`, `toset`, `try`, `can` | Type discipline, optional values |
| Filesystem | `file`, `templatefile`, `fileexists`, `fileset` | Templated configs from disk |
| Date/Crypto | `timeadd`, `timecmp`, `timestamp`, `sha256`, `uuid` | Tags, cache keys, checksums |
| IP/CIDR | `cidrsubnet`, `cidrhost`, `cidrnetmask` | Network math |
| Provider funcs | `provider::aws::arn_parse`, ... (1.8+) | Domain logic a provider ships |

`timestamp()` and `uuid()` are the known plan-time troublemakers: their values differ per run, so they never belong in resources (they force perpetual diffs) - use them in provisioners, or the `time` provider's `time_static` resource for a stable value.

## B.2 Recipes From Real Estates

**Layered tag maps** - the `merge` that every estate eventually writes ([Chapter 5](#ch5)):

```hcl
tags = merge(
  local.common_tags,          # Project, Owner, Managed
  var.service_tags,           # per-service layer
  { Name = "${local.project}-${each.key}" }
)
```

**Nested structure to resource list** - the `flatten` that turns object trees into `for_each`-able lists ([Chapter 3](#ch3)):

```hcl
locals {
  ports = flatten([
    for svc, cfg in var.services : [
      for p in cfg.ports : {
        svc     = svc
        port    = p.port
        proto   = p.proto
      }
    ]
  ])
}

resource "docker_container" "svc" {
  for_each = { for p in local.ports : "${p.svc}-${p.port}" => p }
  # ...
}
```

**Optional values without `null` pain** - `try`/`can` for shape-flexible inputs:

```hcl
region = try(var.network_config.region, "eu-central-1")
has_lb = can(var.network_config.lb)
```

**Templated config from a file** - `templatefile` keeps logic out of strings ([Chapter 3](#ch3)):

```hcl
user_data = templatefile("${path.module}/init.tftpl", {
  region     = var.region
  cluster_ca = tls_self_signed_cert.ca.cert_pem
})
```

**CIDR math** - the subnet calculator you were about to open:

```hcl
subnets = { for i, az in var.azs :
  az => cidrsubnet(var.vpc_cidr, 3, i)      # 3 bits = 8 subnets
}
```

**Set math for security groups** - `setproduct`/`setsubtract` for allow-rules:

```hcl
allowed = setsubtract(keys(var.services), var.restricted)
```

## B.3 Template Directives, Condensed

Inside strings and templates: `${expr}` interpolates; `$${` escapes a literal; `%{ if cond }...%{ else }...%{ endif }` branches; `%{ for x in coll }...%{ endfor }` loops. The style rule from Chapter 3 holds: one directive is readable, two is a template module - move the logic into locals or `templatefile` and pass values in.

## B.4 Type Constraints in One Screen

```hcl
variable "examples" {
  type = object({
    name    = string
    port    = optional(number, 80)               # optional with default
    labels  = optional(map(string), {})
    enabled = optional(bool, true)
  })
  default = { name = "web" }
}
```

`list(string)` vs `set(string)`: lists keep order and duplicates, sets sort and dedupe - `for_each` requires the set/map discipline, so conversions (`toset`, `toset(keys(map))`) belong at the boundary. `any` and `list(any)` exist for genuinely polymorphic passthroughs; every other "I don't know the type" is a missing contract, not a type problem.
