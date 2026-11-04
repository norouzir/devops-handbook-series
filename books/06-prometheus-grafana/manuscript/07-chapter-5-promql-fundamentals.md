# Chapter 5 - PromQL Fundamentals {#ch5}

## 5.1 What a Query Returns: Vectors, Ranges, and Scalars

PromQL is a query language for the dimensional data model from [Chapter 2](#ch2), and its type system has exactly four kinds of values - learn them and the rest of the language is vocabulary. An **instant vector** is a set of series, each with one sample at one evaluation timestamp: `node_load1` returns an instant vector. A **range vector** is a set of series, each with a window of samples over time: `node_load1[5m]` returns five minutes of samples per series. A **scalar** is a single number, and a **string** is a literal.

The distinction matters because functions declare what they accept. `rate()` takes a range vector and returns an instant vector; `sum()` takes an instant vector and aggregates it; putting a range selector inside an arithmetic expression is a type error, and so is passing an instant vector where a range is required. Every "cannot use X here" error message you will ever see in the Prometheus UI reduces to confusing these types. Graphs are drawn from instant-vector expressions evaluated at successive steps across the time range - which is why a raw range selector like `up[5m]` graphs as "steps", not a line: it is a bundle of ranges, not a point per step.

## 5.2 Selectors and Matchers

A **selector** picks series by metric name and label matchers:

```promql
http_requests_total{job="api", method="GET", status=~"5.."}
```

Four matcher operators cover everything: `=` exact, `!=` negated exact, `=~` regex match, `!~` negated regex. Regexes are fully anchored (`5..` means exactly three characters starting with 5) and RE2 syntax - no backreferences, by design, because RE2's linear-time guarantee is what keeps adversarial labels from becoming a denial of service. The metric name itself is a matcher on `__name__`, so `http_requests_total` is sugar for `{__name__="http_requests_total"}` - and the long form is how you match many metrics at once: `{__name__=~"node_memory_.*_bytes"}`.

Three selector habits prevent a decade of confusion. First, `!~` and `!=` **do not match series missing the label**, only series carrying it with a non-matching value - to include label-less series you must select positively or use the `or` operator with a literal. Second, an empty matcher (`method=""`) selects series *missing* that label - the rare case where empty means absent. Third, narrowing beats widening: every matcher you add reduces both the data scanned and the aggregation you will undo later.

## 5.3 Rate, Increase, and the Counter Reset Problem

Counters from [Chapter 4](#ch4) are monotonically increasing *and they reset to zero on every process restart*, so the fundamental PromQL skill is converting raw counters into per-second reality. `rate()` does it:

```promql
rate(http_requests_total{job="api"}[5m])
```

`rate(x[5m])` takes the first and last samples in the five-minute window, divides the delta by the elapsed time, and - the part that matters - detects counter resets and corrects for them, stitching across restarts. Extrapolation at window edges makes results stable under scraping jitter. The companion functions: `increase()` multiplies rate by window length for human-facing "how many since Tuesday" answers; `irate()` uses only the last two samples for maximum responsiveness (good for momentary graphs, wrong for alerting, where a single jittery scrape should not flip a page); `delta()` and `idelta()` are their gauge-oriented cousins.

The one rule with teeth: **the range window should be at least four scrape intervals**. With 15-second scrapes, `rate(...[5m])` is the floor - a 1-minute window contains four samples, and a single failed scrape drops it to three, at which point rate extrapolates from thin data and graphs develop staircases. When someone's dashboard shows jagged rates, the window is the first suspect and the scrape interval the second.

::: {.warn}
**Watch out - rate() on gauges, and on the wrong series**

`rate(node_memory_MemAvailable_bytes[5m])` is a classic beginner query and it is meaningless: gauges can move any direction, and rate assumes monotonicity. Rate belongs on counters (`*_total`), `avg_over_time`/`max_over_time` on gauges. The `-total` suffix convention from [Chapter 4](#ch4) is what makes the difference visible in the query box.
:::

## 5.4 Aggregation: sum, by, without, and Friends

Aggregators collapse instant vectors across labels - this is where dimensional modeling pays off. The two forms are equivalent in expressive power and opposite in intent:

```promql
sum by (job) (rate(http_requests_total[5m]))       # keep job, drop everything else
sum without (instance) (rate(http_requests_total[5m]))  # drop instance, keep the rest
```

`by` enumerates what you want; `without` enumerates what you are discarding - and in production, `without (instance)` is usually the more future-proof form, because it preserves any label someone adds later. The full aggregator set: `sum` totals, `avg` means, `min`/`max` bounds, `count` counts series, `stddev`/`stdvar` spread, `topk(n, ...)` and `bottomk(n, ...)` select extremes (with the caveat that topk is per-instant, not per-window - a moving leaderboard, not a guarantee), `quantile(phi, ...)` aggregates *across series* (distinct from `histogram_quantile`, Chapter 6), `count_values` counts occurrences of a value, `group` emits 1 per group for existence checks.

Aggregation composes outward-in: the rate runs first, the sum collapses its result. `sum(rate(...))` and `rate(sum(...))` differ at counter resets and are not interchangeable - rate on raw counters, then aggregate, is the reliable order.

## 5.5 Binary Operators and Vector Matching

PromQL's arithmetic works element-wise between an instant vector and a scalar (`node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes`) or between two instant vectors - and vector-to-vector is where matching rules enter. By default, Prometheus matches series only when **all labels except the metric name** are identical; two series that differ in any label do not interact, and unmatched elements on the right side are silently dropped.

When default matching is wrong, you declare the match explicitly:

```promql
# per-endpoint error ratio: errors / total, matched on job+endpoint only
sum by (job, endpoint) (rate(http_requests_total{status=~"5.."}[5m]))
/
sum by (job, endpoint) (rate(http_requests_total[5m]))
```

`on (label, ...)` restricts matching to the listed labels; `ignoring (label, ...)` excludes them; `group_left`/`group_right` permit many-to-one matches (the "left" side may have multiple series per right-side element) - the canonical case being machine metrics joined with a low-cardinality lookup such as `label_replace` output or kube-state-metrics metadata. Comparison operators return series with values filtered to matching ones (`> 0.9` as a filter) unless `bool` is appended, which converts to 1/0 - the difference between "show me the outliers" and "paint everything that qualifies".

## 5.6 Reading Graphs: Windows, Steps, and Staleness

Every graph in the UI - and later in Grafana - is the same expression evaluated at `step` intervals across the chosen window, and three effects follow from that mechanical fact. Widening the time range with a fixed step count increases the step size, which smooths detail and can make a 30-second incident invisible; when a graph looks suspiciously calm, check the step before trusting it. Range selectors anchor to evaluation time, so `rate(...[5m])` at 12:00 uses 11:55-12:00 regardless of the graph's overall range. And **staleness** is a first-class state: when a series stops appearing in scrapes, its last sample stays queryable for five minutes and then vanishes - `up == 0` versus "series absent" is precisely the difference between a target that is down and a target that no longer exists, and dashboards should render the two differently.

::: {.note}
**Best practice - name the question before writing the query**

Every production PromQL query answers one operational question: who is slow, who is erroring, how full is the queue. Write the question as a comment above the query in your dashboard or runbook, keep the query the shortest expression that answers it, and prefer `without (instance)` aggregation so the query survives the next fleet resize. Queries that answer questions age well; queries that visualize data age badly.
:::

## 5.7 Lab 3 Preview and the Road to Chapter 6

Everything in this chapter composes into the RED pattern from [Chapter 1](#ch1): rate for traffic, a status-filtered ratio for errors, a histogram for duration. The queries are deliberately identical whether they land in the Prometheus UI, a Grafana panel, or an alert rule - one query language across all three surfaces is a large part of why the Prometheus stack compounds. [Lab 3](#lab3) drills exactly this composition; [Chapter 6](#ch6) adds the tools that make it scale: `histogram_quantile` for latency percentiles, the `_over_time` family, subqueries, label algebra, and recording rules that turn expensive queries into cheap stored series.

**See also:** [Chapter 6](#ch6) for percentiles, subqueries, and recording rules, [Chapter 9](#ch9) when these queries meet Grafana panels, and [Chapter 8](#ch8) when they meet alerting.
