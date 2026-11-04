# Chapter 12 - Detection and Security Telemetry: Falco, Audit Logs, and Alerting {#ch12}

## 12.1 The Detection Gap

Every control in this book so far has a failure mode, and the failure mode is silent: the hook someone skipped with `--no-verify`, the dependency review dismissed in a hurry, the zero-day that predates its CVE, the phishing email that beat the OIDC gate with a human as the endpoint. Detection engineering exists for exactly this residue - and its metric is time. A breach detected in hours is an incident; the same breach detected in months is a disaster with a disclosure letter attached. The industry's own numbers (Mandiant's long-running M-Trends reports put the global median dwell time in the days-to-weeks range, and it has been falling *because* organizations instrument) make the point without needing a number from this book: **the half-life of an attack is detection speed**, and detection speed is a systems engineering problem that the observability books already taught you the tools for.

The good news for a reader of this series: `shopnow` already runs Prometheus, Alertmanager, and the Elastic Stack. This chapter does not build a parallel "security stack"; it feeds security events into the stack that exists, with the same three-tier discipline the metrics book taught - every event logged, most events visualized, a chosen few paging a human.

## 12.2 The Five Sources That Matter

Security telemetry in the `shopnow` stack comes from five sources, each answering a different "who did what":

1. **Falco** ([Chapter 9](#ch9)) - syscall-level events from the nodes: shells in containers, sensitive file reads, unexpected egress. The richest signal and the noisiest; its rules are the first place detection tuning happens.
2. **Kubernetes audit log** - the API server's record of every write (and optionally read): who created the RoleBinding, which identityexec'd into which pod, every admission rejection from [Chapter 8](#ch8). Enabled per cluster with a policy file; shipped like any other log.
3. **The cloud audit stream** (CloudTrail, Azure Activity Log, GCP Audit Logs) - everything the Terraform-applied infrastructure saw: the `AssumeRole` from CI, the new IAM policy, the security group change. The cloud books' audit setup is the reference; here it is a datasource.
4. **Vault's audit log** - every secret read and every lease issued ([Chapter 2](#ch2)); the answer to "who read the production database credentials this month" is a query, not an investigation.
5. **Application and edge logs** - nginx access logs (the DAST-relevant edge) and the app's own auth events (logins, permission denials), which the Elastic Stack book already ships and indexes.

All five share one property that makes them *security* telemetry rather than just logs: they are **append-only and integrity-mattered**. An attacker's first move is erasing the record, so these streams ship off-node immediately (Falco to the collector, audit logs to the log pipeline) into storage the workload's identity cannot write to - the WORM-style retention the Elastic book used for compliance data.

## 12.3 Wiring It Into the Existing Stack

The routing is deliberately boring. Falco streams events over its Falcosidekick bridge to two destinations at once: **Alertmanager** (via the Prometheus webhook) for the severities that page, and **Elasticsearch** for everything, where the two observability books' index templates and dashboards apply unchanged. The Kubernetes and cloud audit logs ride the existing log shippers into Elasticsearch under their own indices. One example makes the pattern concrete - the Falco rule from [Chapter 9](#ch9) reaching a human:

```yaml
# Alertmanager route: security signals page the on-call, others do not
route:
  receiver: security-pager
  matchers:
    - severity = "security-critical"
  group_wait: 30s
  repeat_interval: 4h
```

The corresponding Prometheus alert rule (or Falcosidekick's direct Alertmanager output) tags shell-in-container, audit-log-disabled, and admission-webhook-down as `security-critical`; everything else lands in Elasticsearch with a 90-day retention and a dashboard. The design principle is the series' severity philosophy applied to security: **page on compromise evidence, record on everything else** - a shell in a distroless container pages (it is evidence), a first-time permission-denied logs (it is a signal), and the difference between the two lists is what detection engineering actually is.

## 12.4 Dashboards, Triage, and the Weekly Review

Detection that nobody reads is decoration. The working cadence has three artifacts. A **security overview dashboard** (Grafana or Kibana, whichever the team lives in): events by rule over time, admission rejections by policy and namespace, identity sources of API writes, Vault secret reads by role, and Falco events by node - each panel a question the team actually asks. A **triage workflow**: every `security-critical` page goes through the incident path of [Chapter 13](#ch13); every non-critical finding lands in a weekly triage review whose only outputs are *tune the rule*, *fix the finding*, or *accept with a reason* - the same three outcomes as every other alert in the series. And a **detection metric**: false-positive rate per rule and mean time from event to triage, reviewed monthly, because rules decay - an app change turns yesterday's anomaly into today's noise, and a noisy rule that survives its fourth review gets rewritten or retired.

::: {.note}
**Best practice - log the denials, they are the interesting part**

Success logs tell you the system works; *denial* logs tell you what is trying it. The admission rejections from [Chapter 8](#ch8), the RBAC denials in the audit log, the 403s at the edge, the Vault `permission denied` entries - each is either an engineering mistake worth fixing (someone is blocked by a policy that needs a review) or reconnaissance worth knowing about (something is probing the boundary). Both are valuable; neither is visible unless denials are first-class, indexed, and counted on the dashboard like the successes are.
:::

**See also:** [Chapter 13](#ch13) takes over when a page is real; the Prometheus & Grafana and Elastic Stack books remain the full reference for the pipelines, retention, and dashboard craft this chapter builds on; [Chapter 15](#ch15) tests the whole detection chain by attacking it.
