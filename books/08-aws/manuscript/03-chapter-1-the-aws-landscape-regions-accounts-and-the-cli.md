# Chapter 1 - The AWS Landscape: Regions, Accounts, and the CLI {#ch1}

## 1.1 The Map: Regions, Availability Zones, and Edge Locations

Everything in this book happens inside a hierarchy that most engineers use daily but rarely name precisely. A **Region** is a physical geography - `us-east-1` is Northern Virginia, `eu-central-1` is Frankfurt, `ap-southeast-2` is Sydney - containing two or more (today usually three or more) **Availability Zones**. An AZ is one or more data centers with independent power, cooling, and networking, close enough to other AZs for single-digit-millisecond latency, far enough that a flood or grid failure does not take out two at once. AWS exposes AZs as names like `us-east-1a`, and quietly shuffles which physical AZ each letter maps to per account so that `1a` is not the same building for everyone - a detail that matters when a colleague quotes an AZ-specific issue. **Edge locations** form the outer ring: the points of presence that CloudFront (the CDN) and Route 53 (DNS) run from, so that static content and name resolution terminate close to users rather than in the Region.

Two design rules follow from the map, and both appear repeatedly through the book. First, *an AZ is the unit of failure, a Region is the unit of blast radius*: high availability means distributing across AZs ([Chapter 4](#ch4) spreads subnets, [Chapter 6](#ch6) fails over databases, [Chapter 7](#ch7) spreads Kubernetes nodes), while disaster recovery means thinking across Regions - a concern this book touches but does not drill. Second, *not every service exists in every Region, and prices differ between Regions*: before a launch is designed around a capability, `aws ec2 describe-regions` and the Region-specific service page are worth thirty seconds. All examples in this book use `eu-central-1`; substitute your Region consistently, because a resource created in one Region is invisible to the CLI pointed at another - the single most common "it disappeared!" false alarm in AWS.

## 1.2 The Account and Its Guardrails

An AWS account is a billing and isolation boundary, identified by a 12-digit account ID. Inside it, the **root user** is the email address that created the account: it can do literally anything, including things no other identity can, such as closing the account. The professional reflex is to touch root approximately twice - to set up the first administrative identity and to enable MFA on root itself - and never log in with it again. Real human access goes through **IAM Identity Center**, which federates named users into accounts with permission sets, and real programmatic access goes through **roles**, not long-lived keys; both are the business of [Chapter 2](#ch2). Organizations running many accounts put them under **AWS Organizations**, where Service Control Policies set the guardrails no identity inside can exceed - the reason a company's SCP is why your `us-east-1` instance launch fails no matter how correct your IAM policy is.

One administrative habit belongs in week one because every later chapter depends on it: tag discipline. Every resource this book creates carries tags like `project`, `owner`, and `env`, because tags are how cost reporting ([Chapter 12](#ch12)) and cleanup scripts tell your experiments from your production.

## 1.3 The Free Allowance and the First Billing Alarm

New accounts get a free allowance - a credits-based free plan for recent signups plus always-free service tiers - and the exact shape of that offer changes often enough that this book deliberately does not copy the numbers: read the official Free Tier page once, then let a billing alarm enforce it. What does not change is the reflex that matters: *budget visibility from day one*. The cheapest lesson in AWS is setting an alarm before running anything, not after the first surprise. Chapter 10 wires alarms properly with SNS; here is the two-minute version using the CLI and Cost Explorer's metric, creating an alarm that fires when estimated charges pass ten dollars:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name billing-over-10-usd \
  --namespace AWS/Billing \
  --metric-name EstimatedCharges \
  --dimensions Name=Currency,Value=USD \
  --statistic Maximum --period 21600 --evaluation-periods 1 \
  --threshold 10 --comparison-operator GreaterThanThreshold \
  --alarm-actions <your-notify-topic-or-email-hook>
```

::: {.warn}
**Watch out - the billing alarm is not a spending limit**

AWS bills first and alerts second: an alarm sends a notification when estimated charges cross the threshold, but nothing stops the meter. The real guards are budgets with alert actions ([Chapter 12](#ch12)), SCPs that deny expensive resource types, and deleting what you are not using. Every lab in this book ends with an explicit cleanup step for exactly this reason.
:::

## 1.4 Installing and Configuring the AWS CLI

The **AWS CLI v2** is the book's steering wheel: the console is for looking, the CLI is for doing, and Terraform in [Chapter 11](#ch11) is the CLI's opinionated older sibling. Install it for your platform (the AWS docs own the moving details - package managers, installers, and the v1-to-v2 story), then verify:

```bash
aws --version        # aws-cli/2.x.x Python/3.x ... - the v2 line is what this book uses
aws configure
```

`aws configure` asks four questions and writes them to `~/.aws/credentials` and `~/.aws/config`: an **access key ID** and **secret access key** (for now, the keys of your admin user - [Chapter 2](#ch2) replaces this habit with roles and Identity Center), a **default Region** (`eu-central-1` in this book), and an output format (`json` - machine-readable, pipe-able, and what every example assumes). The keys are *secrets*: they authenticate any API call you could make, so they never go into code, dotfiles committed to git, or CI variables when a role can do the job ([Chapter 9](#ch9) is built on that principle).

Immediately after `aws configure`, prove the plumbing end to end with the identity check you will use for the rest of your career:

```bash
aws sts get-caller-identity
```

The response shows the account, the principal ARN, and the user or role you are acting as. Half of all "why can't I delete this?" mysteries end here, at the discovery that the terminal is pointed at the wrong account or profile.

## 1.5 Profiles, Output, and the CLI as a Contract

Real work means several identities - personal admin, a work account, a CI role - and **named profiles** keep them apart:

```ini
# ~/.aws/credentials
[default]
aws_access_key_id     = AKIA...
aws_secret_access_key = ...

[personal]
aws_access_key_id     = AKIA...
aws_secret_access_key = ...
```

```bash
aws sts get-caller-identity --profile personal   # one-off
export AWS_PROFILE=personal                      # or for the whole shell
export AWS_DEFAULT_REGION=eu-central-1           # region without re-running configure
```

Two flags turn the CLI from a page of JSON into a tool. `--output json|table|text` chooses the shape - `json` for piping into `jq`, `table` for humans, `text` for shell loops - and `--query` filters server responses with JMESPath before they print:

```bash
aws ec2 describe-instances \
  --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType]' \
  --output table
```

Every chapter's examples lean on exactly this pattern: describe, query, loop. Appendix A collects the invocations that recur most into a desk-reference cheat sheet.

::: {.note}
**Best practice - treat CLI output as an API, not a text stream**

The AWS CLI is a thin wrapper over the same API the console uses: nothing is hidden, nothing is magic, and `--debug` will show you the signed request it sent. When the console shows a setting you do not recognize, the fastest way to understand it is usually to `describe` the resource from the CLI and read the raw fields - and when a console action seems unscriptable, check the CLI reference, because it almost never is.
:::

## 1.6 Console, CloudShell, and the Running Example

The **Management Console** earns its keep for discovery and review: the VPC resource map, the Cost Explorer charts, the IAM policy editor with its visual condition builder. **CloudShell** - the terminal icon in the console - is a pre-authenticated CLI in a browser, which makes it the zero-install path for following along and the natural place to run one-off cleanup sweeps from a colleague's machine. The two surfaces are the same control plane; fluency means moving between them without thinking.

The book's running example starts here and grows one service per chapter: a small web platform called **shopnow**, consisting of a couple of web servers (EC2, [Chapter 3](#ch3)) in a custom network (VPC, [Chapter 4](#ch4)), static assets on object storage (S3, [Chapter 5](#ch5)), a PostgreSQL database (RDS, [Chapter 6](#ch6)), a Kubernetes deployment (EKS, [Chapter 7](#ch7)), a few serverless glue functions (Lambda, [Chapter 8](#ch8)), a deploy pipeline (GitHub Actions, [Chapter 9](#ch9)), dashboards and alarms (CloudWatch, [Chapter 10](#ch10)), Terraform definitions (Chapter 11), and a budget (Chapter 12). Each chapter adds one layer with the previous layers in place - which is how real platforms grow, and why the labs chain instead of standing alone.

**See also:** [Chapter 2](#ch2) builds the identity and permission system that every CLI call in this chapter silently leaned on, and [Chapter 3](#ch3) launches the first real compute of the running example.
