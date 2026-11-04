# Chapter 4 - Ingesting Data: Elastic Agent, Filebeat, and Logstash {#ch4}

## 4.1 The Ingestion Menu

An empty index answers no questions, and the distance between "an application printed a log line" and "the line is a searchable document in Elasticsearch" is the ingestion layer. Elastic ships three first-party answers plus two standards-based ones, and choosing between them is an architecture decision worth making once, explicitly:

- **Elastic Agent with Fleet** - one agent, centrally managed, collecting logs, metrics, and security telemetry through named *integrations*. This is Elastic's strategic and recommended path, and the one this book teaches first.
- **Beats** - the classic family of lightweight shippers: **Filebeat** for logs, Metricbeat for metrics, Auditbeat, Packetbeat, and friends. Still fully supported and still the right tool where you need exactly one input with minimal footprint or where an integration you rely on exists only as a Beat module.
- **Logstash** - the heavyweight pipeline: many inputs, a filter grammar (including `grok` for parsing arbitrary text), many outputs, persistent queues. The ETL workhorse when transformation happens *outside* the engine.
- **Ingest pipelines** - transformation that runs *inside* Elasticsearch on ingest nodes; every shipper can reference one.
- **OpenTelemetry Collector** - the vendor-neutral standard; its Elasticsearch exporter ships OTel-collected telemetry into the stack, and OpenTelemetry-instrumented applications fit the same story.

The decision factors are operational, not ideological. One agent per host with central policy management beats six individually-configured shippers the moment the fleet exceeds a handful of machines; Logstash beats in-pipeline parsing when enrichment needs external lookups and buffering; Beats survive in estates that already run them well. The modern default for a new deployment is Agent-first, and that is the path this book follows - while teaching Filebeat and Logstash properly, because you will meet both in the wild for years.

## 4.2 Elastic Agent and Fleet

**Elastic Agent** is a single binary that runs inputs for logs, metrics, host security, and more, configured not by local files but by an **agent policy** fetched from **Fleet** - the management plane that lives in Kibana. One integration in a policy - "Nginx logs," "system metrics," "Kubernetes" - expands into the collection, parsing, and index mapping for that source, kept current by Elastic rather than by you.

The moving parts, in the order data flows:

