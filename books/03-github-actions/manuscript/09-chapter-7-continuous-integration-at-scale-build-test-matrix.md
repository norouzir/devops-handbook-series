# Chapter 7 - Continuous Integration at Scale: Build, Test, Matrix {#ch7}

## 7.1 Matrix Strategies

A `strategy.matrix` stamps out one job per combination of values, each with the same recipe but different `matrix` context. The canonical use is version grids - one test job per OS and runtime pair - but the same mechanism serves architecture sweeps, feature-flag combinations, and per-module builds in monorepos. Matrix values can be strings, numbers, or booleans, and nested values become properties you address as `matrix.os`, `matrix.node`, and so on. The generated jobs are named `job (cell1, cell2)`, which reads beautifully in the checks API.

```yaml
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      max-parallel: 8
      matrix:
        os: [ubuntu-latest, macos-latest]
        node: [20, 22, 24]
        exclude:
          - os: macos-latest
            node: 20
        include:
          - os: ubuntu-latest
            node: 24
            coverage: true
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v5
        with:
          node-version: ${{ matrix.node }}
          cache: npm
      - run: npm ci
      - run: npm test -- --cov=${{ matrix.coverage == true }}
```

Three controls govern matrix behavior. `fail-fast: true` (the default) cancels all remaining cells when one fails - fast signal, but it hides secondary failures and churns re-runs; `fail-fast: false` is what mature CI uses for test grids. `max-parallel` caps concurrent cells to protect quota and external services from 30 simultaneous hammering jobs. `exclude` prunes combinations; `include` adds or enriches them - and include entries with only extra properties are merged into **every** matching combination, which is exactly how the single `coverage: true` flag above lands on one cell. A matrix may generate at most 256 jobs per run, a ceiling that matters more as a billing guardrail than as a practical limit.

## 7.2 Sharding Slow Test Suites

When a single suite outgrows a job, shard it: a matrix of N cells, each running a slice of tests, then a small fan-in job that merges reports. The slicing mechanism varies by ecosystem - Jest and Playwright accept an index/count pair, pytest-mark-split and friends produce explicit buckets - but the workflow shape is constant. Wall time converges on the slowest shard, so strive for balanced, deterministic assignment (hash the test name, do not sort randomly), and let each shard upload its report artifact for a merge step to aggregate.

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - uses: actions/checkout@v6
  - run: npm ci
  - run: npx jest --shard=${{ matrix.shard }}/4 --coverage
  - if: failure()
    uses: actions/upload-artifact@v4
    with:
      name: junit-shard-${{ matrix.shard }}
      path: junit.xml
      if-no-files-found: ignore
```

## 7.3 Quality Gates: Coverage, Linting, and Required Checks

A gate is a check whose result the platform enforces, not just displays. The enforcement mechanism is branch protection (and organization rulesets for wider reach): mark the workflow's job or check name **required**, and merges are blocked while it is red or pending. Coverage gates convert test output into policy - upload a coverage report, compute a summary, fail the job under threshold, or comment the delta on the pull request for humans to judge. Linting gates are cheaper and earlier: format and static-analysis jobs should run before tests, on every pull request, and should be fast enough that developers never learn to bypass them.

Choose enforcement levels deliberately. Some checks are hard gates (build compiles, security scan clean, unit tests pass); some are informational (coverage trend, bundle size delta); some are advisory-but-blocking-for-others (integration suite runs only when `ci-full` label is present, required only for release branches). Encode those tiers as separate jobs with distinct names so branch protection can target them precisely - a single monolithic `ci` check becomes impossible to gate on granularly.

::: {.note}
**Best practice - name checks for gates**

Required checks match by exact job or check-run name. Give gate jobs short, stable, dot-free names (`test`, `lint`, `security`) and let matrices carry the variability - renaming a required check silently unblocks merges until someone re-adds it, so treat check names as API surface and review changes accordingly.
:::

## 7.4 Merge Queue and Final Verification

On busy repositories, a green pull request can still break `main` when two independently green changes conflict - the classic semantic merge failure. The merge queue addresses it: pull requests are grouped, and the `merge_group` event runs your required workflow against the prospective merge result before the commits land. Configure it alongside branch protection with 'Require merge queue', keep the queued verification to the fast, flake-free subset of checks, and set reasonable group sizes. The queue trades a few minutes of latency for the invariant that `main` is always releasable - an invariant worth real money once more than a handful of engineers merge daily.

::: {.lab}
### Lab 2 - Matrix CI with Coverage Gate {#lab2}

1. Take Lab 1's repository and add a `strategy.matrix` over Node versions 20, 22, and 24 with `fail-fast: false` and `max-parallel: 3`.
2. Add an `exclude` cell for one legacy combination and an `include` cell that enables coverage only on Node 24.
3. Wire `actions/setup-node@v5` with `cache: npm`, keyed on `package-lock.json` via `hashFiles`, and confirm the cache hit in the run log on a second run.
4. Shard the test suite into two `jest --shard=i/2` cells; upload per-shard JUnit artifacts with `if-no-files-found: ignore` and merge them in a `report` job that `needs` the matrix.
5. Publish a coverage summary and fail the job when line coverage drops below 80 percent; open a PR that reduces coverage and watch the gate hold.
6. Mark `test`, `lint`, and `report` as required status checks in branch protection; merge only through the merge queue with a `merge_group` trigger added to the workflow.
:::

**See also:** [Chapter 6](#ch6) for the caching these runs depend on, [Chapter 9](#ch9) for what happens after a green build, and [Chapter 12](#ch12) for gates that fail closed.
