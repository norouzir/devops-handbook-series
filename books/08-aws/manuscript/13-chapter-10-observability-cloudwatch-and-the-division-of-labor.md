# Chapter 10 - Observability: CloudWatch and the Division of Labor {#ch10}

## 10.1 The Observability Surfaces of AWS

AWS services emit telemetry whether or not you look at it, and **CloudWatch** is where it lands: **metrics** (numeric time series from every service), **logs** (the log platform, with its own query language), **alarms** (threshold and anomaly rules that act on metrics), **events** (the EventBridge bus that reacts to state changes), and **dashboards** (the assembly layer). The chapter's goal is not a tour but a working setup: the specific metrics worth alarming on for the services this book built, the log hygiene that keeps costs sane, and an honest answer to the question every team that runs both stacks eventually asks - *what belongs in CloudWatch, and what belongs in the Prometheus/Grafana stack from the series' earlier volume?*

The division of labor stated up front: **CloudWatch is the control plane's observability** - it sees what AWS services are doing (RDS lag, Lambda errors, EKS control plane health, the bill itself) because it is inside AWS, with no scraping, no agents for service metrics, and IAM-gated access. **Prometheus and Grafana are the workload's observability** - they see inside your containers and application code (request rates, histograms, business metrics) because they scrape your instrumentation, and Grafana renders both worlds side by side. Teams that fight this boundary pay twice; teams that respect it get each tool where it is strongest.

## 10.2 Metrics: Namespaces, Dimensions, and Statistics

Every metric lives in a **namespace** (`AWS/EC2`, `AWS/RDS`, `AWS/Lambda`, or your own like `Shopnow`), identified by a **metric name** and labeled by **dimensions** - key/value pairs such as `InstanceId` or `FunctionName` that slice one metric into many series. Statistics aggregate over a **period**: `SampleCount`, `Average`, `Sum`, `Maximum`, percentiles. The model's sharp edge is *retention and granularity*: metrics finer than an hour fade over time (1-second points survive 3 hours, 5-minute points 15 days, and beyond an hour only aggregates survive the year), so anything you will want at fine resolution next quarter must be exported (Section 10.4's subscription filters to S3, or the metrics' own long-term home).

Custom metrics come from your code, and the modern path is **Embedded Metric Format**: your application logs structured JSON, and CloudWatch extracts the metrics automatically - metrics without a metrics API call:

```bash
# What is the platform's database actually doing right now?
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=shopnow-db \
  --start-time "$(date -u -d '1 hour ago' +%FT%TZ)" \
  --end-time "$(date -u +%FT%TZ)" \
  --period 300 --statistic Average --output table
```

The EKS cluster's workload metrics mostly bypass CloudWatch (Prometheus's territory), but two CloudWatch-native sources matter regardless: the control plane's own health metrics, and the **Container Insights** agent for node/pod resource views - a pragmatic complement, not a replacement, for the Prometheus stack.

## 10.3 Alarms: Thresholds, Anomaly Detection, and Actions

An **alarm** watches one metric over one statistic and transitions between `OK`, `ALARM`, and `INSUFFICIENT_DATA`; its `alarm-actions` target an **SNS topic** (which fans out to email, webhooks, or mobile push) or, more powerfully, an auto-scaling or recovery action. Two alarm kinds cover most needs. **Static thresholds** are the workhorse - and the craft is choosing metrics that fail *before* users do: disk free space trending down, RDS freeable memory, SQS queue age, Lambda `Errors` and `Throttles`:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name shopnow-db-low-storage \
  --namespace AWS/RDS --metric-name FreeStorageSpace \
  --dimensions Name=DBInstanceIdentifier,Value=shopnow-db \
  --statistic Average --period 300 --evaluation-periods 2 \
  --threshold 5368709120 --comparison-operator LessThanThreshold \
  --alarm-actions arn:aws:sns:eu-central-1:111122223333:platform-alerts
