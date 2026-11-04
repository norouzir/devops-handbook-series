# Appendix C - Ecosystem and Troubleshooting Guide {#appC}

## C.1 The Tool Rack

| Tool | Slot in the ladder ([Chapter 11](#ch11)) | Note |
|------|------------------------------------------|------|
| `tenv` / `tfenv` | Environment | Version managers; `tenv` also covers OpenTofu and Terragrunt |
| tflint | Static analysis | Plugin-aware linting; per-provider rules |
| trivy / Checkov | Static analysis (security) | Plan or config scanning; policy baseline |
| infracost | Static analysis (cost) | PR comments with the plan's cost delta |
| `terraform test` + `mock_provider` | Unit-ish tests | Native framework (1.6+/1.7+) |
| OPA (Rego) | Policy | Platform-neutral plan gating |
| Terraform Policy | Policy | CLI-native, GA in 1.17 |
| Atlantis / Terrateam | Automation | PR-driven plan/apply for self-hosted teams |
| Terragrunt | Layout | DRY wrappers over many roots (opinionated; adopt deliberately) |
| HCP Terraform / TFE | Platform | Workspaces, run queue, approvals, Stacks ([Chapter 13](#ch13)) |

The rack is a menu, not a syllabus: `tenv`, tflint, one scanner, and one policy engine cover most estates' first year.

## C.2 Troubleshooting by Symptom

**"Error: Invalid index" / "This object does not have an attribute"** - a reference to an attribute or instance that does not exist: a `count` resource indexed beyond its instances, a data source returning empty, or an attribute name from a different provider version ([Chapter 4](#ch4)). Check the actual shape with `terraform state show` and fix the index, the query, or the version.

**"Error: Argument or block definition required" / parse errors** - HCL syntax: a block left open, `=` in a nested block (nested blocks take no `=`), or a `${` in a heredoc that meant to be literal (`$${`). `terraform fmt` will not fix logic, but it localizes the parse error to a line.

**"Error: Duplicate resource configuration" / address conflicts** - two blocks claiming one address, or a `for_each` key colliding with an existing `count` instance. Usually the `moved` block ([Chapter 14](#ch14)) is missing from a refactor.

**Plan proposes destroy + create you did not intend** - an immutable attribute changed (provider schema's ForceNew), or a `count` list reordered ([Chapter 3](#ch3)). If recreation is unsafe, reshape with `create_before_destroy` ([Chapter 14](#ch14)) or re-key with `for_each` plus `moved` blocks.

**"Error: Locked state" / lock timeout** - a run crashed holding the lock, or two pipelines raced. Confirm nothing is executing (backend console, CI logs), then `terraform force-unlock <lock-id>`. If it recurs, your concurrency guardrails ([Chapter 12](#ch12)) are not guarding.

**"Objects have changed outside of Terraform"** - drift ([Chapter 14](#ch14)). Decide: `apply -refresh-only` to accept, plan/apply to restore, or `ignore_changes` to delegate ownership - and record which.

**State and reality disagree after a failed apply** - normal: partial progress is persisted. Re-plan and re-apply; the new plan diffs against what actually happened. Only reach for `state` surgery ([Chapter 7](#ch7)) when a specific object's identity is wrong.

**"Provider produced inconsistent result after apply"** - the API returned something different from what the provider planned (flaky defaults, eventual consistency). Re-run plan; if it persists, pin or upgrade the provider and check its issue tracker.

**Secrets visible in plan output** - variables/outputs missing `sensitive = true` ([Chapter 10](#ch10)); and if the value predates the flag, it is in state regardless - rotate, then migrate to ephemeral/write-only patterns.

**`init` downloads the wrong provider version** - the lock file was deleted or hand-edited. Restore it from git; never edit it by hand. `-upgrade` is the only sanctioned movement.

## C.3 The Estate Health Checklist

The habits whose absence generates most of Section C.2, as a review checklist: version file committed; lock file committed; state remote, locked, versioned, encrypted; no laptops apply to shared roots; every root has a drift job; modules have validation and descriptions on every variable; `prevent_destroy` on databases and clusters; policy gates destruction on prod; plans are read as graph decisions, not line edits; and the team can name, from memory, what its state partition means - because an estate nobody can explain is an incident nobody can debug.
