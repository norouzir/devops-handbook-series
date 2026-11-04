# Appendix B - Starter Configurations {#appB}

Copy-paste starting points for the stack this book builds. Every file here appears somewhere in a chapter; this appendix collects them into one place so a new project starts from files, not from memory.

## B.1 `docker-compose.yml` - The Learning Stack

Elasticsearch, Kibana, Nginx (log source), and Filebeat ([Chapters 3](#ch3) and [4](#ch4)):

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:9.5.5
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
      - path.repo=/usr/share/elasticsearch/backup
    ulimits:
      memlock: { soft: -1, hard: -1 }
    ports: ["9200:9200"]
    volumes:
      - es-data:/usr/share/elasticsearch/data
      - es-backup:/usr/share/elasticsearch/backup

  kibana:
    image: docker.elastic.co/kibana/kibana:9.5.5
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    ports: ["5601:5601"]
    depends_on: [elasticsearch]

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

volumes:
  es-data:
  es-backup:
```

The security hardening swap is [Chapter 12](#ch12) Section 12.5; the ECK equivalent for Kubernetes is [Chapter 14](#ch14) Section 14.1.

## B.2 `filebeat.yml` - Minimal Log Shipper

```yaml
filebeat.inputs:
  - type: filestream
    id: nginx-access
    paths:
      - /var/log/nginx/access.log

output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
  pipeline: parse-nginx-access
  # With security enabled (Chapter 12):
  # protocol: "https"
  # api_key: "<id>:<secret>"
  # ssl.certificate_authorities: ["/usr/share/filebeat/certs/ca.crt"]

setup.template.enabled: true
logging.level: info
```

## B.3 Ingest Pipeline - Nginx Access Log

```text
PUT _ingest/pipeline/parse-nginx-access
{
  "processors": [
    {
      "grok": {
        "field": "message",
        "patterns": [
          "%{IPORHOST:client.ip} - %{DATA:user.name} \\[%{HTTPDATE:timestamp}\\] \"%{DATA:http.request.method} %{DATA:url.path} %{DATA:network.protocol_version}\" %{NUMBER:http.response.status_code:int} %{NUMBER:http.request.body.bytes:int}"
        ],
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
    { "remove": { "field": "message", "ignore_missing": true } },
    { "remove": { "field": "timestamp", "ignore_missing": true } }
  ]
}
```

Test before trusting: `POST _ingest/pipeline/parse-nginx-access/_simulate` ([Chapter 4](#ch4)).

## B.4 ILM Policy and Index Template - The Default Log Estate

```text
PUT _ilm/policy/logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": { "max_primary_shard_size": "50gb", "max_age": "7d" }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "forcemerge": { "max_num_segments": 1 },
          "allocate": { "number_of_replicas": 0 },
          "set_priority": { "priority": 50 }
        }
      },
      "delete": { "min_age": "30d", "actions": { "delete": {} } }
    }
  }
}

PUT _component_template/logs-mappings
{
  "template": {
    "settings": {
      "index.number_of_shards": 1,
      "index.number_of_replicas": 1,
      "index.lifecycle.name": "logs-policy",
      "index.codec": "best_compression"
    },
    "mappings": {
      "dynamic": "strict",
      "properties": {
        "@timestamp": { "type": "date" },
        "service.name": { "type": "keyword" },
        "environment":  { "type": "keyword" },
        "level":        { "type": "keyword" },
        "message":      { "type": "text" },
        "client.ip":    { "type": "ip" },
        "http.response.status_code": { "type": "integer" },
        "url.path":     { "type": "keyword" },
        "url.request_duration_ms":  { "type": "float" }
      }
    }
  }
}

PUT _index_template/logs-nginx
{
  "index_patterns": ["logs-nginx-*"],
  "data_stream": {},
  "priority": 200,
  "composed_of": ["logs-mappings"]
}
```

The policy narrative (phases, tiering, retention economics) is [Chapter 10](#ch10).

## B.5 Logstash Pipeline - When Transformation Lives Outside

```text
input {
  beats { port => 5044 }
}

filter {
  grok {
    match => { "message" => "%{IP:client.ip} %{WORD:http.request.method} %{URIPATHPARAM:url.path} %{NUMBER:http.response.status_code:int}" }
  }
  date { match => ["timestamp", "ISO8601"] target => "@timestamp" }
  mutate { remove_field => ["message"] }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    data_stream => "true"
    action => "create"
  }
}
```

`pipelines.yml` runs several side by side; the persistent queue and back-pressure behavior are [Chapter 4](#ch4) Section 4.4.

## B.6 Snapshot Policy - SLM with Retention

```text
PUT _snapshot/local-backup
{ "type": "fs", "settings": { "location": "/usr/share/elasticsearch/backup", "compress": true } }

PUT _slm/policy/nightly-logs
{
  "schedule": "0 30 1 * * ?",
  "name": "<nightly-logs-{now/d}>",
  "repository": "local-backup",
  "config": {
    "indices": ["logs-*", "metrics-*", ".security-*", ".kibana*"],
    "include_global_state": true
  },
  "retention": { "expire_after": "30d", "max_count": 90, "min_count": 7 }
}
```

Object storage (S3/GCS/Azure) swaps the repository type and takes credentials via the keystore ([Chapter 13](#ch13)); the restore drill that makes it real is [Lab 5](#lab5).
