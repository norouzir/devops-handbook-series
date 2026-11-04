# Chapter 1 - Infrastructure as Code and Terraform: The Landscape {#ch1}

## 1.1 The Problem Infrastructure as Code Solves

Every sufficiently old environment contains an outage waiting to be described. A security group opened in the console during a 2 a.m. incident, a database sized up by hand during a launch and never resized back, a subnet that exists only in one region's muscle memory - none of it is written down, none of it is reviewable, and none of it survives the engineer who made it. Infrastructure as Code (IaC) is the discipline of describing infrastructure declaratively in files that live in version control, so that the environment's source of truth is a `git diff` rather than an archaeology project. The payoff is not merely documentation; it is *reproducibility* (the same code plus the same inputs produces the same infrastructure, every time), *reviewability* (changes are proposed, diffed, and approved before they touch production), *auditability* (the history of every change is a commit log), and *speed* (a new environment is an apply away, not a procurement quarter away).

The word *declarative* is doing real work in that sentence, and it is worth pinning down. A declarative tool takes a description of the desired end state - "there is a VPC with these three subnets, and a cluster with these five nodes" - and computes the difference between that description and reality, then produces and executes the sequence of API calls needed to converge the two. You describe *what*, the tool figures out *how* and *in what order*. This is the same philosophy Kubernetes applies to workloads, and it is why the two pair so naturally: the declarative boundary simply moves outward, from "everything inside the cluster" to "the cluster and everything around it". Scripted alternatives - the `bash bootstrap.sh` school, or clouds' sequence-of-API-calls SDKs - invert the contract: they encode *how*, which means every run re-does work, reruns fail halfway through, and nothing detects that the world has drifted from the plan.

Terraform's specific contribution to this model is the *plan*. Where earlier declarative tools showed you their work only after doing it, Terraform separates intention from execution: `terraform plan` computes the entire proposed change set - creates, updates, replacements, destroys - renders it in human-readable form with attribute-level diffs, and *only then* does `terraform apply` execute it. This two-step rhythm is the single most important habit this book teaches, and it recurs everywhere from [Chapter 6](#ch6) (the workflow itself) to [Chapter 12](#ch12) (where the plan becomes the pull-request artifact that reviewers actually read). The plan is also why Terraform scales socially: a change that would take twenty minutes of console clicking becomes a diff that a teammate can approve in thirty seconds, with the reasoning in the commit message.

## 1.2 Terraform in One Paragraph

Terraform, created by Mitchell Hashimoto and Armon Dadgar at HashiCorp and first released in 2014, is an open-source-engine CLI written in Go that reads configuration written in HCL (HashiCorp Configuration Language), talks to providers - plugins that translate generic resource blocks into concrete API calls for AWS, Azure, Google Cloud, Kubernetes, GitHub, Cloudflare, Datadog, and roughly four thousand other platforms - and keeps a *state file* recording the resources it manages so that the next plan can diff against reality. The configuration is cloud-agnostic in shape: the same authoring skills, module patterns, and workflow apply whether you are provisioning an EC2 fleet or a PagerDuty rotation. The state file is the price and the power of the model, and it gets its own chapter ([Chapter 7](#ch7)) because most production incidents with Terraform are, at root, state incidents.

## 1.3 The License Split: Terraform and OpenTofu

In August 2023, HashiCorp relicensed Terraform from MPL-2.0 to the Business Source License (BUSL 1.1), which restricts offering Terraform as a competing commercial service and converts to MPL-2.0 after each release's four-year change date. The community's response was OpenTofu, a fork announced within days, accepted into the Linux Foundation, and now a CNCF-hosted project with its own release cadence and registry. As of October 2026, HashiCorp's Terraform is at 1.17.0 (October 21, 2026) and OpenTofu is at 1.13 (September 2026, supported through August 2027); both track the same HCL language core, and the overwhelming majority of configurations and modules run on both without modification.

The practical guidance for a working engineer is unsentimental. The language you write - and therefore everything in Part I of this book - is shared property. What differs is the *distribution*: OpenTofu adds community features on its own schedule (dynamic `prevent_destroy` and the `destroy = false` lifecycle option in 1.12, the `enabled` meta-argument and ephemeral values in 1.11), while Terraform ships HashiCorp's schedule and the only officially supported path to HCP Terraform, Stacks, and Terraform Enterprise ([Chapter 13](#ch13)). Some organizations standardize on OpenTofu for licensing or governance reasons; many run Terraform CLI against HashiCorp products and keep OpenTofu compatibility as a hedge, enforced by CI running both. This book teaches on Terraform and marks OpenTofu differences where they matter; nothing here requires you to pick a side before [Chapter 14](#ch14), where coexistence strategies are discussed properly.

## 1.4 How Terraform Compares

No tool wins every category, and knowing the neighbors makes you a better Terraform engineer. The honest comparison as of 2026:

| Tool | Model | Cloud scope | Sweet spot |
|------|-------|-------------|------------|
| Terraform / OpenTofu | Declarative HCL, plan/apply, state file | Any platform with a provider | Multi-cloud, platform provisioning, the industry default |
| CloudFormation | Declarative YAML/JSON, AWS-native | AWS only | All-in AWS shops deep in the AWS ecosystem |
| Pulumi | Declarative engine, general-purpose languages (TypeScript, Python, Go) | Any platform with a provider | Teams that want real languages, loops, and unit tests over IaC |
| Ansible | Procedural-leaning YAML modules, agentless | Any (SSH + APIs) | Configuration management and orchestration on existing hosts |
| Cloud-specific CDKs (CDKTF, AWS CDK) | Languages compiling to the above | Follows the base tool | Application teams embedding IaC in existing build tooling |

The boundary that matters most in this series is the one between Terraform and Ansible, because teams genuinely use both. The division of labor this series recommends: Terraform *provisions* - it creates and reshapes the long-lived objects (networks, clusters, databases, DNS, IAM), where ordering and replacement semantics matter and state must be tracked. Ansible *configures and operates* - it runs on machines that already exist, installing packages, templating configs, rolling deployments (*Ansible for DevOps Engineers*, Chapters 5-7). Pointing Terraform at a fleet to run `apt` inside guests, or asking Ansible to create a VPC topology with dependencies, are both possible and both usually wrong. The two tools meet at the boundary objects: Terraform creates the instance and outputs its address, Ansible picks the address up from inventory and takes it from there.

::: {.note}
**Best practice - learn the plan, not the provider**

Beginners optimize for "which cloud should I learn Terraform with?" and the question is nearly empty. The transferable skill is the workflow - plan discipline, state hygiene, module design - and it transfers across providers wholesale. Learn on the cheapest disposable target available (this book uses Docker), then apply the same muscles wherever your employer's workloads live.
:::

## 1.5 What This Book Assumes and Does Not

It assumes you are comfortable on the command line, have used `git` well enough to open a pull request, and have met at least one cloud or platform at the level of "I can log into a console and start a VM". It does not assume prior IaC experience, prior HCL, or deep networking - the concepts are introduced when they are needed. It does not attempt to be a provider reference: the AWS provider alone documents more resources than this book has pages, and the Registry ([Chapter 4](#ch4)) is the real reference, always current. What the book does attempt is the judgment layer - knowing why a plan shows a replacement, when a module boundary is wrong, what to do when state and reality disagree - because that judgment is what separates someone who can run Terraform from someone who can run Terraform in production.

**See also:** [Chapter 2](#ch2) to get a working install and your first apply, [Chapter 6](#ch6) for the workflow in depth, and [Chapter 14](#ch14) for how all of it behaves under production load.
