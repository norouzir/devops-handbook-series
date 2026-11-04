# Chapter 3 - Getting Started: Elasticsearch and Kibana with Docker {#ch3}

## 3.1 Ways to Run Elasticsearch

There are four ways to put Elasticsearch into the world, and they map onto four stages of a team's maturity. The **archive** - a tarball you unpack and run - is the way to see the machine with no curtains: every file, log, and flag visible. **Docker and Docker Compose** are how you run the full two-process stack this book teaches, because Elasticsearch plus Kibana is a multi-process system that Compose describes better than prose. **Elastic Cloud** - hosted or serverless - removes the operations entirely, at the price of someone else's knobs. **Kubernetes**, via the ECK operator, is how production estates run self-managed clusters - the subject of [Chapter 14](#ch14), which assumes the concepts built by then.

The recommendation is chronological, not either/or: run the Compose sandbox for the whole of Part I, and graduate to ECK or a managed offering when the operator model makes sense. Everything in this book runs on a laptop or a single small VM.

## 3.2 The Docker Compose Sandbox

The sandbox has two services: Elasticsearch on port 9200 and Kibana on port 5601. One `docker-compose.yml` ties them together:

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:9.5.5
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
    ulimits:
      memlock: { soft: -1, hard: -1 }
    ports: ["9200:9200"]
    volumes:
      - es-data:/usr/share/elasticsearch/data

  kibana:
    image: docker.elastic.co/kibana/kibana:9.5.5
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    ports: ["5601:5601"]
    depends_on: [elasticsearch]

volumes:
  es-data:
```

Three lines of configuration deserve their definitions, because every one of them is a production decision you are consciously postponing. `discovery.type=single-node` tells the node it is alone in the world - no master election quorum to wait for. `xpack.security.enabled=false` turns off TLS, authentication, and authorization; since version 8.0 security is *on by default* with generated certificates and an `elastic` bootstrap password, and turning it off is the honest way to keep a learning sandbox friction-free. `ES_JAVA_OPTS=-Xms1g -Xmx1g` pins the JVM heap to one gigabyte so the sandbox fits a laptop; [Chapter 11](#ch11) develops the heap-sizing discipline (no more than half of RAM, never above the compressed-oops ceiling around 31 GB).

`docker compose up -d`, then watch it come up:

```bash
docker compose up -d
docker compose logs -f elasticsearch    # wait for "started"
curl -s http://localhost:9200
```

The `curl` returns the node's self-description - cluster and node name, version `9.5.5`, the Lucene line underneath - which is also the first proof that the API works. Kibana is ready a minute or two later at `http://localhost:5601`; with security disabled there is no login step.

::: {.warn}
**Watch out - the sandbox settings are sandbox settings**

`xpack.security.enabled=false` and a single node are fine on a laptop and are an audit finding in production. Everything security-related is deferred to [Chapter 12](#ch12) on purpose, not because it is optional. If you port the Compose file to a shared host today, at minimum enable security and set a password first.
:::

## 3.3 Kibana Dev Tools: The Console

The single most-used surface in Kibana for the first half of this book is **Dev Tools → Console**. It is a REPL for the Elasticsearch REST API: the left pane holds requests in the book's dialect - method, path, optional JSON body - and pressing Ctrl/Cmd+Enter sends the request under the cursor to the cluster, printing the raw JSON response on the right. Autocomplete knows every endpoint; history is scrollable; requests are copy-pasteable as `curl` for scripts.

Every example from here forward is written in Console dialect. The equivalent `curl` is always mechanical - the console hides host, port, and headers and nothing else - and the appendices keep a translation table handy.

## 3.4 Your First Documents

With the stack running, the fastest way to meet the data model is to write three documents and search them. Paste into the Console:

```text
PUT books/_doc/1
{ "title": "The Docker Book", "tags": ["containers"], "year": 2024 }

PUT books/_doc/2
{ "title": "Kubernetes in Production", "tags": ["kubernetes"], "year": 2025 }

PUT books/_doc/3
{ "title": "Search with Elasticsearch", "tags": ["search"], "year": 2026 }

GET books/_search
{ "query": { "match": { "title": "book" } } }
```

Four observations, each of which a later chapter expands. First, the PUTs created the `books` index implicitly - no `CREATE TABLE`, which is convenient in a sandbox and a liability in production ([Chapter 5](#ch5)). Second, the third document was searchable immediately, but a document written *milliseconds* before a search may not be: the near-real-time refresh interval (about one second) means "indexed" and "visible" are separated by design, not by bug. Third, the `match` query on `title: book` returns the document whose title contains *Book* - case folded away - because the field was analyzed: the indexed token is the lowercased `book`, not the original string ([Chapter 5](#ch5) shows exactly which analyzer ran). Fourth, every hit carries a `_score`; relevance ranking is present even in toy examples because the inverted index computes it for free ([Chapter 1](#ch1)).

Deleting is as easy as indexing, and this is the moment to learn the reflex:

```text
DELETE books
```

::: {.note}
**Best practice - treat implicit index creation as a sandbox feature**

In production, indices are created explicitly by templates with explicit mappings ([Chapter 5](#ch5), [Chapter 10](#ch10)), and clusters are configured with `action.auto_create_index` restrictions so a typo in a shipper config cannot create a mistyped index that then receives production traffic. The sandbox is where impatience is cheap; production is not.
:::

## 3.5 Bulk Writes: The `_bulk` API

Real ingestion never writes documents one at a time; the **`_bulk` API** accepts many create/index/delete operations in one request, newline-delimited JSON (NDJSON) where action lines and document lines alternate:

```text
POST _bulk
{ "index": { "_index": "logs-app", "_id": "a-1" } }
{ "@timestamp": "2026-10-30T09:00:01Z", "level": "info", "message": "request served" }
{ "index": { "_index": "logs-app", "_id": "a-2" } }
{ "@timestamp": "2026-10-30T09:00:02Z", "level": "error", "message": "payment gateway timeout" }
{ "create": { "_index": "logs-app", "_id": "a-3" } }
{ "@timestamp": "2026-10-30T09:00:03Z", "level": "warn", "message": "retrying payment" }
```

Two details make bulk correct rather than merely functional. The endpoint is newline-sensitive - no pretty-printing, exactly one JSON object per line, and a trailing newline. And the response reports *per item*: one failed document does not fail the request, so shippers inspect item-level results rather than HTTP status alone. Every ingestion tool in [Chapter 4](#ch4) - Elastic Agent, Filebeat, Logstash - is an organized, retried, back-off-aware `_bulk` client, which is why the API deserves ten minutes of hands-on attention before those tools are trusted.

## 3.6 Reading the Sandbox: Health, Nodes, Indices

The vocabulary of [Chapter 2](#ch2) becomes concrete with three Console lines against the running sandbox:

```text
GET _cluster/health
GET _cat/nodes?v
GET _cat/indices?v
```

Expect status `yellow`, not green - the single node cannot place replica shards of its own indices, so replicas stay unassigned; this is the most common "is my cluster broken?" false alarm and the reason the health colors were explained with a single-node footnote. `_cat/nodes` shows one row: the node's roles (`dim` in the compact display for a do-everything node), heap usage, disk. `_cat/indices` lists `books` (deleted if you followed along), the Kibana system indices, and their document counts and sizes - the table you will sort by `store.size:desc` in production to find what is eating disk.

## 3.7 Lab 1: A Working Stack in Twenty Minutes

::: {.lab}
### Lab 1 - Elasticsearch plus Kibana, with your own documents {#lab1}

1. Create a project directory with the `docker-compose.yml` from Section 3.2 and start the stack with `docker compose up -d`. Confirm `curl -s http://localhost:9200` reports version 9.5.5 and that `http://localhost:5601` shows the Kibana home page.
2. In Dev Tools, run `GET _cluster/health` and `GET _cat/nodes?v`. Record why the status is yellow and what roles the single node holds.
3. Create an index `webshop` with three product documents of your own design (title, category, price, in_stock) using three `PUT` requests, then fetch one by ID with `GET webshop/_doc/<id>`.
4. Load five more documents in a single `POST _bulk` request. Verify with `GET webshop/_count` and `GET webshop/_search?size=5` that all eight are present and returned with `_source`.
5. Search: `match` on a product title word, then a `range` query on `price` (the shape of the query is explained in [Chapter 6](#ch6) - run it anyway):

   ```text
   GET webshop/_search
   { "query": { "range": { "price": { "gte": 10, "lt": 100 } } } }
   ```

6. Time-travel check: write one more document and search for it immediately, then note the refresh behavior by re-running the search after a second. Force visibility when impatient with `POST webshop/_refresh`.
7. Clean up with `DELETE webshop`, and stop the stack with `docker compose down` (add `-v` to also erase the data volume - do this only if you are done for the day).

Deliverable: a directory that boots a two-service stack with one command, and Console history showing you wrote, searched, and deleted documents through the raw API - the substrate every later chapter builds on.
:::

**See also:** [Chapter 4](#ch4) fills the empty cluster with real telemetry, and [Chapter 5](#ch5) explains what Elasticsearch did to your fields the moment you wrote them.
