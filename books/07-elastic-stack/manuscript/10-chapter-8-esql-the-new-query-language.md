# Chapter 8 - ES|QL: The New Query Language {#ch8}

## 8.1 Why a Second Language

The Query DSL is complete and machine-friendly, and nobody has ever called it pleasant to type under pressure. **ES|QL** - the Elasticsearch Query Language, generally available since 8.14 (June 2024) and maturing rapidly through 9.x - is Elastic's answer: a piped, human-first language where a query is a chain of transformations, each reading a table of results and emitting one, Unix-style:

```text
FROM logs-nginx-default
| WHERE http.response.status_code >= 500
| STATS errors = COUNT(*) BY service.name
| SORT errors DESC
| LIMIT 10
```

The same request as JSON DSL would be a twenty-line `bool` with a nested `terms` aggregation. ES|QL executes on a dedicated compute engine, not the DSL path - the engine processes data in blocks with columnar primitives, which is why the language is often *faster* than the equivalent DSL for analytics work, and why its capabilities grow independently. It is available everywhere the DSL is: the `_query` API, Kibana Discover, Lens, and alerting rules; Kibana autocompletes it, and Discover's mode switch between KQL and ES|QL is one click.

Two contract details matter before the first query. ES|QL is **table-oriented**: results are rows and columns (whatever fields the source index has, plus computed ones), not JSON documents with `_source`. And results are **capped** - the `LIMIT` default of 1000 and a hard maximum of 10,000 returned rows per request shape it as a *query* language, not an export language; exports keep using `search_after` ([Chapter 6](#ch6)) or async search.

## 8.2 The Pipes: FROM, WHERE, KEEP, SORT, LIMIT

Every query starts with a **source** command and refines through processing commands. **`FROM`** names an index, index pattern, or data stream - `FROM logs-*` is valid and common. **`WHERE`** filters rows with the boolean syntax of normal programming (`==`, `!=`, `>=`, `AND`/`OR`/`NOT`, `IN (...)`, `LIKE` with wildcards, `RLIKE` for regex):

```text
FROM logs-nginx-default
| WHERE @timestamp > NOW() - 1 hour
  AND http.response.status_code IN (500, 502, 503)
  AND url.path LIKE "/checkout*"
```

**`KEEP`** projects columns (the `_source` filtering of [Chapter 6](#ch6)); **`DROP`** removes them; **`SORT`** orders (with `NULLS LAST` and `DESC`); **`LIMIT`** caps rows. String literals use double quotes; identifiers with dots are used bare; timestamps compare naturally to `NOW() - 1 hour` arithmetic - small ergonomic decisions that make ES|QL read like the query you would have typed in a notebook.

```text
FROM logs-nginx-default
| WHERE http.response.status_code >= 400
| KEEP @timestamp, service.name, http.response.status_code, url.path, message
| SORT @timestamp ASC
| LIMIT 100
```

Time is first-class: every ES|QL query over time-series data implicitly uses the index's timestamp field, and `METADATA _id, _index, _timestamp` on the `FROM` line exposes internal fields when a query needs document identity (for example, to correlate a result row back to the stored document).

## 8.3 STATS, EVAL, and ENRICH

**`STATS`** is the aggregation engine - the whole of [Chapter 7](#ch7) in one command, with `BY` for grouping:

```text
FROM logs-nginx-default
| WHERE @timestamp > NOW() - 24 hours
| STATS
    requests  = COUNT(*),
    errors    = COUNT(*) WHERE http.response.status_code >= 500,
    p95_ms    = PERCENTILE(url.request_duration_ms, 95),
    clients   = COUNT_DISTINCT(client.ip)
  BY service.name
| SORT errors DESC
```

Conditional aggregation inside `STATS` (`COUNT(*) WHERE ...`) replaces the DSL's filter-in-aggregation nesting; grouping is a comma-separated list; and the metric vocabulary - `AVG`, `MIN`, `MAX`, `SUM`, `MEDIAN`, `PERCENTILE`, `COUNT_DISTINCT`, `TOP` for most-frequent values - covers the daily-use set of [Chapter 7](#ch7). Bucket-by-time is a named function: `STATS errors = COUNT(*) BY bucket(@timestamp, 5 minutes)` produces the date-histogram series, ready for a Lens chart.

**`EVAL`** computes new columns from existing ones - unit conversions, string surgery, categorization - inline in the chain:

```text
FROM logs-nginx-default
| EVAL duration_s = url.request_duration_ms / 1000.0,
       tier = CASE(
                http.response.status_code >= 500, "severe",
                http.response.status_code >= 400, "client-issue",
                "ok")
| KEEP @timestamp, url.path, duration_s, tier
```

**`ENRICH`** joins reference data at query time: a policy (defined once with `PUT _enrich/policy`) declares a match field and target index - "attach the `team` and `service_tier` from the services catalog onto every row by `service.name`" - and any query can then use `| ENRICH services-policy`. It is a lookup join against a slowly-changing reference table, which covers the majority of real "JOIN" needs in observability data; full SQL-style joins are not the design goal, and data is still best denormalized at ingest when the relationship is known in advance.

## 8.4 ES|QL for Log Triage: A Worked Investigation

The language earns its keep in the first ten minutes of an incident, when questions arrive faster than JSON can be written. One chain, five refinements, reading like the investigation itself:

```text
// 1. What failed in the last hour, at a glance?
FROM logs-*
| WHERE @timestamp > NOW() - 1 hour AND http.response.status_code >= 500
| STATS count = COUNT(*) BY service.name, url.path
| SORT count DESC
| LIMIT 20

// 2. Is it getting worse right now? Five-minute buckets.
FROM logs-*
| WHERE http.response.status_code >= 500
| STATS errors = COUNT(*) BY bucket(@timestamp, 5 minutes), service.name
| SORT bucket(@timestamp) DESC

// 3. Which clients are hammering the failing endpoint?
FROM logs-*
| WHERE url.path == "/checkout/payment" AND http.response.status_code >= 500
| STATS hits = COUNT(*) BY client.ip
| SORT hits DESC
| LIMIT 10

// 4. What did the failing requests actually say?
FROM logs-*
| WHERE url.path == "/checkout/payment" AND http.response.status_code >= 500
| KEEP @timestamp, message, error.stack_trace
| SORT @timestamp DESC
| LIMIT 50

// 5. Dissect the message text itself.
FROM logs-*
| WHERE message LIKE "*gateway*timeout*"
| EVAL cause = SPLIT(message, " ")[2]
| STATS count = COUNT(*) BY cause
```

Every stage is a small edit of the previous one - add a filter, change a bucket, project different columns - and Kibana's ES|QL editor keeps history and autocomplete under your fingers. This interactive refinement loop, more than any single feature, is why triage sessions moved to ES|QL.

## 8.5 Choosing Between ES|QL and the Query DSL

The two languages coexist by design, and the choice is now a simple decision table:

| Situation | Reach for |
|---|---|
| Ad-hoc analysis, triage, interactive dashboards | ES|QL |
| Time-boxed queries inside alerting rules and ML jobs | ES|QL (supported natively) |
| Application code with deep customization of scoring | Query DSL |
| Features not yet in ES|QL (some niche query types) | Query DSL |
| Existing tooling, saved objects, integrations | whatever they already speak (usually DSL) |

::: {.note}
**Best practice - learn both, write ES|QL first**

The DSL remains the substrate: every dashboard widget, integration, and library ultimately issues DSL, so reading it stays a core skill ([Chapter 6](#ch6), [Chapter 7](#ch7)). But for questions *you* type, ES|QL is faster to write, easier to review in a runbook, and increasingly the surface Elastic optimizes first. The bilingual operator is the efficient one.
:::

**See also:** [Chapter 9](#ch9) puts these queries on dashboards, and [Chapter 14](#ch14) turns an ES|QL query into an alert rule.
