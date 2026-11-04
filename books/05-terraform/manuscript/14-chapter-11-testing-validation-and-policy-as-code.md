# Chapter 11 - Testing, Validation, and Policy as Code {#ch11}

## 11.1 The Ladder: Fail Fast, Fail Cheap, Fail on Purpose

Infrastructure testing is not software testing transplanted; it is a *ladder of increasing cost*, and the craft is pushing every failure as early up the ladder as it will go. From cheapest to most expensive: static formatting and syntax (`fmt`, `validate`), type and value validation (variable `validation` blocks, preconditions), static analysis (tflint, security scanners), *unit-ish* testing of module logic (`terraform test` with mocks), plan-time policy (Terraform Policy, OPA, Sentinel), and finally the integration truth of staging applies ([Chapter 9](#ch9)). A team that only has the last rung tests in production; every rung added below buys a cheaper failure.

```console
$ terraform fmt -check -recursive     # style - the PR gate that costs nothing
$ terraform validate                  # syntax + schema against the provider
$ terraform test                      # the test framework (1.6+)
```

## 11.2 `terraform test`: Assertions Over Plans and Applies

The native test framework (Terraform 1.6+, 2023) executes `.tftest.hcl` files: each `run` block either plans or applies a configuration (typically a module call) and asserts against the result with `assert` expressions - the same expression language as [Chapter 3](#ch3), pointed at outputs and resource attributes:

```hcl
# tests/web_service.tftest.hcl
run "defaults" {
  command = plan

  assert {
    condition     = length(module.web.containers) == 1
    error_message = "default replicas should produce one container"
  }
}

run "scaled" {
  command = plan

  variables {
    replicas = 3
  }

  assert {
    condition     = length(module.web.containers) == 3
    error_message = "replicas input must map to container count"
  }
}
```

`command = plan` runs the cheap rung - the module's logic evaluated without creating anything - and covers the majority of module tests: naming, port math, `for_each` fan-out, conditional features. `command = apply` runs the expensive rung - real resources against a real (disposable) provider target, with the framework managing setup and teardown across `run` blocks - and earns its cost for provider-behavior questions that plans cannot answer. Since Terraform 1.7, `mock_provider` replaces a provider with scripted responses, letting tests assert on *your module's logic* with no provider API in the loop; 1.17-era releases extended mocks to ephemeral resources. The pattern this book recommends: mock-based `plan` tests for module logic in CI on every PR, `apply`-based tests in a scheduled pipeline against the Docker provider (or a cloud sandbox) for the modules that matter most.

## 11.3 Static Analysis and Security Scanning

Two families of linters earn their CI slot. *tflint* goes beyond `validate` with plugin-aware rules: unused declarations, invalid instance types, deprecated syntax - catching per-provider mistakes the core schema cannot see. *Security scanners* - trivy (successor lineage of tfsec), Checkov, Terrascan - parse the plan or configuration for insecure patterns: public buckets, open security groups, missing encryption, IMDSv1. Both run in seconds, both are pre-plan, and both generate their share of noise - which is handled the same way everywhere: a baseline, explicit suppressions with reasons in code, and new findings block. Infracost belongs to the same rung though it checks money, not safety - a PR comment showing the plan's cost delta changes more architecture decisions than any scanner.

## 11.4 Guardrails in Configuration: `check`, Precondition, Postcondition

Between "tests that run in CI" and "policy that gates apply" sit assertions that live *in the configuration* and fire during planning for everyone, forever. `check` blocks assert on data sources and computed values without failing the plan (they warn); `lifecycle.precondition` and `postcondition` blocks gate resources on expressions; and variable `validation` ([Chapter 5](#ch5)) gates inputs. Together they encode the module author's assumptions where the caller cannot miss them:

```hcl
resource "aws_instance" "api" {
  # ...

  lifecycle {
    precondition {
      condition     = var.subnet_cidr <= 26
      error_message = "api subnets must be /26 or smaller to hold 60 hosts."
    }
  }
}
```

The distinction that keeps these maintainable: preconditions express the *module's* requirements (things that must be true for the resource to be correct), while policy engines ([Section 11.5](#ch11)) express the *organization's* requirements (things that must be true for any change to be allowed). An assumption that migrates from a code review comment into a precondition stops being re-litigated.

## 11.5 Policy as Code: Terraform Policy, OPA, Sentinel

Policy engines answer a different question than tests: not "is this module correct?" but "is this *change* allowed?". They evaluate the JSON plan output (`terraform show -json tfplan`, [Chapter 6](#ch6)) against rules, before apply - which means they see exactly what will happen, attribute by attribute, including replacements.

As of Terraform 1.17 (October 2026), **Terraform Policy is generally available**: policies evaluate `plan`, `apply`, and `query` runs via the `-policies` flag, locally or in CI, with human-readable or JSON results - HashiCorp's built-in answer to "gate this plan" without any additional platform. In HCP Terraform and Terraform Enterprise, **Sentinel** (commercial) embeds policy in the run pipeline with enforcement modes (advisory, soft-mandatory, hard-mandatory) and scope by workspace. The open ecosystem standard is **Open Policy Agent (OPA)**: Rego policies over the plan JSON, wired into any pipeline (and Atlantis/Terrateam, [Chapter 12](#ch12)) as a plan/apply gate. The choice is less about capability than venue: Terraform Policy for CLI-native gating, OPA for platform-neutral estates, Sentinel where HCP Terraform's enforcement modes are the product.

```console
$ terraform plan -out=tfplan && terraform show -json tfplan > tfplan.json
$ terraform apply tfplan -policies ./policy/   # Terraform Policy (GA, 1.17)
```

::: {.note}
**Best practice - policy blocks destruction, tests block surprises**

The workable split: policy engines enforce the invariants that must never break (no public S3, no unencrypted RDS, no prod apply outside the pipeline) because they are few, absolute, and expensive to violate. Tests cover the logic that changes weekly (naming, counts, wiring) because they are many and contextual. Teams that point policy at logic drown in rule churn; teams that point tests at invariants re-test the same thing three tools deep.
:::

## 11.6 The Pipeline Layout

The rungs assemble into the CI layout [Chapter 12](#ch12) wires end to end: `fmt` + `validate` + tflint + scanner + module tests on every PR; policy evaluation on the PR's speculative plan ([Chapter 6](#ch6)) with results posted as review comments; the same gates re-run at apply time in the pipeline, where they are binding rather than advisory. The re-run matters: a plan reviewed on Tuesday and applied Thursday is a different diff if the base moved - the pipeline that re-computes and re-gates is what keeps "reviewed" and "applied" the same object.

**See also:** [Chapter 12](#ch12) for the pipeline that runs this ladder, [Chapter 8](#ch8) for the modules these tests target, and [Appendix C](#appC) for the tool catalog.
