# Chapter 10 - Designing Production-Grade Dashboards {#ch10}

## 10.1 Design Principles: Dashboards Are Interfaces, Not Art

A production dashboard is an interface with three audiences and three failure modes. *During an incident*, it answers "where is the system wrong" in under thirty seconds - which means the RED metrics from [Chapter 1](#ch1) and the alert thresholds from [Chapter 8](#ch8) live on the first row, uncluttered by anything that requires interpretation. *During review*, it answers "how is the service trending" - which means recording rules ([Chapter 6](#ch6)) carry the aggregation so panels load instantly. *During design*, it answers "what question does this dashboard exist to answer" - and a dashboard that cannot state its question in a sentence becomes a museum. The three failure modes are the inverse: dashboards with forty panels nobody reads, dashboards whose queries take longer than the incident, and dashboards whose thresholds disagree with the alerts - all three are design defects, not usage problems.

The layout that survives contact with production: **one question per dashboard**, stated in its title ("Payments - Service Health"); a top row of stats that answer "is it broken"; detail rows ordered by diagnostic sequence (service RED → dependencies → resources); consistent units and thresholds across every dashboard in the estate. Consistency is a feature: when every dashboard colors 95 percent latency red at the same value, muscle memory becomes diagnostic speed.

## 10.2 Template Variables: One Dashboard, Many Targets

**Template variables** turn a dashboard from a page into a tool, and the mechanics fit in one example. Add a variable named `instance`, type *Query*, data source Prometheus:

```promql
label_values(up{job="node"}, instance)
```

Then reference it anywhere in panel queries as `$instance` (or `[[instance]]`), with *Multi-value* and *Include All option* enabled so one dashboard serves one host or the whole fleet. The variable types cover the cases: **Query** (values from the data source - the default), **Custom** (a comma list, e.g. `5m,1h,1d` for windows), **Interval** (the panel step control, exposed to queries as `$__interval`), **Textbox**, **Constant**, and **Data source** (picks among data sources - the many-Prometheis pattern from [Chapter 9](#ch9)). Two refinements separate tidy dashboards from flickering ones: *chained variables* (an `endpoint` variable whose query filters by `$instance`) cascade selections top-down, and the `$__rate_interval` macro ([Chapter 9](#ch9)) keeps rate windows valid as users widen time ranges. In dynamic dashboards (Grafana 13's GA layout engine), variables bind into the new schema the same way - `$instance` in the query box - so variable fluency transfers.

Variables are also the cardinality safety valve: a dashboard whose default view is *All* across a fleet variable exercises the recording rules instead of raw queries, and the drill-down views exist for the moment someone needs instance detail. Design the default for the stakeholder, the drill-down for the engineer.

## 10.3 Panels That Answer: Overrides, Annotations, and Repeats

Beyond the basics from [Chapter 9](#ch9), four panel mechanisms carry most production weight. **Overrides and field options** style one series without touching others - color the p99 line distinctly, give bytes panels a SI unit, hide the healthy series from an error-ratio graph. **Thresholds** (per panel, per override) paint states: the stat that is green at `up == 1` and red at 0 is the fastest status read in the building. **Annotations** overlay events on time series - deploys, restarts, config changes - and the query form queries *any* data source; the standard loop is your deploy pipeline POSTing to Grafana's annotations API on release, so every latency change in the graph arrives with a deploy line and the "it got slow Tuesday" conversation ends at the marker. **Repeating rows and panels** instantiate one panel design per variable value (per instance, per data center) - with the caveat that repeats multiply queries, so the repeated panel should read recording rules, not raw series.

::: {.note}
**Best practice - deploy markers are the cheapest observability you will ever buy**

A one-line `curl` in the GitHub Actions workflow that deploys ([GitHub Actions](https://github.com/features/actions), this series' CI volume) turns every production graph into a before/after experiment. Teams that add deploy annotations stop arguing about causality within a week; the graph answers.
:::

## 10.4 Dashboards as Code: Git Sync, Provisioning, and the JSON Model

Grafana 13 made "dashboards as code" a first-class workflow, and the estate should pick one of two patterns and apply it everywhere.

**Git Sync** (GA in 13.0) connects Grafana to a repository - GitHub, GitLab, Bitbucket, or generic Git - for *bidirectional* sync: dashboards edited in the UI are committed as JSON to the configured branch, edits in Git flow back into Grafana, and the connection can gate changes through pull requests. Configuration lives in the UI (Connection → Git Sync) or provisioning; the repository becomes the source of truth, with `main` the synced branch and feature branches the review surface. For teams whose instinct is "review dashboards like code", this is the pattern: a dashboard PR now reads like any other change, with diff and comment.

**File-based provisioning** is the older, stateless pattern: dashboards as JSON in a directory, loaded at startup:

```yaml
# /etc/grafana/provisioning/dashboards/providers.yml
apiVersion: 1
providers:
  - name: default
    orgId: 1
    folder: ""
    type: file
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

Every dashboard is a JSON file (the same artifact **Export → Save as JSON** produces), editable, reviewable, and deployed by whatever deploys the rest of the configuration - the natural fit when Grafana runs in Kubernetes ([Chapter 13](#ch13)) and dashboards ship in the same image or ConfigMap as everything else. Both patterns share one truth: the **JSON model is the dashboard**, and once it lives in Git, the dashboard acquires history, review, rollback, and an owner - the properties that separate an artifact from a document.

::: {.warn}
**Watch out - UI edits and code drift**

A Git Sync (or provisioned) estate has one rule: if a change matters, it is committed, not left as an uncommitted UI edit. Grafana marks provisioned dashboards read-only in the UI by design; Git Sync estates should treat `main` the same way and make "I fixed it in the UI, I will commit later" a firing offense for exactly the same reason as "I fixed it on the server, I will update Ansible later" ([Ansible](https://www.ansible.com/), this series' configuration volume) - the drift *is* the incident.
:::

## 10.5 Dashboard Performance: Queries, Refresh, and Cardinality

A slow dashboard is a self-inflicted outage risk, because forty heavy panels refreshing every five seconds is a scrape-against-your-own-Prometheus you did not plan for. The controls, in order of impact: **refresh rate** - auto-refresh belongs on the incident wall (10-30s), not the default dashboard (off); **max data points** - panels request enough points to fill their width, so a 24-hour range on a wide screen at 5s resolution asks Prometheus for thousands of evaluations per query; set it and let Grafana step the query, which is exactly how recording rules ([Chapter 6](#ch6)) are meant to be consumed. **Recording rules as the panel source** - a p95 computed per refresh across a fleet is the canonical subquery-to-recording-rule conversion from [Chapter 6](#ch6). **Query cost awareness** - the panel editor's query inspector shows execution time and series count; anything over a second or a few thousand series in a default-view panel is a candidate for precomputation. And **panel count** - the estate-wide budget is easier to enforce than per-panel heroics: a dashboard with more than ~25 panels is usually two dashboards pretending to be one.

## 10.6 Lab: A Production Dashboard, Reviewed in Git

::: {.lab}
### Drill 2 - Dashboard as code drill (companion to [Lab 1](#lab1)) {#drill2}

1. Build the Node Overview from [Chapter 9](#ch9) if you have not already, then add an `instance` query variable (multi-value, include All) and convert every panel to `$instance` filtering. Confirm All, single, and multi selections all render.
2. Add a chained `device` variable (network devices filtered by `$instance`) and a repeating row for per-device throughput; observe the query count in the inspector, then convert the row's queries to a recording rule ([Chapter 6](#ch6)) and re-measure.
3. Wire deploy annotations: add a static annotation (type Grafana, with tags) manually for today's lab work, then POST an annotation via the HTTP API with `curl` and confirm it renders on every time series panel.
4. Export the dashboard JSON, commit it to a repository, and set up file provisioning against that directory. Restart Grafana and edit the *provisioned* dashboard in the UI - observe the read-only behavior and articulate why.
5. Break a panel deliberately (wrong metric name), watch the panel's error state and the query inspector's diagnosis, then fix it in the JSON and re-provision. This is the as-code debugging loop, and it should feel identical to fixing any other reviewed artifact.
:::

**See also:** [Chapter 11](#ch11) for alerting from these same queries, [Chapter 12](#ch12) for what "data source" means when Prometheus becomes a fleet, and [Chapter 6](#ch6) for the recording rules the fast panels read.
