# Chapter 7 - Aggregations: Analytics with Elasticsearch {#ch7}

## 7.1 Buckets and Metrics

Search returns documents; aggregations return *answers*. The aggregation framework computes statistics - counts, averages, percentiles, top lists, time series - over the documents a query selects, inside the engine, in one request. The mental model has two kinds of blocks, and every analysis you will ever build is some composition of them. **Bucket** aggregations group documents: by field value, by time interval, by numeric range - each document lands in zero or more buckets. **Metric** aggregations compute over the documents *inside* a bucket: count, average, max, percentile. Buckets nest, metrics attach at any level, and the request is a tree:

```text
GET logs-nginx-default/_search
{
  "size": 0,
  "query": {
    "range": { "@timestamp": { "gte": "now-24h" } }
  },
  "aggs": {
    "per_status": {
      "terms": { "field": "http.response.status_code", "size": 10 },
      "aggs": {
        "avg_duration": { "avg": { "field": "url.request_duration_ms" } }
      }
    }
  }
}
```

Read it as the question it encodes - "in the last 24 hours, how many requests hit each status code, and what was the average duration inside each?" Three conventions appear here that hold for the whole chapter. `"size": 0` says *no hits, just aggregations* - every analytics request starts with it. `aggs` is shorthand for `aggregations`. The response mirrors the request as a tree of `buckets`, which is why dashboards consume aggregations directly ([Chapter 9](#ch9)).

## 7.2 Metric Aggregations

The metric family covers the statistics of a numerical field, and four of them do most operational work. **`avg`**, **`sum`**, **`min`**, **`max`** need no introduction; **`stats`** returns all four plus `count` in one call, and **`extended_stats`** adds variance and standard deviation. **`cardinality`** counts *distinct* values - the number of unique clients, services, or endpoints - and is the aggregation with a footnote: it is approximate, computed by the HyperLogLog++ algorithm, configurable via `precision_threshold` (up to 40,000 with near-exact accuracy at higher memory). Approximate counts over billions of values in milliseconds is a bargain, but dashboards that must show exact uniques need to say so.

**`percentiles`** answers the latency question that averages hide - *what does the slow tail look like?*:

```text
"latency": {
  "percentiles": {
    "field": "url.request_duration_ms",
    "percents": [50, 90, 95, 99]
  }
}
```

The 99th percentile is the number users feel and the median hides, and it is the reason percentile aggregation is a permanent fixture of every latency dashboard this series has drawn. Percentile *ranks* (`percentile_ranks`) invert the question - "what fraction of requests finish under 300 ms?" - and both run from the same data structures.

## 7.3 Bucket Aggregations {#ch7-buckets}

**`terms`** buckets by field value and returns the top N - the "breakdown by" of every investigation: by status code, by service, by client IP. Its `size` parameter (default 10) is a contract with your users, and its ordering (`order: { "_key": "asc" }` for keys, a sub-metric for "worst first") shapes the story the buckets tell. **`date_histogram`** buckets by time interval and is the backbone of every time-series panel:

```text
"errors_over_time": {
  "date_histogram": {
    "field": "@timestamp",
    "fixed_interval": "5m",
    "min_doc_count": 0
  },
  "aggs": {
    "error_count": { "filter": { "term": { "level": "error" } } }
  }
}
```

`fixed_interval` (seconds, minutes, hours - uniform buckets) versus `calendar_interval` (days, weeks, months - calendar-aware) is a distinction with production consequences: calendar intervals respect daylight saving and month lengths, which is what you want for "daily report" charts. `min_doc_count: 0` emits empty buckets so time charts do not collapse quiet periods - the single most common "why does my graph lie?" fix.

**`range`** and **`date_range`** bucket by explicit boundaries (latency `< 100ms`, `100-500ms`, `> 500ms` - the SLO buckets), **`filters`** buckets by named arbitrary queries (one bucket per team's services, one for cache hits, one for misses), **`histogram`** buckets numerics by fixed step, and **`missing`** catches documents where a field is absent - the honest bucket every real dataset eventually needs.

## 7.4 Composing: The Tree Is the Query {#ch7-composing}

The framework's real power is composition - buckets inside buckets inside metrics - and the response echoes the nesting, which dashboards and scripts walk mechanically. Three patterns cover most production analytics.

**Breakdown over time:** date_histogram with a terms sub-aggregation - "errors per minute, per service" is one request, not a script:

```text
"errors_per_service": {
  "date_histogram": { "field": "@timestamp", "calendar_interval": "1h", "min_doc_count": 0 },
  "aggs": {
    "by_service": { "terms": { "field": "service", "size": 5 } }
  }
}
```

**Worst-first drill-down:** terms ordered by a sub-metric - top ten endpoints by their 99th-percentile latency, which is the list an engineering manager actually wants on Monday:

```text
"by_path": {
  "terms": {
    "field": "url.path", "size": 10,
    "order": { "p99_latency": "desc" }
  },
  "aggs": {
    "p99_latency": {
      "percentiles": { "field": "url.request_duration_ms", "percents": [99] }
    }
  }
}
```

**Funnel-to-answer:** filters bucket (segments) with metrics inside each segment - conversion by client type, error ratio by deployment marker. And when a computation must happen *across* buckets - a cumulative sum, a moving average, a derivative - **pipeline aggregations** operate on the results of sibling aggregations (`derivative`, `cumulative_sum`, `moving_fn`, `bucket_script`), one level up in the same tree.

::: {.note}
**Best practice - aggregate on keywords and numbers, not on text**

Aggregations run on the exact terms of a field: keyword fields and numerics aggregate natively; `text` fields need the `.keyword` sub-field (`service.keyword`) and pay an extra indirection for it. Design mappings ([Chapter 5](#ch5)) so that every field you will aggregate is a `keyword` or numeric type, and the dashboards of [Chapter 9](#ch9) never meet a "field is not aggregatable" error.
:::

## 7.5 What It Costs and Where ES|QL Fits

Aggregations are computed at query time over `doc_values` - the columnar, disk-based, read-optimized encoding of every numeric and keyword field (the same structure that powers sorting). No pre-aggregation step exists in vanilla Elasticsearch: freshness is instant, and cost is per query, which is why two disciplines keep it cheap. Keep buckets honest - a `terms` on a high-cardinality field with `size: 1000` builds a thousand buckets per shard per request, and a date_histogram at one-second intervals over a year is a denial-of-service against yourself. And prefer counting to listing - `"size": 0` requests skip scoring and fetching entirely, which is why a well-shaped aggregation on a billion documents routinely beats a page of hits on a million.

The patterns this chapter wrote in JSON are exactly the queries ES|QL ([Chapter 8](#ch8)) writes in four lines of pipes - `FROM ... | WHERE ... | STATS ... BY ...` - and increasingly that is how ad-hoc analysis is written by hand. The DSL remains the language of the API surface everything else speaks: dashboards, saved searches, alerting rules, and integrations all compile down to these trees, so the JSON vocabulary stays in your hands even after your fingers learn the pipes.

**See also:** [Chapter 8](#ch8) rewrites this chapter's queries in pipe syntax, [Chapter 9](#ch9) wires them into dashboards, and [Chapter 11](#ch11) explains what makes aggregations fast or slow at cluster scale.
