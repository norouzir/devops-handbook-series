# Chapter 9 - Grafana Fundamentals: Data Sources and First Dashboards {#ch9}

## 9.1 What Grafana Is in 2026

Grafana started as a Graphite dashboard fork and became the visualization and analysis layer of the entire observability stack: one interface that queries Prometheus, Loki, Tempo, Elasticsearch, SQL databases, and dozens of other backends, and composes their answers into pages a team can share. The edition you run matters less than the model you internalize: **Grafana OSS** (AGPLv3, self-hosted, what this book uses), **Grafana Cloud** (the managed platform with generous free tier), and **Grafana Enterprise** (the commercial distribution with RBAC, auditing, and data-source plugins) all speak the same concepts - data sources, dashboards, panels, variables, alerting - and every dashboard in this book moves between them unchanged.

Grafana 13's headline changes are organizational rather than cosmetic, and both are on by default. **Dynamic dashboards** (GA in 13.0) replace the legacy grid with a new layout engine and schema; existing dashboards migrate on open, so nothing you build in this chapter fights the format. **Git Sync** (GA in 13.0) connects a Grafana instance to a Git repository and manages dashboard resources bidirectionally - edit in the UI, commit, open a pull request - which turns "dashboards as code" from a provisioning trick into a first-class workflow; [Chapter 10](#ch10) builds production practice around it. Rounded out in 13.x: dashboard templates, saved queries shared across a team, recommended visualizations when you pick a panel type, a new Gauge, and improved annotations.

::: {.note}
**Best practice - one data source, many dashboards, one owner each**

Grafana's flexibility makes dashboard sprawl the default failure mode: forty dashboards, none trusted, all stale. The unit of trust is the dashboard with a named owner and a purpose; everything else is a playground. Decide early which dashboards are *the* dashboards for a service.
:::

## 9.2 Running Grafana and the First Login

