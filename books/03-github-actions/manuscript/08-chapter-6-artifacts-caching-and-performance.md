# Chapter 6 - Artifacts, Caching, and Performance {#ch6}

## 6.1 Artifacts: Data Between Jobs and to Humans

Artifacts are files uploaded during a run and downloadable afterward - the transport layer between stateless jobs and the record you keep for humans. The current generation is `actions/upload-artifact@v4` and `actions/download-artifact@v4`: uploads are immutable per workflow run, name-scoped, and vastly faster than the deprecated v3 (which GitHub retired after January 30, 2025 along with the Pages deployment action changes). Each artifact carries metadata - name, size, checksum - and retention is governed by repository policy, defaulting to 90 days, adjustable per upload with `retention-days`, and now surfaced consistently: since late 2026 the retention rules cover checks, runs, and statuses uniformly, and expired artifacts disappear from both UI and API.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: npm ci && npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: dist-${{ github.sha }}
          path: dist/
          retention-days: 14
          if-no-files-found: error

  e2e:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist-${{ github.sha }}
          path: dist/
```

Treat artifacts as plumbing, not as a release registry. The discipline that scales: name artifacts with the commit SHA, upload once and download everywhere, set explicit `if-no-files-found: error` so silent empty uploads cannot masquerade as success, and keep retention short for CI intermediates while long-lived releases go to GitHub Releases or Packages. Storage is billed, and a year of 400 MB nightly artifacts is a real invoice line.

## 6.2 Caching: actions/cache and Its Scopes

`actions/cache@v4` is the general-purpose cache: you provide a key, a list of paths to store, and an ordered list of `restore-keys` fallbacks. Keys are exact-match; `restore-keys` enable prefix matching so a changed lockfile still restores yesterday's 90-percent-overlapping cache and only refetches the delta. Cache entries are scoped to the repository **and** the branch: a workflow on `main` can seed a cache that pull-request branches restore, but a feature branch can never write a cache that `main` restores - the direction of trust flows from default branch to feature branches, never sideways or upward.

```
- uses: actions/cache@v4
  with:
    path: ~/.npm
    key: npm-${{ runner.os }}-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      npm-${{ runner.os }}-
```

Practical constraints: total cache storage per repository is 10 GB, with least-recently-used eviction when full; entries untouched for seven days are also evicted; and the February 2025 service migration forced the v3/v4 upgrade (old twirp endpoints were retired). For language-specific use, the `setup-*` actions accept a `cache:` input that wraps the same machinery with correct paths (`setup-node` with `cache: npm`, `setup-python` with `cache: pip`, `setup-go`, `setup-java`). Cache jobs must be idempotent and safe to restore: never cache credentials inside cached directories, and remember that a poisoned cache is a supply-chain vector - the trust boundary of a cache is the branch that wrote it.

::: {.note}
**Best practice - measure before caching**

Cache save and restore cost minutes. If `npm ci` on a warm network takes 40 seconds and cache round-trips take 35, you are optimizing theater. Instrument one run with and without the cache before enshrining it, and revisit the decision when dependency counts change. For Docker builds, layer-cache via the registry (`cache-from`/`cache-to` with GHCR) instead of duplicating images into the actions cache.
:::

## 6.3 Speed as a Design Concern

Pipeline latency is architectural. The levers, in order of impact: split independent work into parallel jobs instead of one serial job; keep `needs` graphs minimal (lint should not wait for the database image); filter events with `paths` so irrelevant changes do not run at all; cancel superseded pull-request runs with `concurrency`; and right-size `timeout-minutes` so wedged jobs die in minutes rather than the default 360. Matrix strategies (Chapter 7) and test sharding push the same idea further - total wall time should track the slowest shard, not the sum of suites.

- **Parallelism** - unrelated jobs run concurrently by default; resist the temptation to chain them for cosmetic order.
- **Path filters** - `on.pull_request.paths` plus `dorny/paths-filter`-style job-level gating for monorepo fan-out.
- **Timeouts everywhere** - `timeout-minutes` on every job; a 6-hour accidental hang is a bill and a blocked queue.
- **Runner choice** - larger runners (4-64 vCPU) buy wall-clock on heavy builds; ARM runners serve container fleets natively.
- **Cache discipline** - keyed on lockfiles, restore-keys for resilience, measured to prove value.

The platform enforces two ceilings you should plan around rather than discover: a single job may run for 6 hours, and a workflow run for 35 hours total. Both exist to bound runaway compute; neither is a suggestion. If a legitimate workload approaches them, the correct answer is sharding and resumability, not a support ticket.

**See also:** [Chapter 7](#ch7) for the matrices that multiply this cost, [Chapter 13](#ch13) for the bill at the end of the month, and the *Docker for DevOps Engineers* volume for the layer caching these steps complement.
