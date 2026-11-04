# Chapter 13 - Monitoring, Troubleshooting, and Cost Management {#ch13}

## 13.1 Debugging Workflow Failures

Workflow debugging has a disciplined order of operations. Read the failed step's log first - most failures are honest: a test failed, a network call timed out, a YAML typo. Then check the job's setup and teardown phases: checkout, cache restore, and post-job cleanup steps fail independently of your code. Re-run failed jobs only to confirm flakiness, not to wish failures away; a run that needs three retries needs an investigation. The platform's escalation hatches: re-enable a workflow with debug logging by setting repository (or runner) secrets `ACTIONS_RUNNER_DEBUG` and `ACTIONS_STEP_DEBUG` to `true`, which turns on runner diagnostics and step-level debug output; and `gh run view <id> --log-failed` greps just the failing sections from the CLI, which is faster than the UI for large runs.

- **Symptom: workflow did not trigger.** Check the event filters (`paths`, `branches`), check that the workflow file exists on the triggering ref, remember scheduled runs come only from the default branch, and remember `[skip ci]`.
- **Symptom: secret is empty.** Secrets do not flow into `pull_request`-triggered runs from forks; environment secrets require targeting that environment; and org secrets must grant the repository access.
- **Symptom: cache never hits.** The key includes a hash that changed, the entry was written on a branch that cannot read it (trust flows default-branch down), or the 10 GB pool evicted it.
- **Symptom: action startup failure mentioning node.** An old major still declares `node20`, which was removed from runners on September 23, 2026 - bump the action or rebuild its `dist` with `node24`.
- **Symptom: 403 on API calls.** The `GITHUB_TOKEN` lacks the permission, or the 1,000-requests-per-hour repository rate limit was exhausted by a loop.

## 13.2 Observability Beyond the Actions Tab

The Actions UI is where debugging starts, not where fleet visibility lives. For engineering-wide metrics, extract data through the APIs: workflow runs and jobs (REST), check runs (REST/GraphQL), and webhooks (`workflow_run`, `check_suite`, `deployment_status`) streamed into your monitoring stack. Teams tracking DORA-style signals - deployment frequency, lead time for change, change failure rate - typically pipeline `workflow_run` and `deployment_status` events into their analytics warehouse or a tool such as Datadog CI Visibility; the events carry everything needed (repo, ref, conclusion, timings). Since late 2026, retention and expiration behave uniformly across runs, checks, and statuses, and expired artifacts are hidden in API as well as UI, so build export jobs with those lifecycles in mind - history you do not export is history you eventually lose.

::: {.note}
**Best practice - one dashboard for the pipeline**

Pick the four numbers that describe your delivery health (CI success rate, median PR-to-green time, deploy frequency, per-repo minutes spent) and put them on one dashboard with alerting on regressions. Teams that can see minute-burn by repository catch both runaway loops and the quiet cost creep of an ever-growing test matrix.
:::

## 13.3 The Billing Model in Detail

The meter is minutes, and the multiplier is the OS: Linux 1x, Windows 2x, macOS 10x - a minute of macOS burn is ten minutes of Linux burn, which is why fleets of Intel macOS CI jobs were the first thing every team migrated to Apple silicon or Linux containers. Included monthly allowances on hosted runners: 2,000 minutes (Free), 3,000 (Pro), 3,000 (Team), 50,000 (Enterprise Cloud). Larger runners bill at their own per-minute rates (multiplied by the same OS multipliers) and cannot be paid from included minutes. Storage for artifacts and logs is metered separately. Per-minute rounding is up to the nearest minute per job, so many tiny jobs inflate the bill - another argument for batching trivial steps into sensible jobs rather than one-step-per-command layouts.

Two administrative changes of 2025-2026 belong in every cost model. First, **self-hosted metering**: from March 1, 2026, self-hosted runner usage is billed at 0.002 dollars per minute with monthly free allowances (1,000 minutes Free, 3,000 Team, 50,000 Enterprise Cloud; GitHub Enterprise Server exempt) - the days of 'self-hosted is free compute' are over on GitHub-hosted services. Second, the **usage APIs** became the source of truth: `gh api /orgs/{org}/settings/billing/usage` (and the per-repository usage report) now exposes Actions minutes by runner type, including self-hosted metering, which makes chargeback to teams a spreadsheet export instead of a month of detective work.

| Lever | Action | Typical effect |
| ------------ | --------------------- | ----------------- |
| Cancel superseded runs | `concurrency` with `cancel-in-progress` on PR CI | 20-40% fewer runs on active repos |
| Path filters | `on.<event>.paths` per workflow; job-level gates in monorepos | Silences irrelevant runs entirely |
| Runner selection | Move macOS Intel workloads to Linux or Apple silicon; right-size larger runners | Removes 10x multipliers; pays for itself |
| Matrix hygiene | `fail-fast: false` plus `max-parallel` caps; prune dead cells | Bounded worst-case burn |
| Caching | Lockfile-keyed caches; registry-backed Docker layer cache | Minutes per run, multiplied by volume |
| Timeouts | `timeout-minutes` on every job | Caps accident damage at minutes, not hours |
| Sharding | Split slow suites; wall time tracks slowest shard | Latency win that can cut total burn |

: Table 13.1 - Cost levers, in the order to pull them

## 13.4 Retention and Data Hygiene

Defaults are storage policies as much as convenience: workflow runs and their logs are retained 90 days, artifacts 90 days, and both are configurable per repository (and per artifact upload) within plan-dependent bounds, with enterprise accounts able to extend retention substantially. The hygiene rules that keep bills and audit windows aligned: short retention for CI intermediate artifacts, explicit longer retention for release evidence and security scan outputs, scheduled exports of anything compliance requires beyond the platform's window, and a quarterly sweep for repositories whose workflows no longer run but whose artifacts still bill. Since the late-2026 retention unification, a single repository setting governs runs, checks, and statuses together - simpler to reason about, and one more reason to script the sweep.

**See also:** [Chapter 7](#ch7) for the runs that generate these logs, [Chapter 11](#ch11) for the runners whose health you are watching, and [Appendix C](#appC) for the failure patterns worth memorizing.