1. **Fleet Server** - the coordination service agents talk to; it serves policies, collects agent status, and brokers upgrades. It runs as its own container or integration, talking to Elasticsearch and Kibana.
2. **Fleet UI** (in Kibana) - where integrations are added from a catalog, policies assembled, and enrollment tokens issued.
3. **Elastic Agent** - installed on hosts (package, container, or Kubernetes DaemonSet), enrolled with a token, then pulling its policy. The agent authenticates to Fleet with per-agent API keys that Fleet generates - so credentials are scoped and individually revocable, a real operational gain over shared shipper credentials ([Chapter 12](#ch12)).

Data lands in **data streams** named by convention - `logs-nginx.access-default`, `metrics-system.cpu-default` - with mappings, ingest pipelines, and lifecycle defaults attached by the integration ([Chapter 10](#ch10) explains the machinery). The practical consequence: adding Nginx logs to a properly configured estate is a few UI actions plus one agent enrollment, and upgrades are a Fleet-managed rollout rather than an Ansible run per host.

::: {.note}
**Best practice - enroll agents through your configuration manager anyway**

Fleet manages *policy*; something still installs the binary. Bake the Elastic Agent package and an enrollment command into your image or run it from your configuration manager - the Ansible volume of this series covers exactly this pattern of unattended installs. Enrollment tokens are per-policy, so the unattended install is one `elastic-agent install` flag away. Fleet then takes over for the agent's whole life, including upgrades.
:::

## 4.3 Filebeat: The Classic Log Shipper

Filebeat earns its longevity with a small footprint and a simple contract: watch files (or containers, or a syslog socket), remember how far you read in a **registry file**, ship what is new as events, survive restarts without duplication or loss (at-least-once, with idempotent document ids when the pipeline sets them). The modern file input is `filestream`:

```yaml
filebeat.inputs:
  - type: filestream
    id: nginx-access
    paths:
      - /var/log/nginx/access.log
    parsers:
      - container: ~

output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
  pipeline: parse-nginx-access

setup.template.enabled: true
logging.level: info
```

The `pipeline` key is the quiet hero: it routes events through a named ingest pipeline defined on the Elasticsearch side ([Section 4.5](#ch4-pipelines)), which is how a minimal shipper and a maximal parser cooperate. Filebeat also ships **modules** - prebuilt inputs, parsers, and dashboards for common sources such as Nginx, Redis, and system logs - which are what Elastic Agent integrations evolved from; running `filebeat setup` installs their Kibana assets.

Beats and Agent coexist on a timeline: Elastic documents Agent as the recommended default and Beats as fully supported, with a maintained capability-comparison page for the gaps. The pragmatic reading for an operator: choose Agent for new fleets, keep Beats where they already work or where an input needs their specific maturity, and expect the boundary to keep moving toward Agent.

## 4.4 Logstash: The Pipeline Workhorse

Logstash is a three-stage pipeline - **input → filter → output** - that moves and transforms events between systems, with Elasticsearch usually at the right end:

```text
input {
  file {
    path => "/var/log/app/*.log"
    start_position => "beginning"
    sincedb_path => "/usr/share/logstash/data/sincedb"
  }
}

filter {
  grok {
    match => { "message" => "%{IP:client} %{WORD:method} %{URIPATHPARAM:request}
                             %{NUMBER:status:int} %{NUMBER:duration_ms:float}" }
  }
  date {
    match => ["timestamp", "ISO8601"]
    target => "@timestamp"
  }
  mutate { remove_field => ["message", "timestamp"] }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "logs-app-%{+YYYY.MM.dd}"
  }
}
```

`grok` is the reason Logstash survives: a readable macro language over regular expressions that turns unstructured lines into typed fields, with a library of over a hundred built-in patterns. The `date` filter rewrites the event timestamp - the single most important parse in a log pipeline, because every time-based query, dashboard, and ILM policy keys off `@timestamp` ([Chapter 10](#ch10)). Logstash runs multiple pipelines (`pipelines.yml`), back-pressures when Elasticsearch is slow, and buffers to a **persistent queue** so a restart does not drop in-flight events - the properties that make it the buffer of choice between a chaotic fleet and a strict cluster.

The division of labor that has settled out in practice: Elastic Agent/Filebeat collect and ship; Logstash (or an ingest pipeline) transforms; parsing that is pure text-munging moves to ingest pipelines where possible, and Logstash keeps the jobs that need lookups, conditional routing across *outputs*, or heavy buffering.

## 4.5 Ingest Pipelines: Parsing on the Node {#ch4-pipelines}

An **ingest pipeline** is a named list of processors that runs inside Elasticsearch on the ingest node, before indexing. The same grok-style parsing available in Logstash exists here as processors, defined through the API:

```text
PUT _ingest/pipeline/parse-nginx-access
{
  "processors": [
    {
      "grok": {
        "field": "message",
        "patterns": ["%{IPORHOST:client.ip} - %{DATA:user.name} \\[%{HTTPDATE:timestamp}\\] \"%{DATA:http.request.method} %{DATA:url.path} %{DATA:network.protocol_version}\" %{NUMBER:http.response.status_code:int} %{NUMBER:http.request.body.bytes:int}"],
        "ignore_failure": true
      }
    },
    {
      "date": {
        "field": "timestamp",
        "formats": ["dd/MMM/yyyy:H:m:s Z"],
        "target_field": "@timestamp"
      }
    },
    { "remove": { "field": "message", "ignore_missing": true } }
  ]
}
```

The `_simulate` API makes pipelines testable before they touch traffic - paste a sample event, see the output document, iterate:

```text
POST _ingest/pipeline/parse-nginx-access/_simulate
{ "docs": [ { "_source": { "message": "10.0.0.7 - - [30/Oct/2026:09:14:07 +0000] \"GET /checkout HTTP/1.1\" 500 187" } } ] }
```

Choosing between Logstash filters and ingest pipelines is now a genuine trade rather than a capability gap: pipelines run where the data already is (no extra process, automatic horizontal scale with ingest nodes) and are required for Agent and Filebeat modular parsing; Logstash wins on cross-output routing, external enrichment at scale, and queues that decouple a flaky source from a strict cluster. The fields above follow the **Elastic Common Schema (ECS)** - `client.ip`, `http.response.status_code` - the naming convention Elastic integrations use so that a status code means the same thing whatever produced it; adopting ECS field names in custom pipelines keeps your data fluent in Kibana's dashboards and detection rules.

## 4.6 Lab 2: Ship Nginx Logs into Elasticsearch

::: {.lab}
### Lab 2 - Filebeat, an ingest pipeline, and parsed fields {#lab2}

1. Extend the Chapter 3 Compose file with two services - an Nginx whose access log is written to a shared volume, and Filebeat reading it:

   ```yaml
   nginx:
     image: nginx:1.28-alpine
     ports: ["8080:80"]
     volumes:
       - ./logs:/var/log/nginx

   filebeat:
     image: docker.elastic.co/beats/filebeat:9.5.5
     user: root
     command: filebeat -e --strict.perms=false
     volumes:
       - ./filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
       - ./logs:/var/log/nginx:ro
     depends_on: [elasticsearch]
   ```

2. Generate traffic so the log file is real: `for i in $(seq 1 200); do curl -s -o /dev/null http://localhost:8080/; done` plus a few requests to paths that 404.
3. Write the `filebeat.yml` from Section 4.3, pointing at the access log and at pipeline `parse-nginx-access`, and create that pipeline with the `PUT _ingest/pipeline` call from Section 4.5 (adapted to your Nginx log format - check the first two lines of `./logs/access.log`).
4. Use `POST _ingest/pipeline/parse-nginx-access/_simulate` with a real line from the log until the output shows `client.ip`, `http.request.method`, `url.path`, and `http.response.status_code` as typed fields.
5. Verify the results in Elasticsearch: `GET logs-nginx-default/_search?size=3` (or your chosen index) - confirm `@timestamp` is a parse date, not the ship time, and that a `term` filter on `http.response.status_code` finds your 404s.
6. Kill Filebeat mid-stream (`docker compose stop filebeat`), generate ten more requests, restart it, and confirm the registry caught up - the at-least-once contract, demonstrated.
7. Open Kibana Discover (next chapter previews it; just look): the logs should be browsable with the parsed fields on the left.

Deliverable: a three-service stack where generated traffic becomes parsed, typed, timestamped documents - and proof in your own history that a restart loses nothing.
:::

**See also:** [Chapter 5](#ch5) explains the mapping decisions your parsed fields just inherited, and [Chapter 9](#ch9) turns these documents into a dashboard.
