# Chapter 12 - Cost Management and Governance {#ch12}

## 12.1 How AWS Charges: The Four Levers

AWS billing is line-item honest: every service prices a small set of units, and the bill is the sum. Four levers cover nearly everything. **Compute time** - instance hours ([Chapter 3](#ch3)), Lambda GB-seconds ([Chapter 8](#ch8)), EKS control-plane hours ([Chapter 7](#ch7)). **Storage** - GB-months of EBS, S3 classes ([Chapter 5](#ch5)), RDS storage. **Requests** - API calls, S3 operations, Lambda invocations. **Data transfer** - the lever that behaves differently from the others: inbound is free, outbound to the internet is priced per GB, *and traffic between Availability Zones is charged both ways* - the fact behind more surprise bills than any other single line. Every optimization in this chapter is one of these four levers being pulled with a script instead of a hand.

The mental shift that makes costs manageable: the bill is a *time series*, not an invoice. Treated like a metric (it is one - Cost Explorer and the `AWS/Billing` namespace), it gets the same treatment as latency and errors: baselines, alarms, and anomaly review. Treated like a monthly surprise, it gets neither.

## 12.2 Pricing Models: On-Demand, Spot, Savings Plans

Chapter 3 introduced the three compute prices; the platform-level strategy is a portfolio. **On-Demand** is the reference price and the right cost for genuinely variable load. **Spot** (up to ~90% off) belongs on the interruptible middle: batch workers, stateless autoscaling groups, spot-backed EKS node groups ([Chapter 7](#ch7)). **Savings Plans** commit spend for one or three years at double-digit discounts and cover the *steady floor* - the baseline that is running regardless of traffic; **Reserved Instances** are the older, resource-specific equivalent, still common and still effective for databases. The portfolio rule: commit to what a year of history says never turns off, spot what survives interruption, and on-demand the rest. A first Savings Plan sized to the *minimum* historical hourly spend is the safe opening bid - under-committing is a missed discount, over-committing is a lock.

## 12.3 Seeing the Bill: Cost Explorer, Tags, and the CUR

**Cost Explorer** is the bill's time series: daily or monthly spend by service, by tag, by Region, with forecasts. The view that changes behavior is **group by tag** - which is why [Chapter 1](#ch1)'s tag discipline and [Chapter 11](#ch11)'s `default_tags` were not hygiene theater: `project=shopnow` versus `env=dev` turns "why did the bill grow?" into a two-click answer. Cost allocation tags must be *activated* in the billing console before they appear in Cost Explorer, a one-time per-tag step teams always discover a month late. Behind Cost Explorer sits the **Cost and Usage Report (CUR)** - the raw line-item data set delivered to S3, queryable with Athena when a team outgrows the console views; most teams do not need it in year one and are glad it exists in year three.

```bash
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=TAG,Key=project
```

## 12.4 Budgets and the Alerting Habit

**AWS Budgets** is the enforcement layer over the visibility: a budget tracks cost (or usage, or coverage) against a threshold and fires alerts - email, SNS, and an EventBridge event that can trigger anything ([Chapter 10](#ch10)'s bus again). The working pattern is three budgets per platform: a monthly total budget at 80/100%, a per-environment budget so `dev` cannot silently eat `prod`'s headroom, and a *forecast* budget that alerts when the trend says the month will overshoot - early warnings beat accurate postmortems.

```bash
aws budgets create-budget \
  --account-id 111122223333 \
  --budget '{
    "BudgetName": "shopnow-monthly",
    "BudgetLimit": { "Amount": "200", "Unit": "USD" },
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[{
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80
    },
    "Subscribers": [{ "SubscriptionType": "EMAIL", "Address": "ops@example.com" }]
  }]'
```

## 12.5 The Classic Surprises: Where Bills Actually Grow

Every platform team meets the same five lines eventually; meeting them in print is cheaper. **NAT gateway data processing** ([Chapter 4](#ch4)): per-GB pricing turns chatty workloads - container pulls, S3 transfers, logging firehoses - into the top line item; the fixes were Section 4.5's endpoints, and the check is Cost Explorer grouped by usage type, searching for `NatGateway-Bytes`. **Cross-AZ traffic**: pods on nodes in AZ-a talking to a database replica in AZ-b pay both directions; topology-aware routing ([Chapter 7](#ch7)'s controller annotations, RDS Multi-AZ in the same AZs as consumers where practical) is the fix. **Idle EBS and Elastic IPs**: unattached volumes and unassociated EIPs bill forever and are invisible in every dashboard that is not looking for them - a monthly cleanup script (find, verify by tag, delete) is the whole policy. **Forgotten non-production**: the dev cluster that runs nights and weekends costs full price for nothing; scheduled shutdown of dev environments (EventBridge rule from [Chapter 10](#ch10) at 20:00, another at 07:00) routinely cuts a third of a dev bill. **Log and snapshot sprawl**: the retention defaults of [Chapter 5](#ch5) and [Chapter 10](#ch10) exist precisely because unbounded growth is the default state of stored things.

::: {.warn}
**Watch out - "it was only a t4g.micro"**

Cost surprises are almost never one big resource; they are many small ones that outlived their reason. The failed lab's instance, the test NAT gateway, the second EKS cluster from an experiment in March. This is why every lab in this book ends with cleanup, why tags include `env` and `owner`, and why the monthly review in Section 12.6 is a calendar item, not an intention.
:::

## 12.6 A Rightsizing Routine

Rightsizing is a recurring review, not a project. The monthly loop: **find** the top 20 resources by cost (Cost Explorer, grouped by resource); **check utilization** against reality - CloudWatch metrics from [Chapter 10](#ch10) say whether the `m7g.large` has ever crossed 20% CPU, Compute Optimizer (a free AWS service) suggests sizes from the same data; **act** on the boring wins - downsize the idle, gp2→gp3 the volumes (same performance class, lower price, zero migration for most cases), delete the unattached, schedule the non-production, right-size the Lambda memory (Section 8.3's power tuning); **record** what changed so next month's delta is attributable. Thirty minutes a month, automated to the extent [Chapter 11](#ch11) allows, keeps the bill honest without a FinOps team.

## 12.7 Governance: Making Good Choices the Default

The end state of this chapter is architectural, not vigilance. **Tag policies** and SCPs ([Chapter 2](#ch2)) make untagged resources hard to create; **budgets** make overspend visible within a day; **the OIDC pipeline** ([Chapter 9](#ch9)) and **Terraform** ([Chapter 11](#ch11)) mean resources are born with tags and owners by construction; and the **rightsizing calendar** keeps the portfolio honest as workloads change. Governance done well is invisible - the engineer who needs a database finds the standard module, gets the standard tags, runs on the standard schedule, and the bill that arrives at month end is the one the dashboards predicted. That is the whole book's arc in its final chapter: the platform is not a pile of consoles; it is a system that makes the right thing the easy thing.

**See also:** [Appendix C](#appC) collects the cost-symptom troubleshooting entries (the surprise NAT bill, the orphaned ALB), and the *Terraform for DevOps Engineers* volume's modules are where Section 12.7's standards live as code.
