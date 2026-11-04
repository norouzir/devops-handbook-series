# Chapter 6 - Advanced PromQL: Histograms, Recording Rules, and Subqueries {#ch6}

## 6.1 Latency Percentiles with histogram_quantile

The histogram instrumentation from [Chapter 4](#ch4) exposes three series families per metric - `_bucket{le="..."}`, `_sum`, `_count` - and `histogram_quantile()` is what turns them into the latency numbers humans reason about:

```promql
histogram_quantile(0.95,
  sum by (job, le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
```

Read it as an onion. The innermost `rate` converts bucket counters into per-second observation rates (counter resets absorbed). `sum by (job, le)` aggregates across instances *and across endpoint labels*, keeping only `le` - the quantile boundary - alongside the grouping labels. `histogram_quantile(0.95, ...)` interpolates within the cumulative buckets to estimate the value below which 95 percent of observations fall. Get the grouping right and the query answers "how slow is the service, worst-case-normal"; drop `le` from the `by` clause and the query collapses all buckets into one and returns nonsense.

Three properties make histograms the default choice despite their series cost (one series per bucket per label combination). They **aggregate before quantile computation** - a fleet-wide p95 is legitimate, which is not true of client-computed summaries. They **let you add buckets later** - retuning precision does not require a deploy. And they compose with arithmetic: `rate(_sum[5m]) / rate(_count[5m])` is the average duration, bucket ratios are the fraction of requests above any threshold, and both are cheaper than quantiles for dashboards that refresh every few seconds.

::: {.warn}
**Watch out - percentiles are estimates, and p99 is a liar**

With buckets ending at 0.1s and 0.5s, a true p99 of 0.11s is reported anywhere in (0.1, 0.5] depending on interpolation - keep buckets dense near your SLO threshold. And because p99 is computed from a *window*, a single slow request in a low-traffic endpoint dominates it: on sparse series, alert on error ratios and saturation instead of long-tail percentiles, or you will page on noise.
:::

## 6.2 The _over_time Family and Subqueries

Range-vector functions beyond `rate` answer questions about gauges and about time itself. The `_over_time` family takes a range vector and reduces each series to one instant value: `avg_over_time`, `min_over_time`, `max_over_time`, `sum_over_time`, `count_over_time`, `quantile_over_time`, `stddev_over_time`, `last_over_time`, `present_over_time`, `absent_over_time`. Typical uses: `max_over_time(node_memory_MemAvailable_bytes[1h])` for the worst memory moment of the last hour, `avg_over_time(...[1h])` to compare against a current reading for trend, `count_over_time(up[1h])` versus `count_over_time(up[1h] == 1)` for scrape reliability.

A **subquery** manufactures a range vector from an instant-vector expression, with its own resolution:

```promql
max_over_time(
  sum by (instance) (rate(node_cpu_seconds_total{mode!="idle"}[5m]))[1h:1m]
)
```

The `[1h:1m]` suffix reads "evaluate the inner expression every 1 minute, over the last 1 hour" - instant access to "peak busy-ness of the hour" without recording rules. Subqueries are the right tool for ad-hoc exploration and Grafana panels; they are the wrong tool for expensive inner expressions evaluated fleet-wide on every dashboard refresh, because each evaluation recomputes the inner query at every step. When a subquery lands in a dashboard or an alert and the query is heavier than a few hundred series, it is asking to become a recording rule - which is the next section's subject.

Two more temporal tools finish the kit: `offset 1w` shifts evaluation into the past for week-over-week comparison (`sum(rate(http_requests_total[1h])) offset 1w`), and the `@` modifier pins a query element to an absolute timestamp - niche in dashboards, decisive in postmortems ("what did the world look like *at* 03:14?").

## 6.3 Label Algebra: label_replace and label_join

Aggregation needs labels to *agree* before it can collapse them, and two functions rewrite labels at query time. `label_replace(v, dst, replacement, src, regex)` copies a (transformed) capture group from one label into another - creating the label if needed:

```promql
# derive a "mount" label from the device path
label_replace(
  rate(node_disk_read_bytes_total[5m]),
  "mount", "$1", "device", "/dev/(.*)"
)
```

`label_join(v, dst, separator, src...)` concatenates several labels into one. Their production uses are narrower than they look but decisive when they appear: normalizing labels from two exporters that name the same thing differently, deriving a service label from a pod label before joining with `group_left` ([Chapter 5](#ch5)), and the classic join pattern - matching app metrics with machine metrics by constructing a shared key. At write time, the same job belongs to `metric_relabel_configs` ([Chapter 7](#ch7)); query-time label algebra is for the cases you did not anticipate at write time.

## 6.4 Absence, Prediction, and the Edges

Two functions cover the failure modes that arithmetic cannot see. `absent(http_requests_total{job="api"})` returns a single synthetic series with value 1 *only when the selector matches nothing* - the alertable form of "this metric stopped existing", which is different from "this metric is zero" and from "this target is down" (`up == 0`). The absence case covers agents that died before exporting anything, jobs deleted from configuration, and exporters that dropped a metric in an upgrade. `absent_over_time(...[30m])` gives the time-buffered version. Prediction rounds out the set: `predict_linear(node_filesystem_avail_bytes{mountpoint="/"}[6h], 24 * 3600)` extrapolates a gauge linearly over the next 24 hours - the standard "disk fills on Thursday" alert - with the honest caveat that linear prediction of a non-linear system is a heuristic, best paired with `for:` clauses and human review rather than treated as an oracle.

## 6.5 Recording Rules: Precompute, Store, Reuse

A **recording rule** evaluates a PromQL expression on a schedule and stores the result as a new time series. Everything expensive in this chapter - aggregated rates, histogram quantiles, subqueries - becomes a stored, indexed, cheap-to-read series:

```yaml
groups:
  - name: api-red
    interval: 30s
    rules:
      - record: job:http_requests:rate5m
        expr: sum by (job) (rate(http_requests_total[5m]))

      - record: job:http_errors:ratio_rate5m
        expr: |
          sum by (job) (rate(http_requests_total{status=~"5.."}[5m]))
          /
          sum by (job) (rate(http_requests_total[5m]))

      - record: job:http_request_duration_seconds:p95_rate5m
        expr: |
          histogram_quantile(0.95,
            sum by (job, le) (rate(http_request_duration_seconds_bucket[5m])))
```

The naming convention is load-bearing and worth adopting verbatim: `level:metric:operations`, colon-delimited, aggregations listed at the same level they are applied at. `job:http_errors:ratio_rate5m` tells a reader in one glance: per-job error ratio, computed from a 5-minute rate. Recording rules live in rule files loaded via `rule_files`, checked with `promtool check rules`, visible (and historically graphable) in the UI's Rules page. Two operational notes: recorded series consume TSDB space like any other series - the cardinality budget includes them - and the evaluation interval (30s above) sets the data's granularity; a dashboard panel reading a 30s recording rule cannot show 5s detail, by design.

::: {.note}
**Best practice - a recording rule for every repeated query**

The rule of thumb that keeps query load sane: if the same expression appears in two dashboards, or in a dashboard and an alert, it becomes a recording rule. Alerts then fire off precomputed series (`job:http_errors:ratio_rate5m > 0.01`), which makes alert evaluation cheap and predictable - a property [Chapter 8](#ch8) leans on for burn-rate alerting.
:::

## 6.6 Query Performance and Cardinality Discipline

PromQL performance problems are almost always cardinality problems wearing a disguise, and the diagnostic sequence is fixed. The TSDB status page (Head stats, Top series count by metric names) identifies the expensive metric. The query planner's own signals - query duration, and the `count()` of any selector - size the blast radius: `count(http_requests_total)` tells you how many series the query touches before you aggregate them. The patterns that keep queries fast: aggregate early (`sum by (job)` before further arithmetic), avoid unanchored regex matchers on high-cardinality labels (`status=~".*"` matches everything and scans nothing less), prefer recording rules for anything computed per refresh across large label spaces, and cap dashboards' time ranges rather than letting a curious stakeholder graph a year of per-second data. When a query is slow in Grafana but fast in the Prometheus UI, suspect the panel's refresh rate before the query - [Chapter 10](#ch10) covers the dashboard-side controls (max data points, interval variables) that complete this picture.

## 6.7 Lab 3: PromQL Drill with Recording Rules

::: {.lab}
### Lab 3 - From raw counters to a served RED dashboard {#lab3}

1. Using the Chapter 4 instrumented service plus node_exporter, write the three RED queries for the app: request rate per endpoint, error ratio per endpoint (`5xx / total`), and p95 latency via `histogram_quantile`. Verify each in the UI's Table view, then graph for 1 hour.
2. Aggregate the rate query two ways - `by (endpoint)` and `without (instance)` - and add a second app replica to the Compose stack. Confirm both aggregations still return one series per endpoint, and explain in a comment why `without` survives future label additions.
3. Deliberately reduce a `rate()` window below four scrape intervals (`[15s]`, `[30s]`) and observe the staircase artifacts in the graph; restore `[5m]`. Record the rule you will enforce for your team.
4. Convert all three RED queries into recording rules in `rules/api-red.yml` following the `level:metric:operations` convention, wire the file into `rule_files`, validate with `promtool check config`, reload, and confirm the new series appear (query them by name in the UI).
5. Write and verify the edge-case queries: `absent()` for the app metric, `predict_linear` on the root filesystem, and a subquery for peak CPU over the last hour at 1-minute resolution. Note which of the three you would turn into a recording rule and why.
6. Compare query timings: run the raw p95 query and its recorded series back to back in the UI, several times, and note the difference. This number is the entire economic argument for recording rules.
:::

**See also:** [Chapter 7](#ch7) for controlling what enters the TSDB that these rules read, [Chapter 8](#ch8) which alerts on the recorded ratios, and [Chapter 10](#ch10) where the recorded series become dashboard panels.
