# Chapter 6 - The Core Workflow: Init, Plan, Apply {#ch6}

## 6.1 The Three Commands, Properly Understood

`terraform init`, `plan`, and `apply` looked like a simple chant in [Chapter 2](#ch2); they deserve their real definitions before you lean on them. `init` *prepares the working directory*: it reads `versions.tf`, resolves and downloads the required providers (honoring the lock file), fetches referenced modules, and configures the backend - state storage. It is safe to re-run at any time and is idempotent; it is also the only command that changes provider or module versions, which is why upgrades happen through `init -upgrade` and nowhere else. `plan` *proposes*: it refreshes state against reality, evaluates the configuration, builds the dependency graph, computes the difference, and renders it. `apply` *executes* the proposed change set: with a confirmation prompt by default, writing every resulting attribute back into state.

The rhythm to internalize - and the one the labs enforce - is that **the plan is the artifact you review, and the apply is its execution**. A plan you did not read is infrastructure change you did not approve; an apply that surprises you is a plan you skimmed.

## 6.2 Plan Modes and Flags That Matter

The plan command's option surface is small and every option is load-bearing. `-out=tfplan` writes the plan to a file: the plan becomes an artifact that `terraform apply tfplan` executes *exactly as computed*, closing the gap between "what was reviewed" and "what ran" - the pattern CI pipelines use ([Chapter 12](#ch12)). `-refresh=false` skips the state-refresh phase for speed when you know nothing external changed. `refresh-only` (a mode, not a flag: `terraform apply -refresh-only`) updates state to match reality *without proposing changes* - the honest answer to "someone changed it in the console, make Terraform accept it". `-target=resource.address` restricts the plan to a resource and its dependencies; `-replace=resource.address` forces destruction and recreation of one object (the civilized successor to `taint`). And since Terraform 1.17, `-minimal-refresh` restricts the refresh pass to resources whose plan proposes changes - a genuine speedup on estates of thousands of resources.

```console
$ terraform plan -out=tfplan
$ terraform show -json tfplan > tfplan.json     # machine-readable for policy/tests
$ terraform apply tfplan                        # executes exactly the reviewed plan
```

::: {.warn}
**Watch out - plans expire**

A saved plan file is a snapshot of reality at planning time. Apply it soon (minutes to hours, not days), and never on a different workspace or environment: `apply tfplan` does not re-check that the target matches the source, it executes the recorded changes against whatever state it finds. The plan file also contains the full proposed configuration - treat it as sensitive ([Chapter 10](#ch10)).
:::

## 6.3 Reading a Plan Like an Operator

Plans render as four prefix-marked change classes - `+` create, `-` destroy, `~` update in place, `-/+` destroy and recreate (also written `#` with `forced replacement` when immutable attributes changed) - and end with a summary line (`Plan: 2 to add, 1 to change, 0 to destroy`). The reading order that catches incidents: *destroy* lines first (did I intend any?), then `-/+` replacements (what breaks when this object is rebuilt?), then `~` updates (which attributes change, and which of them are things like image, machine type, or security group?), then creates. The `Note: objects have changed outside of Terraform` block at the top of a plan is not decoration: it lists drift detected during refresh, and ignoring it is how console changes get silently reverted by the next apply ([Chapter 14](#ch14) turns drift into a monitored workflow).

Plan readability is also a *configuration* quality: consistent locals for names ([Chapter 5](#ch5)), stable `for_each` keys ([Chapter 3](#ch3)), and small modules keep diffs reviewable. A plan that scrolls past thirty screens is a plan nobody reads, and that is a configuration bug before it is a process bug.

## 6.4 Apply Discipline and Destroy

`terraform apply` without arguments recomputes the plan interactively - fine for local labs, wrong for shared environments where the reviewed plan and the executed plan must be the same object. The production grammar is `plan -out` then `apply <file>` (or an HCP Terraform remote run, [Chapter 13](#ch13), where the platform enforces exactly this). `apply -auto-approve` skips confirmation; reserve it for pipelines that already gate the change elsewhere and for disposable lab resources. Terraform retries transient API errors, aborts on unrecoverable ones, and persists partial progress to state - which is why the recovery chapter ([Chapter 7](#ch7)) exists and why "just re-run apply" is usually the right first response to a failed apply: the plan re-diffs against what *actually* happened, not what should have.

`destroy` is `apply` with an inverted plan: same review discipline, same `-target`/`-var` surface, same state consequences. Destroying by workspace or directory is the standard environment teardown ([Chapter 9](#ch9)); destroying a *subset* belongs to `-target` or, better, to removing the resource from configuration and using a `removed` block ([Chapter 7](#ch7)). `prevent_destroy` lifecycles ([Chapter 5](#ch5)) are the tripwire that keeps the deepest layers of the estate out of reach of a mistyped command.

## 6.5 The Workflow in Team Context

Solo, the loop is plan-apply locally. On a team, the same loop moves into version control: every change is a branch and pull request, CI runs `fmt`, `validate`, and a *speculative* plan (a plan without saving or applying - HCP Terraform, Atlantis, and the GitHub Actions pattern in [Chapter 12](#ch12) all do this) whose output is posted as a PR comment, and merge triggers apply against a shared backend. The tools differ; the invariants do not: **one place where state lives, every change reviewed as a plan, no applies from laptops against shared infrastructure**. Chapters 7 and 12 build that pipeline; this chapter built the vocabulary it automates.

## 6.6 Lab 2: The Full Cycle - Predict, Diff, Save, Apply, Recover

::: {.lab}
### Lab 2 - Plan discipline against a real target {#lab2}

1. Rebuild the Chapter 2 project with a `variable "external_port"` (type `number`, validated) and a locals-driven name (`atlas-${var.env}` with `env` defaulting to `lab`).
2. Run `terraform plan -out=tfplan` and read every line. Predict the effect of `apply tfplan` before running it - then run it and confirm the apply output matches the plan summary exactly.
3. Add a `random_id` resource (from the `hashicorp/random` provider) whose hex feeds the container name, `init -upgrade` to fetch it, and re-plan: notice the create, and notice that apply changes the container's *name* - check `docker ps` to see what a name replacement does to a running service.
4. Edit the container's `image` tag in configuration and re-plan; identify in the diff whether the change is in-place or replacement, and say why before checking the provider docs.
5. Change the port *in Docker directly* (`docker stop` then `docker run` a lookalike, or edit labels via `docker update`), run `terraform plan`, and read the drift block. Repair it with `terraform apply -refresh-only` (accept reality) - then revert it with a normal plan/apply (restore the code's intent). Understand which direction you chose and when each is right.
6. Finish with `terraform destroy` and `terraform state list` to confirm an empty state; then delete nothing else.
:::

**See also:** [Chapter 7](#ch7) for the state these commands read and write, [Chapter 12](#ch12) for the CI pipeline that automates this loop, and [Appendix A](#appA) for the flag reference.
