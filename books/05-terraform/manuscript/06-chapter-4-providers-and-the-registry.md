# Chapter 4 - Providers and the Registry {#ch4}

## 4.1 What a Provider Is

Terraform's core knows *nothing* about AWS, Docker, or Kubernetes. All platform knowledge lives in *providers* - standalone plugins that expose resource types, data sources, and (since Terraform 1.8) functions, and that translate the generic plan/apply protocol into concrete API calls. When your configuration says `resource "docker_container" "web"`, the core resolves `docker_container` against the provider whose prefix it carries (`kreuzwerker/docker`), asks that provider what the type's schema is, validates your arguments against it, and during apply hands the provider the diff to execute against the Docker API. This two-layer design is why Terraform speaks four thousand platforms with one workflow - and why `terraform init` exists: before anything else happens, the core must *install the plugins your configuration needs*.

Every provider declares itself in the `terraform` block's `required_providers` map, keyed by *local name* and pinned by *source address* plus *version constraint*:

```hcl
terraform {
  required_version = ">= 1.10"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"   # [<hostname>/]<namespace>/<type>
      version = "~> 3.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

The source address has an optional hostname (default: `registry.terraform.io`, the public Terraform Registry), a namespace, and a type; the local name on the left is what your resource prefixes must match (`docker_container`, not `kreuzwerker_docker_container`). The Registry itself is the discovery surface: it documents every resource and data source with its schema and examples, publishes provider releases with checksums, and is where the lock file's verification data comes from. Treat `registry.terraform.io` search as part of your IDE; the book does not enumerate resources for exactly the reason Chapter 1 gave.

## 4.2 Version Constraints and the Lock File

Provider version constraints use the same grammar as `required_version`: `>= 1.0`, `~> 3.0` (3.x, the pessimistic operator - the daily driver), `~> 3.1` (3.1 <= v < 4.0), exact pins, and `!=` exclusions. The constraint is an upper bound *contract with the future*: it says "this configuration is believed to work up to, but not including, this major version", which is exactly the amount of trust appropriate for plugins that can change resource schemas.

The constraint does not select the version alone, though - the **dependency lock file** (`.terraform.lock.hcl`, created by `init`, committed) records the *exact* version chosen and the checksums of every platform build. On the next `init`, Terraform installs the locked version even if a newer one matches the constraint, which is what makes builds reproducible. The upgrade is therefore a deliberate act: `terraform init -upgrade` re-resolves to the newest version satisfying the constraint and rewrites the lock file, producing a reviewable diff. Since 1.10-era releases, providers also publish *signing keys and checksum verification* as part of `init`, so a compromised mirror fails loudly - one more reason never to bypass the lock file.

::: {.note}
**Best practice - upgrade providers like dependencies, not like weather**

A provider upgrade is a code change: constrain, upgrade with `init -upgrade`, read the provider changelog for deprecations, run `plan` and *read the diff*, commit the lock file in its own PR. Teams that batch "bump everything" once a quarter discover breaking changes in production; teams that upgrade small and often read one changelog at a time.
:::

## 4.3 Multiple Provider Instances: Aliases and `provider` Blocks

`required_providers` declares *which* plugins; `provider` blocks *configure* them - credentials, regions, endpoints. The default configuration (no label) serves most uses, but real estates constantly need the same platform in two flavors: two regions, two accounts, one production and one staging. The `alias` meta-argument creates a second instance, and resources select it with the `provider` meta-argument:

```hcl
provider "aws" {
  region = "eu-central-1"
}

provider "aws" {
  alias  = "us"
  region = "us-east-1"
}

resource "aws_instance" "eu" {
  # uses the default provider implicitly
  ami           = data.aws_ami.debian.id
  instance_type = "t3.micro"
}

resource "aws_instance" "us" {
  provider      = aws.us                 # explicit alias
  ami           = data.aws_ami.debian.id
  instance_type = "t3.micro"
}
```

Since Terraform 1.17, `provider` blocks can be *parameterized* - `variables` and `locals` are now allowed in provider requirements and configuration, which closes the long-standing gap where regions or endpoints had to be hardcoded or duplicated. The companion meta-argument `configuration_aliases` inside `required_providers` is what lets a *module* accept provider configurations from its caller rather than configuring them itself - the correct pattern for reusable modules ([Chapter 8](#ch8)), because a module that hardcodes credentials is a module that only works in one estate.

## 4.4 Authentication: How Providers Get Credentials

Each provider documents its own credential chain, and they rhyme: environment variables (`AWS_ACCESS_KEY_ID`, `ARM_CLIENT_SECRET`), shared config files (`~/.aws/credentials`, `~/.azure/config`), and where possible *federation*. The 2026 best practice is unambiguous: **no long-lived static keys**. Clouds support OIDC-based role assumption - GitHub Actions or any OIDC-capable CI exchanges a short-lived token for cloud credentials with no secret stored anywhere - and HashiCorp's HCP Terraform handles dynamic credentials natively ([Chapter 13](#ch13)). The Docker provider, refreshingly, needs nothing beyond access to the daemon socket. Whatever the provider, credentials belong to the *environment that runs Terraform*, never to the configuration: a `provider` block containing a literal key is a finding, not a shortcut.

## 4.5 Beyond the Registry: Mirrors, Filesystem Sources, and Provider Functions

Enterprise networks frequently cannot reach the public Registry. The `filesystem_mirror` and `net_mirror` sources in the CLI config (`~/.terraformrc`) redirect provider downloads to an internal mirror or a vendored directory, with `include`/`exclude` patterns controlling what goes where - the standard pattern in air-gapped and compliance-bound estates. Provider *functions* (Terraform 1.8+) extend the same idea to logic: a provider can ship functions callable as `provider::namespace::type::name(...)`, such as AWS's ARN-parsing family - worth knowing when the core function library ([Appendix B](#appB)) lacks a domain-specific helper.

::: {.warn}
**Watch out - two providers where you wanted one**

Mixing provider *versions* across modules that share resources is a frequent source of "attribute not found" errors: the plan runs under one provider build while another module's docs promise a schema from a newer one. Keep one provider version per configuration (the lock file enforces this), constrain modules with compatible ranges, and let CI's `init -upgrade` PR surface version bumps as reviewable changes.
:::

**See also:** [Chapter 2](#ch2) for what `init` does end to end, [Chapter 8](#ch8) for modules that consume providers correctly, and [Chapter 13](#ch13) for credential handling in HCP Terraform.
