# Chapter 9 - Kibana: Discover, Visualizations, and Dashboards {#ch9}

## 9.1 Kibana as a Workspace

Kibana is the human surface of the stack, and in a modern version it is several applications behind one shell: Discover for exploring documents, Dashboard for composed analytics, Alerting for rules and connectors ([Chapter 14](#ch14)), Stack Management for the machinery - data views, users, integrations, snapshots. Two organizing concepts make the shell navigable. **Spaces** are workspaces that partition everything - dashboards, data views, even feature visibility - so the payments team and the platform team can share one Kibana without sharing one cluttered sidebar; the default Space is fine for a single team. **Data views** (formerly index patterns) are named queries over indices - the bridge between Kibana's tools and Elasticsearch's indices, and the first object to create in any new Kibana.

## 9.2 Data Views: Naming What You Explore

A data view says *which indices* and *which time field*: pattern `logs-*` against `@timestamp` covers every log data stream in this book's stack. Creation lives in Stack Management → Data Views and takes two fields - the rest is optional (field formatting, runtime fields for derived values). Three habits keep data views useful rather than sprawling:

One data view per *audience*, not per index - `logs-*` for log triage, `metrics-*` for infrastructure, not one per data stream, or every future index rename becomes a Kibana migration. Name patterns to include time-sliced backing indices automatically - data streams ([Chapter 10](#ch10)) roll over into `.ds-*` indices that the parent pattern keeps covering, which is why dashboards survive rollovers without edits. And keep the timestamp field set - it is what enables the time picker in Discover and the time axis defaults in every visualization; a data view without one is a different, non-temporal tool.

## 9.3 Discover: The Log Reading Room

**Discover** is the interface every engineer who joins a team running Elastic must learn on day one, because it is where the raw documents live. The layout is three-sided: the time picker (top right) scopes every query; the query bar filters documents; the document table shows `_source` expanded to readable fields. The query bar speaks **KQL** (Kibana Query Language) by default:

```text
http.response.status_code >= 500 and service.name == "checkout" and not url.path: /health*
```

KQL is deliberately smaller than the DSL - field comparisons joined by `and`/`or`/`not`, wildcards, quotes for phrases, parentheses for grouping - and its superpower is that Kibana compiles it to the DSL of [Chapter 6](#ch6) with correct contexts. The Lucene syntax toggle remains for veterans; KQL is the default for good reason. Around the query bar live the panel of fields (click a field to see its top values - instant histogram of a keyword), the filter chips that accumulate as you click values in documents, and the histogram that makes every query a time series by default. The workflow that becomes reflex: pick a time window, filter to the failing signature, click through top values of `error.type` or `service.name`, open documents, paste the stack trace into the incident channel.

::: {.note}
**Best practice - run Discover in ES|QL mode for analysis, KQL for triage**

The query bar has an ES|QL mode ([Chapter 8](#ch8)): `FROM logs-* | WHERE ... | STATS ...`. The two modes are complementary rather than competing: KQL filters *documents* and keeps the histogram-centric workflow fast, ES|QL computes *tables* and replaces the "export to spreadsheet" step of many investigations. The mode switch preserves nothing between modes - they are different queries - so pick per question, not per session.
:::

## 9.4 Lens: Building Visualizations

**Lens** is Kibana's drag-and-drop visualization builder, and it has quietly become the only visualization tool most teams need. You drag fields onto a canvas; Lens suggests chart types from the field types (keyword → bar or pie, numeric with timestamp → line, numeric alone → metric or gauge); underneath, it compiles your drag to an aggregation ([Chapter 7](#ch7)) or an ES|QL query. The standard observability panel set maps directly:

- **Line chart** - a `date_histogram` of error counts (the DSL of [Section 7.3](#ch7-buckets) rendered), one series per `service.name` via a breakdown field.
- **Bar chart** - `terms` aggregation, horizontal for long label lists: top clients, top paths, top error types.
- **Metric and gauge** - a single number with a threshold: current error rate, 99th-percentile latency against an SLO.
- **Pie** - proportional shares: traffic by service tier, statuses by class (2xx/4xx/5xx).
- **Data table** - raw aggregation output for the rows a chart would waste.

Every panel is backed by the exact aggregation you would have typed in the Dev Tools console, which makes Lens a good teacher: switch a panel to "show underlying query" and the JSON of [Chapter 7](#ch7) appears. For programmatic cases, **TSVB** and the **Visualize Builder** handle time-series math (rates, moving averages, derivatives) with pipeline aggregations ([Section 7.4](#ch7-composing)) beyond Lens's current reach.

## 9.5 Dashboards That Answer Questions

A dashboard is a set of panels sharing filters and a time picker, and the difference between a useful one and a wallpaper of charts is design discipline, not tooling. The pattern that holds across teams: one dashboard per *question*, not per data source - "Are we serving users well?" (latency percentiles, error ratio by service, traffic, saturation), "What is happening right now?" (log stream, alert panels, deploy markers), each answering its question in under ten seconds of reading.

Mechanics that matter: **controls** (dropdown filters for service, environment) turn one dashboard into many views; **shared cross-filtering** - clicking a bar in one panel filters every other panel to that value - is the drill-down interaction that makes dashboards investigative instead of decorative; **saved searches** from Discover embed as log-tail panels; and **drilldowns** link a panel click to another dashboard, a Discover view, or an external runbook URL with parameters. Dashboards are JSON objects stored in Kibana, which means they export, version in Git, and move between environments - the deployment story [Chapter 14](#ch14) and the companion metrics volume both lean on.

## 9.6 Lab 4: The Log Analytics Dashboard

::: {.lab}
### Lab 4 - From data view to dashboard, on the Nginx stack {#lab4}

1. Ensure the Chapter 4 stack is up and generating traffic (rerun the load generator; a few thousand documents makes every chart meaningful).
2. Create the data view: pattern `logs-nginx-*` (or `logs-*` for the broader estate), timestamp field `@timestamp`. Name it `nginx-logs`.
3. In Discover, build the triage query in KQL: `http.response.status_code >= 500`, last 24 hours. Click top values of `url.path` and `client.ip` to feel cross-filtering, then save the search as `nginx-errors`.
4. In Lens, build four panels and put them on a dashboard named `Nginx - Service Health`:

   - Line: request count per 5-minute bucket, broken down by `http.response.status_code` (top 5).
   - Line: 95th percentile of `url.request_duration_ms` over time.
   - Horizontal bar: top 10 `url.path` by count, error-status filter applied.
   - Metric: current count of 5xx (last 15 minutes) with a red threshold at 50.

5. Wire the interaction: add a Controls dropdown on `url.path`; set the metric panel to drive a drilldown to the saved search `nginx-errors`.
6. Stress the dashboard: rerun the load generator with a burst of requests to one path, and watch the metric panel and the breakdown line separate the signal (new spike) from the noise (baseline traffic).
7. Export the dashboard (Stack Management → Saved Objects → export) and read the JSON: identify the aggregation behind two panels - the DSL of [Chapter 7](#ch7) should now be recognizable on sight.

Deliverable: a shareable, clickable dashboard that answers "is Nginx healthy, and what broke?" - and proof you can trace every panel to the aggregation underneath it.
:::

**See also:** [Chapter 10](#ch10) keeps the data behind dashboards cheap as volume grows, and [Chapter 14](#ch14) adds alerting so the dashboard wakes you when it should.
