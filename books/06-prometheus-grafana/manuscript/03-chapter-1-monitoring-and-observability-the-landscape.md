# Chapter 1 - Monitoring and Observability: The Landscape {#ch1}

## 1.1 Why Monitoring Is a DevOps Discipline

Every operational practice in this series - deploying with Docker, running on Kubernetes, shipping with GitHub Actions, configuring with Ansible, provisioning with Terraform - eventually converges on the same moment: something you built is running in production, and somebody is asking whether it is working. The discipline that answers that question is monitoring, and it is a DevOps discipline in the strict sense, because the people who build the system are the people who need the answer. A monitoring stack that only the operations team can read produces tickets, not engineering; a monitoring stack the whole team reads produces conversations that start with a graph and end with a fix.

The economics have a brutal asymmetry worth internalizing early. A metric you failed to collect yesterday cannot answer a question today; there is no retroactive scrape, no way to reconstruct what an unlabeled counter was doing during last night's incident. Storage is cheap, context switching during an outage is expensive, and disk space spent on metrics you rarely query is almost always cheaper than the fifteen minutes an on-call engineer spends blind. This is why monitoring decisions are architectural decisions, made at design time alongside database schemas and network topology, and why this book starts with concepts rather than installation: what you choose to measure, and how you name it, will outlive every tool you use to measure it.

Monitoring also earns its keep long before anything breaks. Usage trends justify capacity purchases, latency percentiles validate a performance refactor, a deploy marker on a graph turns "it feels slower since Tuesday" into a decision. Teams that treat monitoring as a page-and-respond utility miss most of the value; the best teams read their dashboards when nothing is wrong at all.

## 1.2 The Three Signals: Metrics, Logs, and Traces

Modern systems emit three primary telemetry signals, and knowing where each one wins is the first competency of the job.

**Metrics** are numeric time series: a name, a set of key-value labels, and a stream of (timestamp, value) samples. They are small - a handful of bytes per sample - cheap to store and query over long ranges, and mathematically composable, which makes them the signal of choice for dashboards, alerting, and capacity planning. What they buy in size they pay for in structure: a metric tells you *that* CPU is at 97 percent and *for whom*, but not *which* code path put it there.

**Logs** are discrete, timestamped text events with the full fidelity of whatever the application chose to print. They answer the questions metrics raise: the stack trace behind the error rate spike, the request body behind the 500. The cost is volume - logs are routinely orders of magnitude larger than the metrics describing the same period - which is why mature estates keep logs indexed and searchable for days and archive them for months, while metrics stay queryable for years.

**Traces** follow one request as it crosses service boundaries, recording each hop with timing and metadata. They answer the distributed-systems question that neither metrics nor logs can: of the eleven services a checkout request touches, which one added 800 milliseconds? Tracing is the youngest signal and increasingly arrives through OpenTelemetry, the vendor-neutral instrumentation standard that has become the default way to instrument new code.

There is a fourth signal - continuous profiling - and a family of glue technologies, but the working model is simple: *metrics tell you where to look, logs and traces tell you what you are looking at*. This book builds the metrics half of that loop deeply, and positions it honestly: Chapter 12 shows how Prometheus coexists with log stores such as Grafana Loki and the Elastic Stack rather than pretending one signal replaces the others.

## 1.3 The Pull Model and How Prometheus Won

Prometheus began in 2012 at SoundCloud as a reaction against the monitoring orthodoxy of the day, consciously modeled on Google's internal Borgmon system, and joined the Cloud Native Computing Foundation as its second graduated project after Kubernetes. By the mid-2020s it had become the de facto metrics standard of the cloud native world: every Kubernetes distribution scrapes Prometheus format by default, and the CNCF ecosystem ships Prometheus metrics as a lingua franca.

The design decision people still argue about is the *pull model*: Prometheus initiates an HTTP request to each target on a fixed schedule - the *scrape* - and the target simply exposes its current state as text at `/metrics`. Push-based agents of the older generation required every application to know where the monitoring server lived and to keep sending whether or not anyone was listening. Pull inverts the dependency: an application only needs to *describe* itself, not *contact* anyone, which is why the metrics endpoint needs no configuration, why a metrics endpoint is trivially debuggable with `curl`, and why Prometheus can discover that a service is *down* - the most valuable alert of all - precisely because the scrape fails. Batch jobs that outlive a scrape interval are the model's one genuine gap, filled by the Pushgateway (see [Chapter 4](#ch4)).

The second architectural bet is *local storage first*. A Prometheus server is a single static Go binary with an embedded time-series database; it needs no distributed store, no queue, no coordination service to do its job. That makes the failure domain small and the operational contract honest - you run one process per data domain, scale by adding servers rather than growing one, and adopt long-term storage (Chapter 12) only when a real requirement appears.

::: {.note}
**Best practice - treat the scrape endpoint as an API**

Because any client can `curl /metrics`, the exposition format doubles as documentation of your system's inner state. Keep it readable, keep it labeled, and version it like any other interface.
:::

## 1.4 Golden Signals, RED, and USE

