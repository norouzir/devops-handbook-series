# Appendix A - Workflow Syntax Quick Reference {#appA}

## A.1 Top-Level Workflow Keys

| Key | Purpose |
| ----------- | --------------------------------------- |
| `name` | Display name in the Actions tab; defaults to the file path |
| `run-name` | Per-run title (expression-interpolated) shown in run lists |
| `on` | Event triggers: push, pull\_request, workflow\_dispatch, schedule, workflow\_call, release, and webhook events |
| `permissions` | Scopes the automatic GITHUB\_TOKEN (workflow or job level) |
| `env` | Environment variables available to all jobs and steps |
| `defaults` | Default `run.shell` and `run.working-directory` for all steps |
| `concurrency` | Queueing group; `cancel-in-progress` replaces superseded runs |
| `jobs` | The job graph - the only mandatory key besides `on` |

: Table A.1 - Top-level keys

## A.2 Event Filters Worth Memorizing

| Event | Key filters | Notes |
| ---------- | ----------------------- | ----------------- |
| `push` | `branches`, `tags`, `paths`, `paths-ignore` | Fires on the pushed ref; `[skip ci]` honored |
| `pull_request` | `branches` (base), `types`, `paths` | Runs contributor's file; read-only token; no secrets from forks |
| `pull_request_target` | same as above | Runs base-branch file with full token - harden or avoid |
| `workflow_dispatch` | `inputs` (string, boolean, number, choice, environment) | Manual button; ref selectable in UI/API/CLI |
| `repository_dispatch` | `types` | External webhook via API; payload in `client_payload` |
| `schedule` | `cron` (UTC) | Default branch only; delayed under load; disabled after 60 days of inactivity |
| `workflow_run` | `workflows`, `types` | Chains after another workflow; default-branch context |
| `merge_group` | `branches` | Merge-queue verification of prospective merges |
| `release` | `types` (published, prereleased, ...) | Richer release signal than tag push |
| `workflow_call` | `inputs`, `outputs`, `secrets` | Makes the workflow reusable |

: Table A.2 - Common triggers and their key filters

## A.3 Job and Step Keys

| Key | Purpose |
| ----------- | --------------------------------------- |
| `runs-on` | Runner labels: hosted (`ubuntu-24.04`, `windows-2025`, `macos-15`) or self-hosted label sets |
| `needs` | Job dependencies; outputs/results arrive via the `needs` context |
| `if` | Condition using the expression language and status functions |
| `timeout-minutes` | Kill switch (job or step); default 360 |
| `strategy.matrix` | Fan-out cells; pair with `fail-fast`, `max-parallel`, `exclude`, `include` |
| `environment` | Binds the job to an environment (protection rules, scoped secrets) |
| `container` / `services` | Run the job in a container; compose service containers (Linux runners) |
| `uses` / `run` | Step types: an action reference or a shell command (mutually exclusive) |
| `with` / `env` | Action inputs; per-step environment |
| `continue-on-error` | Let a step fail without failing the job (outcome vs conclusion) |

: Table A.3 - Job and step essentials

## A.4 Expressions Cheat Sheet

```bash
${{ github.ref_name }}            branch or tag name
${{ github.sha }}                  commit SHA of the triggering ref
${{ github.actor }}                user who triggered the run
${{ github.event_name }}           'push', 'pull_request', ...
${{ github.event.pull_request.number }}
${{ inputs.environment }}          workflow_dispatch / workflow_call input
${{ needs.build.outputs.image }}   output of a dependent job
${{ steps.img.outputs.name }}      output of a step in this job
${{ matrix.os }}                   current matrix cell
${{ secrets.MY_SECRET }}           masked; unavailable in some positions
${{ vars.MY_VAR }}                 configuration variable

# functions
success()  failure()  cancelled()  always()
contains('abc','b')  startsWith()  endsWith()
format('v{0}-{1}', a, b)  join(list, ',')
fromJson(s)  toJSON(v)  hashFiles('**/lock')
a || b  a && b  a == b  a != b  !cond  x ?? fallback
```

## A.5 Default Environment Variables

| Variable | Meaning |
| --------------- | ----------------------------------- |
| `GITHUB_WORKSPACE` | Working directory of the job's checkout |
| `GITHUB_SHA` | Commit SHA that triggered the workflow |
| `GITHUB_REF` / `GITHUB_REF_NAME` | Full ref and its short name |
| `GITHUB_REPOSITORY` | `owner/repo` (lowercase it for GHCR paths) |
| `GITHUB_RUN_ID` / `GITHUB_RUN_NUMBER` | Identifiers for links and versioning |
| `GITHUB_ENV` / `GITHUB_OUTPUT` / `GITHUB_PATH` | Files a step appends to export values to later steps |
| `RUNNER_OS` | `Linux`, `Windows`, or `macOS` |
| `CI` | Always `true` - lets local/CI code branches behave differently |

: Table A.4 - Default variables used most in scripts
