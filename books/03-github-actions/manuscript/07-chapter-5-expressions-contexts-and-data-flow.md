# Chapter 5 - Expressions, Contexts, and Data Flow {#ch5}

## 5.1 Contexts: The Data Available to You

A context is a named bag of metadata describing the current run. Expressions - always wrapped in `${{ }}` - read into those bags, and every decision you make in YAML goes through them. The contexts you will use weekly are `github` (event payload, ref, SHA, actor, repository, `run_id`), `env` (environment variables you set in YAML), `vars` (configuration variables stored on repo/org), `secrets`, `needs` (outputs and results of dependencies), `steps` (outputs of steps in the same job), `inputs` (workflow and action inputs), `runner`, `job`, and `matrix`. The full map lives in the workflow syntax documentation, but internalizing these ten is enough for production work.

| Context | Contains | Typical use |
| ------- | -------------------- | ----------------------- |
| github | Event payload, ref, SHA, actor, token-less repo info | Branch filters, PR guards, run identifiers |
| env | Variables declared in YAML env blocks | Conditioning steps on configured values |
| vars | Repo/organization configuration variables | Non-secret config: feature flags, endpoints |
| secrets | Repo/environment/organization secrets | Credentials - never logged, never echoed |
| needs | Result and outputs of dependent jobs | Fan-in deploy decisions after parallel CI |
| steps | Outputs, conclusion, outcome of same-job steps | Reading tool output from earlier steps |
| inputs | workflow\_dispatch / workflow\_call inputs | Parameterizing manual and reusable runs |
| matrix | Current matrix cell values | Per-OS, per-version step differences |

: Table 5.1 - The contexts that matter in daily work

Context availability is scoped: `steps` exists only inside a job, `needs` only after `needs` is declared, and `secrets` is deliberately unavailable in a few places (most notably in top-level `jobs.<id>.if`). When a workflow refuses to start with a cryptic reference error, check whether the context you referenced is legal at that position - it is the most common syntax-class failure after plain YAML indentation mistakes.

## 5.2 Expression Language: Operators and Functions

The expression language is small and typed loosely. Operators include the usual comparisons, logical `&&` and `||`, null-coalescing `??`, string concatenation via `format()`, and status functions - `success()`, `failure()`, `cancelled()`, `always()` - that make `if:` conditions readable. Helper functions cover JSON (`fromJson`), hashing (`hashFiles`, the canonical cache-key ingredient), string search (`contains`, `startsWith`), array work (`join`, `fromJSON` on arrays), and type coercion. There are no loops and no variables you can assign inside an expression; anything more elaborate than a conditional belongs in a script or an action.

```yaml
steps:
  - name: Deploy on success or specific failure
    if: ${{ success() || (failure() && needs.test.result == 'success') }}
    run: ./deploy.sh

  - name: Run only for merged PRs to main
    if: >-
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      !contains(github.event.head_commit.message, '[skip deploy]')
    run: ./notify.sh
```

Condition semantics matter more than operator trivia. A job step's `if` defaults to `success()` - steps are skipped after any earlier failure unless you opt back in with `failure()`, `always()`, or `cancelled()`. The `continue-on-error: true` flag lets a step fail without failing the job, and `steps.<id>.outcome` records what happened while `steps.<id>.conclusion` records what was allowed to count. Distinguishing those two fields is the difference between 'report flakiness without failing' done correctly and done accidentally.

## 5.3 The Environment Variable Hierarchy and Exporting

Values flow into steps through four channels, and confusion between them is the classic beginner bug. Environment variables are set in `env` blocks (workflow, job, step scopes) and are visible to **shell code** but not to expressions. Expressions read **contexts**, not raw environment variables - `${{ env.FOO }}` reads only what YAML itself declared, not what a script exported. Steps that need to publish values to later steps append `NAME=value` lines to `$GITHUB_ENV`; publish outputs to `$GITHUB_OUTPUT` as `key=value` pairs; and add directories to `$GITHUB_PATH`. The modern form of a 'compute then consume' pair looks like this:

```yaml
steps:
  - name: Compute version
    id: ver
    run: |
      echo "version=v$(date +%Y%m%d)-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      echo "channel=nightly" >> "$GITHUB_ENV"

  - name: Use the values
    run: |
      echo "Output version : ${{ steps.ver.outputs.version }}"
      echo "Env channel    : $channel"
      echo "Both appear in later steps of this job only."
```

::: {.warn}
**Watch out - outputs are job-scoped**

`$GITHUB_OUTPUT` and `$GITHUB_ENV` values exist within the job that wrote them. To hand a value to another job, declare a job-level `outputs:` map that references a step output, and let consumers read it through the `needs` context. Forgetting the job-level map is the most frequent 'my output is empty downstream' cause.
:::

## 5.4 Secrets, Variables, and the GITHUB\_TOKEN

The platform offers three stores with different trust levels. **Encrypted secrets** (repository, environment, and organization scope) are write-only from the workflow's perspective: masked in logs, not echoable, not readable via API. **Configuration variables** are plain-text, API-readable settings for non-sensitive configuration - endpoint URLs, feature toggles, default regions. The automatic **`GITHUB_TOKEN`** is a short-lived installation token minted per job, scoped by the `permissions:` block (Chapter 12 makes least privilege the default posture), and usable both as `${{ secrets.GITHUB_TOKEN }}` and via `gh` CLI with `GH_TOKEN` set. Since 2023 the token defaults to read-only repository permissions on new repositories, which is the correct default; workflows that publish packages or create releases must request the specific scopes they need.

Masking is real but not magic. Values are masked in log output, yet anything a step writes to artifacts, statuses, comments, or external systems leaves the mask behind. The rules that keep secrets honest: never pass secrets on command lines (they leak through `ps` and error output), prefer environment variables or the runtime API, rotate through environments rather than workflow YAML, and audit with secret scanning plus push protection, which GitHub's security features provide out of the box on the Advanced Security plans and for public repositories.

## 5.5 Passing Data Between Jobs

The canonical fan-in pattern: parallel jobs compute, a dependent job consumes. Jobs declare `outputs:` mappings from names to step outputs; dependents declare `needs:` and read `needs.<job>.outputs.<name>`. Combined with `needs.<job>.result`, this is also how you encode policy like 'deploy only if all gates succeeded and this run came from the default branch'.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image: ${{ steps.img.outputs.name }}
    steps:
      - uses: actions/checkout@v6
      - id: img
        run: echo "name=ghcr.io/${GITHUB_REPOSITORY}:${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      - run: ./build-and-push.sh

  deploy:
    needs: build
    if: ${{ needs.build.result == 'success' && github.ref == 'refs/heads/main' }}
    runs-on: ubuntu-latest
    steps:
      - run: ./deploy.sh '${{ needs.build.outputs.image }}'
```

**See also:** [Chapter 2](#ch2) for where these expressions sit in the file, [Chapter 6](#ch6) for cache keys built out of them, and [Appendix A](#appA) for the full context list.
