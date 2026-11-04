# Chapter 8 - Alerting with Alertmanager {#ch8}

## 8.1 Alert Rules: From Query to Alert

Alerting is where PromQL stops being descriptive and becomes a contract, and the contract has two halves. The **alerting rule** lives in a rule file alongside recording rules ([Chapter 6](#ch6)) and turns an expression into an alert *state*:

```yaml
groups:
  - name: availability
    rules:
      - alert: TargetDown
        expr: up{job="node"} == 0
        for: 2m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Node target {{ $labels.instance }} is down"
          description: "Scrape of {{ $labels.job }} target {{ $labels.instance }} has failed for more than 2 minutes."
          runbook_url: "https://runbooks.example.com/target-down"
```

An alert transitions through two states. **Pending** from the moment the expression is true; **firing** once it has been true continuously for `for` - and Prometheus exposes both states as a synthetic series, `ALERTS{alertname="TargetDown", alertstate="firing", ...}`, which you can graph, record, and alert on like anything else. The templated variables in annotations are the label set at evaluation time: `{{ $labels.instance }}` and `{{ $values.value }}` (the expression's result) are the two you will use constantly. `for` is the cheapest noise filter in the whole stack - it converts blips into non-events - and its absence is the difference between "we get paged about real problems" and "we have muted the channel"; a scrape-interval-scale alert (2-5 minutes for infrastructure, longer for trends) should have one unless the failure mode it detects is shorter than the `for` itself.

::: {.warn}
**Watch out - the alert that cannot resolve**

An alerting rule's labels are fixed at evaluation; an alert fires *per resulting series*. If the expression's label set includes something unstable (`instance`, `pod`), every restart produces a brand-new alert identity, and notification systems accumulate ghosts. Aggregate in the expression (`max by (job)`) when the *service* is the thing that is down, and reserve per-instance labels for alerts a human will triage per-instance.
:::

## 8.2 Designing Alerts Worth Receiving

The technology of alerting is trivial; the design is not, and three principles separate pages from noise. **Alert on symptoms, not causes**: "users cannot check out" (error ratio, latency, availability) pages; "high CPU" is a diagnosis you investigate *after* the symptom alert, usually from the same dashboard the page linked to. **Every alert is actionable**: if the only response to a firing alert is "look at it later", it is a dashboard panel or a ticket, not a page. **Alerts reference runbooks**: the `runbook_url` annotation is not bureaucracy - it is the difference between an on-call engineer who reads the intended response and one who improvises.

SLO-based alerting formalizes "symptom" into math. With an availability objective of 99.9 percent, the monthly error *budget* is 43 minutes, and the standard implementation is **multi-window burn-rate alerting**: alert when errors are consuming budget at 14.4x (2 percent in 1 hour - would exhaust the month in ~3 days) *and* at 14.4x over 5 minutes (confirmation window), with a second pair at 6x/30m and 1x/6h for slower burns. The recorded-ratio series from [Chapter 6](#ch6) make the rules one line each:

```yaml
- alert: ErrorBudgetBurnFast
  expr: |
    (
      job:http_errors:ratio_rate1h > (14.4 * 0.001)
      and
      job:http_errors:ratio_rate5m > (14.4 * 0.001)
    )
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Fast error-budget burn on {{ $labels.job }}"
```

Two windows ANDed together is the noise-killer: the long window provides stability, the short window provides responsiveness, and neither alone pages. Severity labels (`critical` pages, `warning` opens a ticket, `info` notifies a channel) are the routing vocabulary the Alertmanager consumes next.

## 8.3 The Alertmanager: Grouping, Routing, Deduplication

The **Alertmanager** receives firing alerts from Prometheus (via the `alerting:` section configured in [Chapter 3](#ch3)) and answers the questions Prometheus deliberately does not: *who* should know, *how*, *how often*, and *when to stop talking*. Its configuration is a single `alertmanager.yml` built on four concepts.

**Grouping** collapses equivalent alerts: `group_by: ['alertname', 'job', 'severity']` means thirty instances of `TargetDown` for one job become one notification with thirty instances listed - the difference between a page and a notification storm during a network partition. Grouping waits are the tuning knobs: `group_wait` (default 30s) delays the first notification so stragglers join the group; `group_interval` (5m) controls when a changed group notifies again; `repeat_interval` (4h) re-notifies an unchanged firing group. **Routing** is a tree: the root route is the fallback receiver, and child routes match label sets - `severity="critical"` to PagerDuty, `team="payments"` to the payments Slack, `continue: true` when an alert must go to two places. **Receivers** are destinations (next section). **Inhibition** suppresses downstream noise: when `TargetDown` fires for a node, the *symptoms* of that node being unreachable should not page separately - an `inhibit_rule` with equal source/target labels and a `not_equal` on severity does exactly that, critical mutes warning.

```yaml
route:
  receiver: default-slack
  group_by: [alertname, job]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers: [severity="critical"]
      receiver: pagerduty-platform
    - matchers: [team="payments"]
      receiver: slack-payments
      continue: true

inhibit_rules:
  - source_matchers: [alertname="TargetDown", severity="critical"]
    target_matchers: [severity="warning"]
    equal: [instance]
```

::: {.note}
**Best practice - time-based routing beats mute-by-hand**

Maintenance windows belong in Alertmanager `time_intervals` (referenced as `active_time_intervals`/`mute_time_intervals` on routes), not in a human's memory to unmute. A silenced-by-person system pages the next person during the next deployment window; a time-interval system does not.
:::

## 8.4 Receivers and Notification Templates

Receivers bind routing decisions to destinations, and the built-in integrations cover the standard set: `email`, `slack`, `pagerduty`, `opsgenie`, `webhook` (the universal integration for everything else - Incident.io, PagerDuty-adjacent tools, your own bot), `victorops`, `sns`, `telegram`, `discord`, `webex`. A Slack receiver shows the template surface:

```yaml
receivers:
  - name: slack-payments
    slack_configs:
      - api_url_file: /etc/alertmanager/secrets/slack_url
        channel: "#payments-alerts"
        send_resolved: true
        title: '{{ .CommonLabels.alertname }} - {{ .Status }}'
        text: >-
          {{ range .Alerts }}{{ .Annotations.summary }}
          {{ .Annotations.runbook_url }}
          {{ end }}
```

Two details separate working integrations from abandoned ones. **`send_resolved: true`** delivers the recovery notification - without it, teams learn within a week that notifications mean bad news and start ignoring the channel. And **secrets come from files** (`api_url_file`), so the config itself stays committable; the file is provisioned by whatever manages your secrets ([Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html) and Terraform are this series' usual suspects). Notification text is Go templates over the alert group - `.Alerts`, `.CommonLabels`, `.Annotations` - and the discipline from [Chapter 8](#ch8)'s rules applies here too: the notification should answer "what is broken, where, and what do I do first" in three lines, with the runbook link doing the rest.

## 8.5 Silences, amtool, and Running Alertmanager in HA

**Silences** are the operator-facing mute: created in the UI or with `amtool`, they match label sets for a duration - `amtool silence add instance=web-01 -d 2h -c "kernel upgrade" -o /dev/null`. Silences are for *known, bounded* work; time intervals ([Section 8.3](#ch8)) for *recurring* windows; and the combination covers both "deploy tonight, do not page" and "this specific host is being rebuilt". The **Alertmanager UI** also shows the current routing tree and any alert's journey through it - when "the alert did not arrive", the tree view is the first diagnostic: did it match, which receiver won, is a silence or inhibition holding it?

High availability is built in: run two or three Alertmanagers, point every Prometheus at all of them, and they gossip alert state among themselves (`--cluster.peer`), deduplicating so exactly one notification goes out per group. The failure modes are honest: an Alertmanager that dies takes nothing with it - its peers already know everything - and a split cluster might double-send rather than lose a notification, which is the correct way for a paging system to fail.

## 8.6 The Alert Lifecycle in Practice

End to end, a production alert's journey: a counter's ratio crosses a threshold recorded by a rule ([Chapter 6](#ch6)), the alerting rule evaluates true twice (evaluation interval), enters Pending, survives its `for`, fires; Prometheus sends it to every configured Alertmanager; the Alertmanager groups it, waits `group_wait`, routes it by labels to a receiver; a human acknowledges, consults the runbook, fixes the cause; the expression goes false, the alert resolves, `send_resolved` closes the loop; `repeat_interval` would have re-paged had it stayed firing. Every stage of that pipeline is observable - `ALERTS` in Prometheus, the routing tree in Alertmanager, delivery state per receiver - and the failure diagnosis follows the same order: is the rule firing (Prometheus UI), did Alertmanager receive it (AM UI), did it route (tree view), did delivery succeed (receiver logs).

## 8.7 Lab 4: The Complete Alert Pipeline

::: {.lab}
### Lab 4 - From threshold to delivered notification {#lab4}

1. Add Alertmanager to the Compose stack (image `prom/alertmanager:v0.34.2`, port 9093) and wire it into `prometheus.yml`'s `alerting:` section with `promtool check config` before reload.
2. Write `TargetDown` (from [Section 8.1](#ch8)) with `for: 2m` and severity `critical`. Break the stack (`docker compose stop node-exporter`), watch the alert move Pending → firing in the UI, and graph `ALERTS{alertstate="firing"}`.
3. Configure a `webhook` receiver pointing at a listener (a one-line Python `http.server` POST logger is enough) and observe the JSON payloads: grouping, `startsAt`, `labels`, `annotations`. Add `send_resolved` and restart the target - then find the resolved payload.
4. Exercise routing: add a second alert (`ProbeDown` from [Lab 2](#lab2), severity `warning`), create child routes (critical → webhook A, warning → webhook B), and prove both deliveries. Then add an `inhibit_rule` (TargetDown inhibits warnings on the same instance), stop node_exporter *and* its probe target, and confirm only TargetDown notifies.
5. Practice the social tools: create a silence via `amtool` for the stopped target, confirm no notification while it burns, expire the silence, and verify the repeat behavior by shrinking `repeat_interval` to 1m for the experiment.
6. Close the loop: restore the stack, confirm both alerts resolve, and write the two-line runbook for `TargetDown` - the document you would have wanted while it was firing.
:::

**See also:** [Chapter 11](#ch11) for Grafana's unified alerting as the alternative surface, [Chapter 9](#ch9) for the dashboards that give a fired alert its context, and [Appendix C](#appC) when alerts do not arrive.