```

**Anomaly detection alarms** learn a metric's seasonal band (a workload that spikes at 09:00 daily is normal at 09:00 and an incident at 03:00) and alarm on band breaches - the right tool for traffic-shaped metrics where a fixed threshold is either noisy or blind. The alarm discipline that keeps the on-call sane: every alarm must be *actionable* (a runbook line in its name or description), every alarm must have an owner, and an alarm that fires twice with no action gets deleted or fixed - noisy monitors are how real signals get ignored.

::: {.note}
**Best practice - the billing alarm is an observability requirement**

Chapter 1 set a two-minute billing alarm; a production account deserves the full treatment: a Cost Explorer-based alarm on actual spend, a forecast alarm, and an EventBridge rule for budget breaches ([Chapter 12](#ch12) builds the budget side). A surprise bill is an incident - it belongs in the same pipeline as latency and errors, not in a monthly email.
:::

## 10.4 Logs: Groups, Streams, Retention, and Insights

CloudWatch Logs organizes into **log groups** (typically per application or service), each holding **log streams** (per source - an instance, a Lambda execution environment) of timestamped events. Sources flow in automatically where they are born (Lambda writes its own; RDS exports database logs you enable; CloudTrail ships audit logs) and are collected from EC2/EKS by the CloudWatch agent or Fluent Bit. The one setting that decides whether logs are a tool or a bill: **retention**. Log groups default to *never expire* - the default is a slow-motion cost leak, and the professional baseline is explicit retention per group (30 days operational, 90-365 days audit, Glacier-class archives in S3 for the long tail):

```bash
aws logs put-retention-policy --log-group-name /aws/lambda/shopnow-hello --retention-in-days 30
aws logs tail /aws/lambda/shopnow-hello --since 10m --filter-pattern "ERROR"
```

**CloudWatch Logs Insights** is the query layer: a piped, SQL-flavored language over log groups (`fields @timestamp, @message | filter level = "ERROR" | stats count() by bin(5m)`), good enough that many teams' first log-search tool is CloudWatch rather than the Elastic Stack - and when the *Elastic Stack* volume's search-and-analyze power is what you need, the **subscription filter** is the bridge: CloudWatch streams matching log events to Lambda, Kinesis, or Firehose, which lands them in Elasticsearch. The two stacks compose instead of compete.

## 10.5 EventBridge: The Event Bus That Glues the Platform

**EventBridge** (the renamed CloudWatch Events) is a bus of JSON events from AWS services, your applications, and SaaS partners, with rules that route patterns to targets. Two patterns earn their place in every platform. **Scheduled rules** are cron (Section 8.5 used one to trigger the nightly report). **Service-event rules** react to state changes without polling: an RDS failover event posts to the alert channel, an ECR image push triggers a staging deploy, a GuardDuty finding opens a ticket. The design shift is from "poll everything, hope" to "subscribe to what matters" - and it composes with the alarms of Section 10.3: alarms publish to SNS, SNS targets include EventBridge, and one alert path serves both human and machine consumers.

## 10.6 Dashboards and X-Ray: The Assembly and the Deep Dive

**Dashboards** assemble the cross-service view that no single service's console provides: the shopnow board shows the ALB's p99 and 5xx rate, the EKS nodes' CPU, RDS connections and lag, Lambda errors and throttles, and the month-to-date spend widget - one screen, one incident channel. Build them in code (the dashboard is a JSON document; [Chapter 11](#ch11) keeps it in Terraform like everything else). **X-Ray** adds distributed tracing for the cases where metrics say *slow* but not *where*: instrument the application (the X-Ray SDK or OpenTelemetry - the latter is the strategic choice), and traces follow a request across API Gateway, Lambda, and the database, segment by segment. The observability ladder this book teaches stands on the series' earlier volumes: *metrics tell you where to look, logs tell you what you are looking at* (Prometheus/Grafana and Elastic Stack), and *traces tell you the path between* - X-Ray or OpenTelemetry in AWS.

**See also:** [Chapter 9](#ch9)'s pipeline deploys the instrumentation changes this chapter requests, [Chapter 12](#ch12) turns the cost dashboards into governance, and the *Prometheus & Grafana* volume owns the workload-metrics stack this chapter deliberately did not duplicate.
