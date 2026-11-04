# Chapter 3 - Jobs, Steps, and Runners {#ch3}

## 3.1 Jobs: Units of Scheduling and Failure

A job is the smallest unit the platform schedules. Each job gets a fresh runner, a fresh workspace, and an independent failure domain: when a job fails, other jobs continue unless they declared `needs` on it. Job IDs are keys under `jobs:` and become both the display name and the programmatic identifier used in `needs`, in output references, and in the checks API. Give jobs plain, grep-friendly IDs (`lint`, `test`, `build`, `deploy-staging`) and reserve human-friendly wording for the optional `name:` field - debugging is much easier when logs, checks, and YAML all use the same string.

Jobs declare where they run with `runs-on`, how long they may run with `timeout-minutes`, and what they depend on with `needs`. A job may also declare a `strategy` (Chapter 7 turns this into matrices), a `container` in which to run, `services` to compose alongside it, and an `environment` for deployment gating (Chapter 9). The `permissions` block can be narrowed per job, which is the correct granularity for anything touching the `GITHUB_TOKEN`: a workflow that lints code has no business holding package-write rights.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    needs: lint
    steps:
      - uses: actions/checkout@v6
      - run: npm ci && npm test

  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v6
      - run: npm ci && npm run lint
```

## 3.2 Steps: Commands and Actions

Steps run sequentially within a job and share three things: the workspace directory, the `GITHUB_PATH` and `GITHUB_ENV` mechanisms for exporting values, and the job's lifetime. A step with a `run:` key executes a shell command; a step with a `uses:` key executes an action. The two are mutually exclusive. Every step gets an ID (`id:`) whose outputs other steps can read through `steps.<id>.outputs`, and steps support `if:`, `env:`, `working-directory:`, `shell:`, `continue-on-error:`, and `timeout-minutes:` at their own scope. Name your steps with `name:` - the default log line for an un-named run step is the raw command, which becomes unreadable in any nontrivial job.

The default shell differs by runner OS: bash without pipefail on Linux and macOS, PowerShell on Windows. Two habits remove a whole class of silent breakage. Set `defaults: run: shell: bash` at workflow or job level when you write bash everywhere, and remember that bash's default mode does **not** stop on the first failing command in a pipeline: a `curl | grep` step can exit zero even when `curl` failed. Use `shell: bash` with an explicit `set -euo pipefail` line at the top of multi-command scripts, or split commands into separate steps where each failure is visible.

```yaml
steps:
  - name: Run migration safely
    shell: bash
    working-directory: services/api
    run: |
      set -euo pipefail
      ./scripts/migrate.sh
      ./scripts/smoke-check.sh
```

## 3.3 Runners: GitHub-Hosted Virtual Machines

Hosted runners are ephemeral Azure virtual machines built from public image definitions in the `actions/runner-images` repository. Every job starts from a clean snapshot: nothing you install survives the job, disk state cannot leak between customers, and the toolchain is refreshed on a published schedule. Standard Linux runners offer 4 vCPUs and 16 GB of RAM; Windows runners match that; Apple-silicon macOS runners offer 3 vCPUs and 7 GB. The virtual environment labels you can target are `ubuntu-latest`, `ubuntu-24.04`, `ubuntu-22.04`, `windows-latest`, `windows-2022`, `windows-2025`, and the macOS family (`macos-latest` pointing at Apple silicon, `macos-15`, `macos-14`, plus the retiring `macos-13`).

| Label | OS | Notes |
| ----------- | ------------- | -------------------------- |
| ubuntu-latest | Ubuntu 24.04 | Resolves to the newest stable Ubuntu image; Docker preinstalled, but the set of pre-pulled images was trimmed on 24.04 |
| ubuntu-24.04 / ubuntu-22.04 | Ubuntu LTS | Pin the exact LTS for reproducibility; ubuntu-20.04 images were retired in 2025 |
| windows-latest | Windows Server 2022 | windows-2025 images are available; windows-2019 was retired in 2025 |
| macos-latest | macOS 15 (Apple silicon) | Arm64 runners; Intel images (macos-13) are deprecated |
| macos-15 / macos-14 | macOS 15 / 14 | macos-14 reached retirement on October 1, 2026; Xcode 27 image available on newer macOS |

: Table 3.1 - GitHub-hosted runner labels (October 2026)

::: {.warn}
**Watch out - latest is a moving floor**

`ubuntu-latest` and friends are convenience labels that move to new major OS versions over time. Production pipelines that must reproduce byte-identical artifacts should pin exact versions (`ubuntu-24.04`) and record the image build number from the run summary. Teams learn this lesson when a `latest` rollover changes a compiler version under a release tag.
:::

## 3.4 Container Jobs and Services

A job may declare a `container:` instead of running directly on the host VM. Everything in `steps` then executes inside that container, with the runner VM acting as the supervisor: it mounts the workspace, injects environment variables, and forwards the network namespace. Container jobs are the cleanest way to pin a toolchain (a specific Python, a Rust cross-compiler, a database client) without depending on what the hosted image ships this month. The `services:` block composes additional containers - typically databases and message brokers - on a user-defined Docker network, reachable by service label as hostname, with health checks deciding when the job may start.

```yaml
jobs:
  integration:
    runs-on: ubuntu-latest
    container:
      image: node:22-bookworm
      env:
        DATABASE_URL: postgres://app:app@postgres:5432/app
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: app
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v6
      - run: npm ci && npm run test:integration