Three frameworks dominate the answer to "what should I measure?", and they are complementary rather than competing.

The **four golden signals** - latency, traffic, errors, and saturation - come from Google's SRE practice and describe a service from the user's side. Latency distinguishes successful from failed requests, because they usually have different distributions; traffic is demand; errors are the rate of failed operations; saturation is how full your constraints are - queues, connection pools, disk.

The **RED method** - rate, errors, duration - is the request-service slice of the same idea, popularized by Tom Wilkie of Grafana Labs, and it maps one-to-one onto the three metrics you will build for every HTTP endpoint in this book: request rate, error rate, and request duration, typically as a histogram with percentiles.

The **USE method** - utilization, saturation, errors - comes from Brendan Gregg and describes *resources* rather than services: for every CPU, disk, network interface, and pool, ask how busy it is, how much extra work it has queued, and how often it errors. USE is the lens for infrastructure dashboards; RED is the lens for the software running on it.

A production service gets both: RED dashboards per endpoint, USE dashboards per host, and alerting built on the symptoms users would feel (Chapter 8 turns this into a discipline).

## 1.5 The 2026 Landscape: Prometheus 3, OpenTelemetry, and Grafana 13

The ecosystem this book covers is mid-flight in a consolidation that is worth understanding before the tool chapters, because it explains several design choices you will meet.

**Prometheus 3** arrived in November 2024 and is now the mature line, at 3.15 as of October 2026. Its generational changes: a rewritten web UI, **Remote Write 2.0** (a more efficient, metadata-carrying protocol for shipping metrics to long-term stores), UTF-8 metric and label names by default, and a **native OTLP receiver** - Prometheus now speaks the OpenTelemetry ingestion protocol directly, which means OpenTelemetry-instrumented applications no longer need a translation gateway to feed a Prometheus backend. Native histograms (a more efficient histogram format) remain experimental behind a feature flag.

**OpenTelemetry convergence** is the second force. The OTel Collector has become the standard agent for shipping telemetry, and the Prometheus exposition format and Prometheus-compatible backends are where most of that telemetry lands. The practical consequence for a DevOps engineer is pleasant: instrumenting code with OpenTelemetry SDKs and running Prometheus remain fully compatible strategies, and Chapter 4 shows both.

**Grafana 13** (13.3 as of October 2026) continues Grafana's evolution from a visualization layer into an observability platform. Two 13.0 changes matter for how this book teaches dashboards: *dynamic dashboards* are now generally available (a new layout engine and schema that dashboards migrate to automatically), and *Git Sync* is GA, providing bidirectional Git integration so dashboards can be edited in the UI and committed as code without leaving the browser. Grafana is licensed AGPLv3 - open source by any reasonable operational definition, but worth reading if you redistribute it inside a commercial product.

**Long-term storage** settled into two durable open-source architectures, Thanos and Grafana Mimir, both building on the same block-storage ideas (Chapter 12 compares them), alongside managed offerings such as Grafana Cloud and Amazon Managed Service for Prometheus. VictoriaMetrics remains a popular single-binary alternative.

::: {.warn}
**Watch out - version numbers in examples**

Prometheus, Alertmanager, and Grafana release frequently; example configuration in this book targets Prometheus 3.15 / Alertmanager 0.34 / Grafana 13.3 but the vast majority of the surface - PromQL, relabeling, alerting semantics - has been stable for years. When you hit a configuration error, read the error text first and the changelog second; both projects are unusually good at actionable messages.
:::

## 1.6 How This Book Teaches Prometheus and Grafana

Part I builds Prometheus from the ground up: architecture and data model ([Chapter 2](#ch2)), a running stack by the end of [Chapter 3](#ch3), real telemetry from exporters and instrumented code in [Chapter 4](#ch4), and then the query language in two passes - fundamentals in [Chapter 5](#ch5), histograms, recording rules, and subqueries in [Chapter 6](#ch6) - before service discovery ([Chapter 7](#ch7)) and the full alerting pipeline ([Chapter 8](#ch8)). Part II turns telemetry into an operated system: Grafana fundamentals ([Chapter 9](#ch9)), production dashboard design ([Chapter 10](#ch10)), Grafana's unified alerting ([Chapter 11](#ch11)), high availability and long-term storage ([Chapter 12](#ch12)), and Kubernetes monitoring with the operator pattern ([Chapter 13](#ch13)).

Five labs carry the hands-on load, embedded in the chapters where they consolidate the most: the core stack ([Lab 1](#lab1)), instrumentation and probing ([Lab 2](#lab2)), PromQL with recording rules ([Lab 3](#lab3)), the alert pipeline ([Lab 4](#lab4)), and kube-prometheus-stack on a kind cluster ([Lab 5](#lab5)). If you are reading to pass a platform-interview loop rather than to operate a system, chapters 2, 5, 6, 8, and 12 are the spine; if you are reading to stand up monitoring this week, do the labs in order and let the prose catch up with your curiosity.

**See also:** [Chapter 2](#ch2) for how the data you will query is actually stored, and [Chapter 3](#ch3) when you are ready to run the stack.
