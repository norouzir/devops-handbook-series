# Chapter 6 - The Query DSL {#ch6}

## 6.1 Two Contexts: Query and Filter

The Query DSL is Elasticsearch's JSON query language, and its first principle is a division into two *contexts*. In the **query context** (`query: { ... }`), the engine asks *how well does this document match* and computes a relevance score `_score` - BM25 over the inverted index, as introduced in [Chapter 1](#ch1). In the **filter context** (`filter: { ... }`), the engine asks only *does this document match* - yes or no, no score. Filters are cheaper, and because their answers are independent of document order they are cached aggressively by the node.

The practical rule is mechanical, not philosophical: full-text conditions - which words appear in a message - go in `query`; everything else - status codes, time ranges, host names, existence - goes in `filter`. A realistic search is mostly filter with one query clause supplying relevance:

```text
GET logs-app/_search
{
  "query": {
    "bool": {
      "must":     [ { "match": { "message": "payment timeout" } } ],
      "filter":   [
        { "term":  { "level": "error" } },
        { "range": { "@timestamp": { "gte": "now-1h" } } }
      ]
    }
  }
}
```

Every example in this chapter runs against the Chapter 4 data stream or any index with `message` (text), `level` and `service` (keyword), `@timestamp` (date), and `http.response.status_code` (integer) - adjust names to your data.

## 6.2 Leaf Queries: The Building Blocks

**`match`** is the full-text workhorse. It analyzes the search string with the field's analyzer, then ORs (by default) the resulting terms:

```text
GET logs-app/_search
{ "query": { "match": { "message": { "query": "payment timeout", "operator": "and" } } } }
```

The `operator: and` variant requires all terms - "payment AND timeout" - and is the first knob to reach for when matches are too loose. **`match_phrase`** requires the terms in order, as a unit: `"payment gateway timeout"` matches the phrase, not the three words scattered. **`term`** matches a single exact term - the keyword field's query; on a `text` field it is almost always a bug (the term `Error` does not match the indexed token `error`), on a `keyword` field it is exact and fast. **`terms`** is the multi-value form, **`ids`** fetches by document id, **`exists`** asks whether the field is present at all - the query for "show me requests that logged *no* trace id." **`range`** covers numbers, dates, and IPs with `gte`/`gt`/`lte`/`lt` and a rich date-math dialect (`now-1h`, `now-1d/d` for day rounding); on `ip` fields it accepts CIDR notation: `{ "term": { "client.ip": "10.0.0.0/8" } }`.