```

::: {.note}
**Note - containers on macOS and Windows**

Container jobs are a Linux-runner feature. On macOS and Windows hosted runners, `container:` is unsupported; use setup actions or tool caches instead. Docker-in-Docker scenarios (building images inside a container job) work on Linux via mounted sockets but add fragility - prefer running build steps directly on the runner with `docker/build-push-action`.
:::

## 3.5 Environment Variables and the Workspace

Environment variables arrive from four scopes, each overriding the previous: runner defaults, workflow-level `env`, job-level `env`, and step-level `env`. The platform also injects a documented set of default variables - `GITHUB_WORKSPACE`, `GITHUB_SHA`, `GITHUB_REF_NAME`, `GITHUB_RUN_ID`, `GITHUB_RUN_NUMBER`, `GITHUB_ACTOR`, and `CI=true` among them - which are the stable, documented way to read repository context from scripts. For writing rather than reading, steps export values by appending to the special files `GITHUB_ENV` (environment variables for subsequent steps) and `GITHUB_PATH` (PATH additions); outputs from `uses:` steps travel through the `GITHUB_OUTPUT` file. Chapter 5 gives these mechanisms their full treatment alongside expressions.

The workspace is a fresh directory per job, checked out by `actions/checkout`. Subsequent jobs do not inherit it: anything one job produces for another must travel through artifacts (Chapter 6) or job outputs. This statelessness is a feature - it forces pipelines to be reproducible - but it is also the single most common surprise for engineers arriving from Jenkins, where workspaces persist by default.

::: {.lab}
### Lab 1 - Your First Complete CI Pipeline {#lab1}

1. Create a new public repository and add a minimal Node.js service (or clone a sample project); confirm `npm ci` and `npm test` pass locally.
2. Add `.github/workflows/ci.yml` with three jobs: `lint`, `test`, and `build`. Make `test` and `build` depend on `lint` with `needs: lint`.
3. Set `permissions: contents: read` at workflow level, `timeout-minutes: 10` on every job, and `concurrency` with `cancel-in-progress: true` grouped on `github.ref`.
4. Run the `test` job against a `postgres:17` service container with a health check, and prove the job fails if the database is unreachable.
5. Open a pull request and observe: the checks API renders each job as a required check; deliberately break a test and confirm the merge is blocked once you mark `test` required in branch protection.
6. Intentionally remove `timeout-minutes` from one job, add `sleep 600`, and watch the run consume minutes needlessly - then restore the cap and write the number into your team's runbook.
:::

**See also:** [Chapter 4](#ch4) for the actions these steps call, [Chapter 11](#ch11) for the machines they run on, and [Appendix A](#appA) for runner labels and matrix syntax.
