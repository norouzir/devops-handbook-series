# Chapter 5 - Mapping and Analysis {#ch5}

## 5.1 What Happens When You Index a Document

Two independent transformations turn a JSON document into searchable data, and confusing them is the most common beginner error in Elasticsearch. **Mapping** is the schema: a per-index definition of every field's type - is `status` an integer, is `title` searchable text - which decides how each field is stored and indexed. **Analysis** is the text pipeline: how a string is chopped into the *terms* that the inverted index actually contains. Mapping decides *what kind* of question a field can answer; analysis decides *which documents match* when you ask it. The `match` query of [Chapter 3](#ch3) that found *Book* in a title about books was analysis at work; the fact that `status: 500` filters numerically was mapping at work.

If you create an index with no mapping, Elasticsearch guesses. **Dynamic mapping** inspects the first document that mentions a field and picks a type: strings become `text` with a `.keyword` sub-field, numbers become the smallest fitting numeric type, dates that look like dates become `date`. For a sandbox this is magical; for production log data it is a slow leak - every unique string a shipper might emit can become a new field, and the mapping can only grow.

::: {.warn}
**Watch out - mapping explosions are forever**

A malformed shipper that emits `{"level_500": "on"}` style keys, or user-generated data indexed into dynamic fields, can add thousands of fields to a mapping. Mappings cannot delete or retype fields - only new indices get new mappings - so the fix is always a reindex ([Chapter 10](#ch10) shows the modern lifecycle answer). Guard rails exist: `index.mapping.total_fields.limit` (default 1000) and the `dynamic: strict` mode that rejects unknown fields outright. Set both deliberately on production indices.
:::

## 5.2 Field Types: Text, Keyword, and the Rest

The type system divides into families, and three of them do almost all the work in an observability context.

**`text`** fields are analyzed: the string is tokenized, lowercased, stemmed (depending on the analyzer), and indexed as terms. Text fields answer *which documents contain words close to this phrase* - the `match` family of queries. They are not usable for exact matching, sorting, or aggregations.

**`keyword`** fields are indexed verbatim as a single term. They answer *is this value exactly X* - `term` queries - and they are the fields you sort by, aggregate into buckets, and filter on. The auto-generated `.keyword` sub-field on dynamically mapped strings exists precisely so one field can do both jobs:

```text
PUT logs-app/_mapping
{
  "properties": {
    "message":      { "type": "text" },
    "service": {
      "type": "text",
      "fields": { "raw": { "type": "keyword" } }
    },
    "level":        { "type": "keyword" },
    "status":       { "type": "integer" },
    "duration_ms":  { "type": "float" },
    "@timestamp":   { "type": "date" },
    "client.ip":    { "type": "ip" },
    "error.stack":  { "type": "text" }
  }
}
```

The rest of the type system is worth recognizing on sight. **Numeric** types (`long`, `integer`, `short`, `byte`, `double`, `float`, and the space-efficient `scaled_float`) behave like databases expect. **`date`** accepts ISO-8601 strings and epoch millis and is the field every time-based dashboard, retention policy, and ES|QL query keys on - conventionally `@timestamp`. **`ip`** holds IPv4 and IPv6 with efficient range queries (the CIDR filter in [Chapter 6](#ch6) uses it). **`boolean`**, **arrays** (any field may hold many values - no separate type needed), and two structured types complete the picture: **`object`** (nested JSON flattened into dotted fields) and **`nested`** (arrays of objects kept queryable as units - needed when an array of objects would otherwise have its fields matched across elements). Finally, since 9.x, **`dense_vector`** fields hold embeddings for semantic and hybrid search, with BBQ quantization applied by default to new fields ([Chapter 1](#ch1)).

## 5.3 Analyzers: From String to Terms

The analyzer pipeline has three stages, and the standard installation covers most needs once you can name them. A **char filter** first transforms the raw string (stripping HTML, remapping characters). A **tokenizer** then splits text into tokens - the `standard` tokenizer on Unicode word boundaries; `whitespace`, `keyword` (no split at all), and pattern tokenizers for special cases. **Token filters** then process each token: lowercase, stop-word removal, and stemming, which reduces *running* and *ran* to a common root.

Which pipeline runs is decided by the field's `analyzer` (at index time) and optionally `search_analyzer` (at query time). The `standard` analyzer is the default and does the right thing for most prose. Log messages, though, are not prose: they are full of punctuation, identifiers, and versions. The English-language analyzer earns its keep on human text; exact codes deserve exact treatment:

```text
GET _analyze
{ "analyzer": "standard", "text": "payment gateway timeout after 3000ms" }

GET _analyze
{ "analyzer": "english", "text": "connections refused by gateway" }

GET _analyze
{ "analyzer": "keyword", "text": "svc-checkout-v3" }
```

Run the three and compare the token lists - the fastest way to build the intuition that later explains every puzzling search result. The `_analyze` API accepts custom analyzer compositions too, which is how custom analyzers are debugged before being committed to a mapping.

::: {.note}
**Best practice - analyzer decisions are query decisions**

A field analyzed with the `english` stemmer will match *connection* against *connections* - usually desirable for logs and documentation. The same field can no longer be `term`-filtered exactly. Choose per field, document the choice in the mapping (analyzer names are right there), and remember the asymmetry: changing an analyzer requires reindexing, so deciding deliberately on day one is cheaper than migrating on day three hundred.
:::

## 5.4 Index Templates: Mapping Before the First Document

Production indices are never created implicitly; they arrive through **index templates** - named definitions that apply settings, mappings, and lifecycle hooks whenever an index (or data stream, [Chapter 10](#ch10)) matching a pattern is created. Templates compose from reusable **component templates**, which is how teams share one mappings component across many index families:

```text
PUT _component_template/logs-mappings
{
  "template": {
    "settings": { "number_of_shards": 1, "number_of_replicas": 1 },
    "mappings": {
      "dynamic": "strict",
      "properties": {
        "@timestamp": { "type": "date" },
        "service":    { "type": "keyword" },
        "level":      { "type": "keyword" },
        "message":    { "type": "text" },
        "duration_ms": { "type": "float" }
      }
    }
  }
}

PUT _index_template/logs-app
{
  "index_patterns": ["logs-app-*"],
  "data_stream": {},
  "composed_of": ["logs-mappings"],
  "priority": 200
}
```

Three settings in this block carry most of the production weight. `dynamic: strict` rejects unknown fields loudly instead of absorbing them silently - the mapping-explosion guard of Section 5.1 made policy. `number_of_shards: 1` for a data stream that will roll over by size ([Chapter 10](#ch10)) rather than grow forever - the shard-count decision of [Chapter 2](#ch2) deferred to rollover. And `priority` resolves the case where several patterns match one index name; higher wins, and unexplained template surprises usually mean two patterns matched.

## 5.5 The Elastic Common Schema in Practice

The mapping in Section 5.4 quietly used field names from the **Elastic Common Schema (ECS)** - `@timestamp`, `service`, `client.ip`, `http.response.status_code` - the naming convention that lets a dashboard built for one shipper work for another. You met ECS fields in the Chapter 4 pipeline; the mapping chapter is where the habit becomes policy: when you design your own mappings, keep to ECS names where a field exists (`url.path` not `path`, `error.message` not `err_msg`), add custom fields under your own namespace when it does not, and let the shared vocabulary pay off in Kibana, where visualizations, saved queries, and detection rules all assume it. The full catalog lives at the ECS documentation; the working subset for logs - service, event, http, url, client/server, error - fits on a page and covers the vast majority of fields this book's examples use.

## 5.6 Inspecting What You Got

Two read-only APIs close the loop, and both belong in the debugging reflex list. `GET logs-app/_mapping` shows the live mapping - the ground truth for "why does `term` not match this field," answered in one look at whether the field is `text`. `GET logs-app/_settings?filter_path=*.analysis` shows the index's analyzer definitions. And when a document misbehaves, `GET logs-app/_doc/<id>` returns `_source` (what you sent) next to the stored fields (what was indexed) - the pair that usually explains the difference between what you wrote and what you can find.

**See also:** [Chapter 6](#ch6) puts these fields to work in queries, [Chapter 10](#ch10) shows how templates and data streams automate index creation, and [Chapter 8](#ch8) queries the same fields without any JSON at all.
