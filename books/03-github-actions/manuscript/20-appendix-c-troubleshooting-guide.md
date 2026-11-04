# Appendix C - Troubleshooting Guide {#appC}

## C.1 Symptom-to-Cause Reference

| Symptom | Likely cause | Fix |
| ------------- | ------------------ | ------------------- |
| Workflow never triggers | Path/branch filters exclude the change; file not on default branch; `[skip ci]` present; schedule dormant after 60 idle days | Verify filters against changed files; confirm the file exists on the triggering ref; remove skip markers; re-save the schedule with a dummy commit |
| 'Permission denied' on API/push | GITHUB\_TOKEN lacks scope; default read-only token | Add least-privilege `permissions:` (contents/packages/deployments as needed) at job level |
| Secret empty in logs | Fork PRs get no secrets; wrong environment not targeted; repo lacks org-secret access | Use `pull_request_target` safely or `workflow_run`; target the environment; grant repo access to the org secret |
| Action fails at startup with Node error | Action still declares `node20` (removed Sept 23, 2026) | Bump to a `node24` release or rebuild the action's dist; update self-hosted runner versions |
| Cache always misses | Lockfile hash changed with no restore-key; entry written on a branch you cannot read; 10 GB eviction | Add `restore-keys`; cache from default branch; trim cache paths |
| Job hangs until killed | No `timeout-minutes`; interactive prompt waiting for input | Set timeouts; use non-interactive flags (`CI=true`, `--yes`, `DEBIAN_FRONTEND=noninteractive`) |
| Docker push rejected | Repository name contains uppercase letters | Lowercase the image path (`${GITHUB_REPOSITORY,,}`) before tagging |
| Merge blocked though checks green | Required check name mismatch (matrix-renamed job) | Match protection settings to exact job/check names; stabilize check naming |
| OIDC credential exchange fails | Missing `id-token: write`; trust policy ref/environment mismatch | Grant the permission; align `sub`/claims with the cloud trust policy |
| Unexpected large minutes bill | Uncapped matrix; macOS multiplier; no concurrency cancellation | Apply Table 13.1 levers; review larger-runner assignments |

: Table C.1 - Fast diagnosis by symptom

## C.2 Local Reproduction Techniques

Most workflow failures reproduce locally with the same ingredients: run the failing command in the runner's shell baseline (bash on Linux, PowerShell on Windows), pin the same toolchain versions the setup actions install, and set `CI=true` so tools behave as they do in CI. For workflow-level logic - expressions, conditions, ordering - `act` (nektos/act) runs jobs in local Docker containers with a close approximation of the runner environment, useful for trigger and matrix logic though not a substitute for a real hosted run. For self-hosted debugging, run the runner process in the foreground (`./run.sh --ephemeral`) to watch registration, job pickup, and teardown live, and enable the debug secrets from Section 13.1 on a scratch repository rather than polluting production logs.

## C.3 When to Escalate to GitHub Support

Some classes of failure belong to the platform rather than to you: runs stuck in `queued` beyond your concurrency quota's explanation; runner image maintenance windows drifting from the published schedule; billing usage that contradicts your own minute math; and webhooks or API responses that fail persistently with server-side errors. Before opening a ticket, capture the evidence support will ask for: run URLs, run IDs, timestamps in UTC, repository and org names, and - for billing - the usage export. Subscribe the platform team to the GitHub changelog; the majority of 'yesterday it worked' platform surprises (image retirements, runtime removals, retention changes) are announced there weeks in advance, and a two-line changelog subscription has saved more weekends than any other single practice in this book.
