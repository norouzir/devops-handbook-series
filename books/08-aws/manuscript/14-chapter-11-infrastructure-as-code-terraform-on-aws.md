# Chapter 11 - Infrastructure as Code: Terraform on AWS {#ch11}

## 11.1 What This Chapter Adds to the Terraform Book

The series' *Terraform for DevOps Engineers* volume teaches the language: resources, modules, state, workspaces, plan discipline. This chapter assumes all of that and teaches only what is specifically **AWS** about the practice - the provider setup, the remote-state home, the way a real account is shaped into modules, the AMI and account data sources, and the CI integration that closes the loop with [Chapter 9](#ch9). The running example's platform - VPC from [Chapter 4](#ch4), EKS from [Chapter 7](#ch7), RDS from [Chapter 6](#ch6) - is the material, and the chapter's claim is simple: by the end, every manual command from Part I has a reviewed, versioned, reproducible equivalent.

## 11.2 Provider, Versions, and the Remote State Home

The provider block pins both the Terraform and provider versions - pinning is what makes a plan six months from now identical to today's:

```hcl
terraform {
  required_version = "~> 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
  backend "s3" {
    bucket       = "shopnow-tfstate-eu-central-1-prod"
    key          = "platform/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = "eu-central-1"
  default_tags { tags = { project = "shopnow", managed_by = "terraform" } }
}
```

The **S3 backend** is the standard state home: the bucket is exactly the [Chapter 5](#ch5) bucket built properly - versioned, encrypted, public-blocked - because state contains credentials' neighbors (resource attributes, sometimes secrets) and losing it means losing the map of the platform. Locking is what prevents two engineers (or one engineer and one pipeline) from planning against each other: modern Terraform supports **S3-native locking** via `use_lockfile` (a lock object in the bucket); the classic arrangement was a companion DynamoDB lock table, and either works - the requirement is that *there is one*, enforced before any apply. `default_tags` stamps every resource the configuration creates, which is what makes [Chapter 12](#ch12)'s cost reporting and the cleanup scripts work by construction rather than by memory.

::: {.warn}
**Watch out - state is the platform's source of truth, treat it like one**

Two habits prevent the classic state disasters. *Never edit state by hand* - `terraform state list`, `state mv`, and `import` exist for the surgical cases, and a hand-edited state file is an unrecoverable one. And *one state per blast radius*: a monolithic state across dev, staging, and prod means a typo in a directory affects everything; the layout in Section 11.5 exists to keep a mistake's radius equal to its environment.
:::

## 11.3 The Reference VPC as a Module

Part I's manual VPC build ([Chapter 4](#ch4), Lab 2) compresses into a module whose variables are the design decisions:

```hcl
module "network" {
  source = "./modules/network"

  name          = "shopnow"
  cidr          = "10.0.0.0/16"
  azs           = ["eu-central-1a", "eu-central-1b"]
  public_cidrs  = ["10.0.0.0/20", "10.0.16.0/20"]
  private_cidrs = ["10.0.32.0/20", "10.0.48.0/20"]
  single_nat    = false   # one NAT per AZ in prod, true in dev
}

module "eks" {
  source = "./modules/eks"

  cluster_name    = "shopnow"
  subnet_ids      = module.network.private_subnet_ids
  node_type       = "t4g.medium"
  min_size        = 2
  max_size        = 4
}

module "db" {
  source = "./modules/rds"

  identifier     = "shopnow-db"
  subnet_ids     = module.network.private_subnet_ids
  app_sg_id      = module.eks.node_security_group_id
  multi_az       = true
}
```

Read the composition, not the syntax: outputs of one module feed inputs of the next - `private_subnet_ids` from the network land in both the cluster and the database, and the database's SG admits traffic *from the cluster's node SG* (Section 4.4's SG-referencing, now in code). The module boundaries are the platform's real architecture: `network` changes when the topology changes, `eks` when the cluster shape changes, `rds` when the database changes - and each has its own state (Section 11.5's layout), its own plan output, and its own review radius. Appendix B ships a starter skeleton in exactly this shape.

## 11.4 Data Sources: AMIs, AZs, and the Account as Input

Data sources read what already exists, and three AWS ones appear in nearly every configuration. The **AMI data source** replaces the hard-coded image ID from [Chapter 3](#ch3) - the same SSM-public-alias trick in Terraform form, or a filter query:

```hcl
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}
```

The **availability zone data source** (`data "aws_availability_zones"`) stops you from hard-coding AZ letters that not every account sees the same way, and **caller identity** (`data "aws_caller_identity"`) feeds account IDs into ARNs - the difference between a configuration that runs on your laptop and one that runs in any account it is pointed at. The general rule: *resources are what Terraform owns, data sources are what it observes* - and a configuration that observes more than it invents is one that plays well with a platform that already exists.

## 11.5 Environments: Workspaces vs Directory-per-Environment

Two layout schools, and the choice is worth making consciously. **Workspaces** keep one configuration with state files switched by name (`terraform workspace select prod`) - lean, but identical code across environments with differences expressed in variables, which grows awkward when environments *should* differ structurally (dev with `single_nat = true`, prod without). **Directory-per-environment** (`environments/dev`, `environments/prod`, each its own root module and state) duplicates a little code to buy structural independence - environments can drift deliberately, be destroyed independently, and be planned in isolation. The series' recommendation for AWS platforms: directory-per-environment for anything beyond a one-person project, with shared logic in `modules/` so the duplication is shallow. A typical tree:

```text
.
├── modules/          # network, eks, rds, observability
├── environments/
│   ├── dev/          # small: single NAT, no Multi-AZ
│   └── prod/         # full layout from Part I
└── global/           # IAM, OIDC provider, ECR - shared, rarely changed
```

## 11.6 Plans, Drift, and Imports in a Living Account

Real accounts are never greenfield, and three disciplines keep Terraform honest inside one. **Plan review** is the actual change-control: the plan output in the pull request is the review artifact ([Chapter 9](#ch9)'s pipeline posts it), and the reader's job is to catch the destructive `-/+` (replace) markers before apply does. **Drift** - changes made outside Terraform (a console fix at 2 a.m., the classic) - is surfaced by `terraform plan` showing diffs nobody wrote; the healthy loop is reconcile-by-import (`terraform import` adopts the manual change into code) or revert-by-apply, decided deliberately rather than discovered in the next apply. **Import blocks** (native since Terraform 1.5) make adoption a code review too:

```hcl
import {
  to = aws_instance.legacy_web
  id = "i-0123456789abcdef0"
}
```

The account that results is one where the console becomes read-only by convention - looking, not touching - and the CLI from [Chapter 1](#ch1) becomes read-mostly: everything that *changes* the platform flows through a plan someone reviewed.

## 11.7 Terraform in CI: The OIDC Role Closes the Loop

The [Chapter 9](#ch9) trust setup applies to Terraform with one role and two jobs. A plan job on pull requests (`terraform fmt -check`, `terraform validate`, `terraform plan -out=plan.tfplan`, posted as a comment) gives every infrastructure change a review surface, and an apply job on main (after approval, with `environment: production`) runs the reviewed plan. The role's permissions policy is scoped to the resources the configuration manages - and the OIDC `sub` condition can pin to the workflow file itself, so only `infra-plan.yml` can plan and only `infra-apply.yml` can apply. The end state is the whole book in one sentence: *the account is what the repository says it is, the pipeline is the only hand that changes it, and CloudWatch from [Chapter 10](#ch10) watches both do their jobs.*

**See also:** [Chapter 12](#ch12) adds the budgets and tagging enforcement that make the cost story automatic, and the *Terraform for DevOps Engineers* volume owns the language mechanics (expressions, `for_each`, testing) this chapter deliberately did not re-teach.