Two shape differences between these queries matter more than their names suggest. `term` on a keyword field compares one immutable term - predictable. `match` on a text field runs the analyzer - flexible but fuzzy. When a search surprises you, the first question is always: *which context did the value go through - analyzer or verbatim?* [Chapter 5](#ch5)'s `_analyze` API answers it in one call.

## 6.3 Compound Queries: `bool`

**`bool`** combines clauses four ways: `must` (scored AND), `filter` (unscored AND, cached), `should` (scored OR - and when there is no `must`, at least one by default), `must_not` (unscored NOT, filter context). Nesting is unlimited, which turns `bool` into the grammar of real searches:

```text
GET logs-app/_search
{
  "query": {
    "bool": {
      "must_not": [ { "term": { "service": "healthcheck" } } ],
      "filter": [
        { "range": { "@timestamp": { "gte": "now-24h" } } },
        { "terms": { "http.response.status_code": [500, 502, 503] } }
      ],
      "should": [
        { "match": { "message": "timeout" } },
        { "match": { "message": "circuit breaker" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

This one query - exclude healthcheck noise, keep the last day's 5xx, require at least one of two symptoms in the message - is the shape of a real incident triage search, and it reads top-to-bottom almost like the sentence that motivated it. With `must` present, `minimum_should_match` defaults to 0 (should becomes a scoring boost); set it explicitly whenever shoulds are requirements rather than preferences.

## 6.4 Full-Text Mechanics: Fuzziness and Highlighting

Two capabilities make text search forgiving in the way operators need at 3 a.m. **Fuzziness** tolerates typos through edit distance: `{ "match": { "message": { "query": "payemnt timeout", "fuzziness": "AUTO" } } }` finds *payment*. **Highlighting** returns the matching fragments with markup, which is what turns a hit list into evidence:

```text
GET logs-app/_search
{
  "query": { "match_phrase": { "message": "gateway timeout" } },
  "highlight": {
    "fields": { "message": { "number_of_fragments": 2 } },
    "pre_tags": ["[b]"], "post_tags": ["[/b]"]
  }
}
```

Each hit then carries a `highlight` block - the two most relevant fragments of `message` around the phrase, bracketed. In Kibana's Discover this is automatic; in APIs and export scripts it is the difference between results and answers.

## 6.5 Sorting, Pagination, and What Comes Back

By default results arrive by `_score` descending, ten at a time, with `_source`. Three controls adjust the contract. **`from`/`size`** paginate - with a hard ceiling (`index.max_result_window`, default 10,000) that is not a database LIMIT: deep pagination makes every shard produce `from + size` results to be merged. For deep scans - exports, "give me everything from yesterday" - the correct tool is **`search_after`** with a sort tiebreak (`@timestamp`, then `_id`), a cursor that scales to millions. **`sort`** reorders - timestamp ascending for log reading, a field descending for "worst first" - and when you sort, you usually stop caring about `_score`, which is the signal that the whole query belongs in `filter` context. **`_source`** filtering trims the payload: `"_source": ["@timestamp", "service", "message"]` keeps export jobs and dashboards honest about what they actually use.

```text
GET logs-app/_search
{
  "size": 100,
  "sort": [ { "@timestamp": "asc" }, { "_id": "asc" } ],
  "_source": ["@timestamp", "service", "level", "message"],
  "query": { "bool": { "filter": [
    { "range": { "@timestamp": { "gte": "now-6h" } } },
    { "term": { "level": "error" } }
  ] } }
}
```

::: {.note}
**Best practice - count cheaply, search specifically**

`GET logs-app/_count` with a filter returns just the number - the query behind "how many 500s in the last hour" needs no hits, no scores, no `_source`. Reserve `_search` for when the documents themselves are the answer; run counts for thresholds, trends, and alert rules ([Chapter 14](#ch14)). The same query in both shapes differs in cost by an order of magnitude on large indices.
:::

## 6.6 Lab 3: Build a Structured Log Search

::: {.lab}
### Lab 3 - From question to query, on your own data {#lab3}

1. Take the Chapter 4 stack with its Nginx documents (rerun the traffic generator for a few hundred lines). Confirm the parsed fields exist: `GET logs-nginx-default/_mapping` (or your index name from Lab 2).
2. Warm-up: find every request with status 500 using a filter-context `term` on the status field; note there is no meaningful `_score` - say why, out loud, to yourself.
3. Text layer: search `url.path` for the checkout path with `match_phrase`, then with `term` on the same field - one returns hits, the other (probably) none. Explain with `_analyze` before looking at the mapping.
4. Compound: build the real triage query - last 6 hours (`range` on `@timestamp`), status in `[404, 500, 502, 503]` (`terms`), excluding static assets by prefix (`bool.must_not` with `prefix` on `url.path`), sorted `@timestamp` ascending, `_source` trimmed to timestamp, method, path, status.
5. Add highlighting on any text field you search with `match` and confirm the fragments come back.
6. Count twice: the same filter as a `_count` query and as a `_search` with `"size": 0` - verify the numbers agree, and note which one you would hang an alert on.
7. Deep-read exercise: paginate through all of today's errors with `search_after` (sort on `@timestamp, _id`), three pages of 100, verifying the cursor advances past the previous page's last sort value.

Deliverable: a saved query file with the triage query from step 4 - this becomes the basis of the alert rule in [Chapter 14](#ch14) and the dashboard in [Lab 4](#lab4).
:::

**See also:** [Chapter 7](#ch7) aggregates instead of listing, and [Chapter 8](#ch8) expresses this chapter in five lines of pipe syntax.
