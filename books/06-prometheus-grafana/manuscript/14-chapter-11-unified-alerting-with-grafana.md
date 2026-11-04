# Chapter 11 - Unified Alerting with Grafana {#ch11}

## 11.1 Two Alerting Stacks and When to Use Each

By now you operate one alerting pipeline - Prometheus rules to Alertmanager ([Chapter 8](#ch8)) - and Grafana ships a second one, **Grafana Alerting** (formerly unified alerting, the default since Grafana 9). Choosing between them is an architecture decision, so make it explicitly. The Prometheus path wins when: alerts must survive Grafana being down (rules evaluate in Prometheus), the estate already runs Alertmanager with tuned routing, and alert authors are PromQL-fluent. The Grafana path wins when: dashboards are the source of truth and the alert should be *the panel's query plus a threshold*, alerts span multiple data sources (a Prometheus metric AND an Elasticsearch count, or an SQL check), notification management should be central and UI-driven, and the team does not run Alertmanager at all.

The failure mode to avoid is running both by accident - a Prometheus-side rule and a Grafana-side rule for the same condition, two notification paths, two deduplication domains, one very confused on-call. A common and defensible hybrid: infrastructure and availability alerts in Prometheus/Alertmanager (close to the data, independent of dashboards), product and data-quality alerts in Grafana (close to the dashboards, multi-source, fast to author). Whatever you choose, write it down - one sentence in the runbook beats an archaeology dig at 3 a.m.

## 11.2 Alert Rules: Queries, Conditions, and Evaluation

A Grafana alert rule is built from **queries and expressions** evaluated per rule group. The default flow: one or more data source queries (A, B...), then server-side **expressions** - `Reduce` (collapse a range to a value: last, min, max, mean), `Math` (arithmetic across queries), `Threshold` (boolean compare) - and a condition that decides firing. A minimal rule: query `A` = `sum by (job) (rate(http_requests_total{status=~"5.."}[$__rate_interval]))`, expression `B` = Reduce A (Last), expression `C` = Threshold B (> 10). Rules evaluate on a schedule per **evaluation group** (interval, e.g. 1m), with a **pending period** - Grafana's `for` - before a firing transitions to notification, and each rule's **labels and annotations** use the same templating vocabulary as Alertmanager (`{{ $labels }}`, `{{ $values.B }}`).

Three settings prevent the classic Grafana-alerting surprises. **Evaluation behavior on missing data**: `No Data` state per rule - the safe default is *Alerting* for availability checks (the metric disappearing *is* the emergency) and *OK* or *Keep Last State* for trend metrics (a missing gauge is not a page). **Error handling**: what happens when the query errors (default keep-last-state; availability checks should alert). **Pending period**: Grafana evaluates per *rule*, not per *series*, by default - a query returning many series fires one alert per series unless reduced; use `Reduce` or label-aware queries deliberately, because a fleet-wide rule that fans out to 200 series is an Alertmanager-shaped job better done in Alertmanager.

::: {.warn}
**Watch out - $__rate_interval in alert rules**

Dashboard queries are evaluated per step across a graph range; alert queries are evaluated at discrete points in time. A query written against the dashboard's step behavior can behave differently at alert-evaluation cadence - the rate window and the evaluation interval must agree. Test every alert query in **Explore** at the alert's evaluation interval, not just in the panel it was copied from.
:::

## 11.3 Contact Points and Notification Policies

Grafana's notification model mirrors Alertmanager's concepts with different names. A **contact point** is a destination: email, Slack, PagerDuty, Opsgenie, webhook, Microsoft Teams, Telegram, and the generic webhook that integrates anything else; secrets live in the contact point (or, better, in provisioned YAML and a secret store). **Notification policies** are the routing tree: a default policy catches everything, child policies match labels (e.g. `team=payments`, `severity=critical`) with `continue matching` for fan-out, and each policy sets grouping, timing (`group wait`, `group interval`, `mute timings`), and its contact point. **Mute timings** are Grafana's time intervals - recurring windows like nights and weekends - and **silences** are the operator's manual mute, with the same semantics as Alertmanager's.

The workflow discipline from [Chapter 8](#ch8) transfers verbatim: `send_resolved` (Grafana defaults resolved notifications on for most integrations - verify yours), severity labels drive routing, runbook links in annotations, and a routing tree small enough to explain in one sentence. The one genuinely new mechanism is the **alert rule → notification → contact point audit trail** in the UI: when "the alert did not arrive", Grafana's alerting UI shows each rule's state history and each notification's delivery state per contact point - start there before touching configuration.

## 11.4 Provisioning Alerting Resources as Code

Alerting configuration belongs in Git with everything else, and Grafana provisions the three alerting resources from YAML at startup - the same pattern as data sources ([Chapter 9](#ch9)) and dashboards ([Chapter 10](#ch10)):

```yaml
# /etc/grafana/provisioning/alerting/rules.yml
apiVersion: 1
groups:
  - orgId: 1
    name: payments-health
    folder: Payments
    interval: 1m
    rules:
      - uid: payments-error-rate
        title: Payments error ratio high
        condition: C
        data:
          - refId: A
            relativeTimeRange: { from: 300, to: 0 }
            datasourceUid: prom
            model:
              expr: 'sum by (job) (rate(http_requests_total{job="payments",status=~"5.."}[5m])) / sum by (job) (rate(http_requests_total{job="payments"}[5m]))'
          - refId: C
            datasourceUid: __expr__
            model:
              type: threshold
              expression: A
              conditions:
                - evaluator: { type: gt, params: [0.01] }
        noDataState: Alerting
        execErrState: Alerting
        for: 2m
        labels: { severity: critical, team: payments }
        annotations:
          summary: "Payments error ratio {{ $values.A }} above 1%"
          runbook_url: "https://runbooks.example.com/payments-errors"
```

Contact points and notification policies provision from sibling files with the same `apiVersion: 1` shape. The estate that provisions dashboards ([Chapter 10](#ch10)) should provision alerting identically: the alert rule is code, reviewed like code, deployed like code, and the UI is the read/observe surface rather than the write surface - with Git Sync ([Chapter 10](#ch10)) covering the bidirectional cases where on-call fixes something in the UI at 3 a.m. and the commit lands without a manual step.

## 11.5 Recording Rules and the Grafana-Managed Prometheus Path

Grafana Alerting also includes a **recording rules** feature (writing computed series back to a Prometheus-compatible backend) and ships an embedded **Alertmanager-compatible** component (Grafana-managed alerts can route through an external Alertmanager). These matter at the edges: recording rules let a Grafana-authored computation feed dashboards and Prometheus-side alerts alike, and the external-Alertmanager bridge lets a Grafana-first estate keep its existing notification infrastructure. For the estate in this book - Prometheus evaluating recording rules ([Chapter 6](#ch6)), alerting rules ([Chapter 8](#ch8)), Grafana visualizing and adding multi-source product alerts - the guidance is: keep heavy fleet-wide evaluation in Prometheus, use Grafana recording rules for dashboard-local computations, and route everything through one notification layer with one owner.

## 11.6 Drill: A Multi-Source Alert, End to End

::: {.lab}
### Drill 3 - Grafana alerting drill (companion to [Lab 4](#lab4)) {#drill3}

1. In Grafana, create the `payments-error-ratio` rule from [Section 11.4](#ch11) *in the UI first* (query → Reduce → Threshold), set `for: 2m`, and break the payments job to watch Pending → Firing in the alert rules page. Fix it, and confirm the resolved notification.
2. Set `No Data` handling to Alerting, then stop the data source's network (or point the rule at a dead data source) to see the no-data state fire. Decide with a colleague which of your real rules deserve which no-data state, and write the decision down.
3. Create a Slack (or webhook) contact point, add a notification policy matching `severity=critical`, and verify delivery end to end - then add a mute timing for a pretend maintenance window and confirm suppression.
4. Convert the rule to provisioned YAML ([Section 11.4](#ch11)), restart Grafana, and confirm the UI shows the provisioned rule. Edit it in the UI, observe the read-only marker, and articulate the as-code contract.
5. Deliberately run the same condition in both stacks - the Grafana rule above *and* the Prometheus rule pattern from [Chapter 8](#ch8) - and observe the double notification. Then delete one and record which stack owns which alerts in your runbook. That artifact is the real deliverable of this drill.
:::

**See also:** [Chapter 8](#ch8) for the Alertmanager concepts this chapter mirrors, [Chapter 10](#ch10) for the as-code workflow, and [Appendix C](#appC) when notifications do not arrive.