The Compose stack from [Chapter 3](#ch3) already runs Grafana at `http://localhost:3000`; the deployment model is a single container (or binary) with two storage locations that matter: `/var/lib/grafana` holds the SQLite database where dashboards, users, and alert state live - the volume in the Compose file - and `/etc/grafana/grafana.ini` holds configuration. First-day settings in the INI: `[server] root_url` if you serve behind a reverse proxy, `[security] admin_user`/`admin_password` (default admin/admin, changed at first login), `[users] allow_sign_up` (turn it off the moment more than one person has access), and `[auth]` providers - OAuth against your identity provider is the standard production setup, and anonymous read-only access (`[auth.anonymous]`) is a common pattern for wall displays.

Datasources and dashboards can also be **provisioned** from files at startup - no UI clicking, no hand-reconfiguration after a rebuild:

```yaml
# /etc/grafana/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    uid: prom
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

Mount that file into `/etc/grafana/provisioning/datasources/`, restart, and the data source exists - the pattern that [Chapter 10](#ch10) extends to dashboards and [Chapter 11](#ch11) to alerting, and the reason a Grafana instance can be stateless in a Git-backed estate.

## 9.3 Data Sources: Connecting Grafana to Prometheus

A **data source** is a named connection to one backend, and three fields of the Prometheus data source matter beyond the URL. **Access mode**: `proxy` (Grafana server queries Prometheus - the default and the right choice; `browser` sends credentials to clients and exists for edge cases). **Scrape interval**: tell Grafana the source's `scrape_interval` (15s here) so it can pick sensible `min interval` defaults for panels. **Prometheus type**: since Grafana's Prometheus integration also speaks Mimir and other compatible backends, setting *Prometheus* keeps UI hints accurate for vanilla servers. The data source editor's **Save & test** button validates connectivity - and when a panel says "no data", the diagnosis order starts here: data source reachable from Grafana (note: from *Grafana's network*, which in the Compose stack means the service name `http://prometheus:9090`, not localhost), then the query, then the time range.

One connection pattern worth knowing before [Chapter 12](#ch12): multiple Prometheus servers (per cluster, per shard) appear as multiple data sources, and a **data source variable** ([Chapter 10](#ch10)) lets one dashboard serve all of them - the standard answer to "one Grafana, many Prometheis".

## 9.4 Panels and the Query Editor

A **panel** is one visualization backed by one or more queries, and the panel editor is the same query box you learned in [Chapter 5](#ch5) with Grafana's additions: a time range picker (panel defaults to dashboard), a legend format with `{{label}}` templating, and functions that inject dashboard context (`$__rate_interval` - the rate window that always satisfies the four-scrape rule from [Chapter 5](#ch5), computed from the panel's step; prefer it over a hardcoded `[5m]` in dashboards). The visualization picker covers the working set: **Time series** for anything over time; **Stat** and **Gauge** for current values with thresholds; **Bar gauge** for ranked quantities; **Table** for inventories (targets, silences, top-N); **Heatmap** for latency distributions; **Logs** and **Traces** when the Loki/Tempo data sources arrive; **Canvas** and **Geomap** for layouts that need them. Pick the smallest panel that answers the panel's question - a stat that answers "are we up?" beats a time series the eye must parse, and a time series answers "how did it move?" better than five stats ever will.

Thresholds deserve a deliberate word, because they are the visual vocabulary of incident response: color a panel red *at the value the page fires* ([Chapter 8](#ch8)), not at an aesthetic guess. A dashboard whose red lines match the alerting thresholds teaches the team the contract without a document.

## 9.5 Your First Production Dashboard: The Node Overview

The dashboard every estate starts with is the node overview, and building it once - carefully - teaches every mechanism this chapter needs. Start with a dashboard named `Node Overview`, data source Prometheus, and four panels in a row across the top (stats), detail rows below:

- **Stat: Availability** - `avg(up{job="node"})`, thresholds: red at 0.999, green above. Unit: percent (0-1 → 100). This is the panel an incident commander trusts.
- **Time series: CPU busy** - `100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval])) * 100`. Legend `{{instance}}`, unit percent, thresholds 80/90.
- **Time series: Memory available** - `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100`, unit percent. Inverted coloring (low is bad).
- **Time series: Network I/O** - `rate(node_network_receive_bytes_total{device!~"lo"}[$__rate_interval])` and its transmit sibling, unit bytes/sec.
- **Table: Targets** - `up{job="node"}`, instant query, showing instance and value - the inventory panel.

Layout rhythm matters more than panel count: one overview row a stakeholder can read, drill-down rows for the engineer, and the "one question per dashboard" rule from [Chapter 10](#ch10) governing what gets added. Save, star it, and make it the home dashboard for the team - the first artifact of the monitoring practice this book is building.

::: {.warn}
**Watch out - the dashboard that was built once and never owned**

Every panel above encodes a decision (which metric, which aggregation, which threshold). When those decisions live only in someone's head, dashboards drift into superstition - panels copied between dashboards until nobody knows what a query means. Name an owner in the dashboard description, and require that a copied panel either references its source dashboard or has its own owner. [Chapter 10](#ch10)'s Git Sync workflow makes ownership visible in pull requests instead of tribal memory.
:::

## 9.6 Folders, Permissions, and Sharing

Dashboards organize into **folders** - the permission boundary (a folder per team is the common structure), with viewer/editor/admin roles per folder and per dashboard. Sharing options each have a niche: **Export** (the dashboard JSON, the as-code artifact), **Share → link** (short link with time range), **Snapshot** (a frozen data capture for postmortems and bug reports), and **public dashboards** (read-only views of selected panels for stakeholders outside the auth boundary). Organizational discipline beats features here: a folder per team, a folder per environment only when environments genuinely diverge, and a graveyard folder with an expiry date rather than hundreds of undeleted experiments.

**See also:** [Chapter 10](#ch10) for variables, annotations, and the dashboard-as-code workflow this chapter's JSON export feeds, [Chapter 11](#ch11) when dashboards start paging, and [Lab 1](#lab1) if the data source connection needs a refresher.
