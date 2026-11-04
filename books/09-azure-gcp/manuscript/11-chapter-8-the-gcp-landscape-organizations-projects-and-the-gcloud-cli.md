# Chapter 8 - The GCP Landscape: Organizations, Projects, and the gcloud CLI {#ch8}

## 8.1 Projects: The Unit Everything Belongs To

Google Cloud's hierarchy is shorter than Azure's and built around a different atom. At the top sit the **organization** and its **folders** - the AWS Organizations analog - and below them, the **project**: the unit that owns every resource, every quota, every IAM policy, and every bill. Where AWS draws the boundary at the account and Azure at the subscription, GCP draws it at the project - and projects are *cheap*: creating one takes seconds and costs nothing, so the AWS multi-account discipline (environment per account, prod isolated from labs) becomes the GCP multi-project discipline with none of the account-creation ceremony. Every resource the running example creates lives in a project like `shopnow-dev`, and the hierarchy looks like this:

```
example-org.com               (organization)
└── platform                  (folder)
    ├── shopnow-dev           (project: labs, experiments)
    ├── shopnow-staging       (project: pre-prod)
    └── shopnow-prod          (project: production)
```

Every project carries three names, and the distinction is the first gotcha of the platform. The **project ID** - globally unique, immutable, usually `-dev`/`-prod` suffixed - is what every command and every API wants. The **project number** is the internal numeric identifier that shows up in identity strings. The **project name** is a friendly label that is *not* an identifier and is not what you type into the CLI.

::: {.warn}
**Watch out - the CLI wants the project ID, not the name**

`gcloud run deploy --project shopnow` fails with a confusing "Project 'shopnow' not found" when `shopnow` is the display name and the real ID is `shopnow-prod-eu`. The reflex that prevents it: `gcloud projects list --format='table(project_id, name, project_number)'` before you start, and always quote the leftmost column.
:::

## 8.2 Regions, Zones, and the Honest Map

A **region** is a geography (`europe-west3` is Frankfurt, sitting next door to the Frankfurt examples of the two previous cloud books), and inside it, **zones** - `europe-west3-a`, `-b`, `-c` - are physical datacenter clusters. Zone names mean the same physical place for every customer, which makes outage postmortems shareable in a way AWS's per-account letter-shuffling is not; GCP even publishes per-zone capacity and lets you check which zones your quotas live in. Services are **regional** (most managed products), **zonal** (Compute Engine instances, which you spread deliberately), or **global** (the load balancer family and a few others) - and the service model, not the console's tab order, is what tells you where a thing lives. The same region-consistency rule as the last two clouds applies: a resource created in `europe-west3` is invisible to a CLI pointed at `europe-west1`, and all GCP examples in this book use `europe-west3`.

## 8.3 gcloud: Install, Init, and the Configuration Habit

The **gcloud CLI** is the steering wheel, with the same "console for looking, CLI for doing" contract as `az` and `aws`. `gcloud init` walks through sign-in, project, and default region/zone; `gcloud auth login` re-authenticates; `gcloud config list` shows the working defaults. What maps to AWS named profiles is **configurations** - named bundles of project, region, and account you switch between explicitly:

```bash
gcloud init                                    # first-time: auth + project + defaults
gcloud config configurations create shopnow-dev
gcloud config set project shopnow-dev-eu
gcloud config set compute/region europe-west3
gcloud config configurations activate shopnow-dev

gcloud auth list                               # which identities are known to gcloud
gcloud components update                       # the CLI self-updates in place
```

Two flag families appear on every command and are worth learning once. `--project` overrides the configuration for a single command. And the output family is `--format` with its own grammar - `--format=json`, `--format='table(id, name)'`, `--format='value(project_id)'` - plus `--filter` for server-side selection (`--filter="state:RUNNING"`), which replaces the JMESPath `--query` habit of the two previous CLIs rather than translating it. **Cloud Shell** (the terminal icon in the console) is the pre-authenticated browser shell with `gcloud` current, and it fills the same "zero-install follow-along" role as it did on AWS and Azure.

::: {.note}
**Best practice - learn `--format` and `--filter` as one pattern, not fifty**

Every gcloud command is the same API with the same selection grammar: `gcloud compute instances list --filter="labels.env=dev AND status=RUNNING" --format="table(name, zone, machineType.machineType)"` reads like the `describe + query + loop` pattern of the AWS book with different punctuation. Appendix B collects the invocations that recur across this book into a desk reference, exactly as the AWS volume's Appendix A did.
:::

## 8.4 Billing: The Account, the Project Link, and the First Budget

Billing separates cleanly: a **billing account** (the payment instrument) is *linked* to projects, and one account can serve many projects - which makes moving a project between billing accounts a supported operation rather than a migration. Day one, before the first resource, set the budget: Cost Management budgets live on the billing account or on a project, alert at threshold percentages (50/90/100% is a sane start), and can publish to a Pub/Sub topic for automation. The CLI path needs the billing account ID from `gcloud billing accounts list`:

```bash
gcloud billing budgets create \
  --billing-account=<billing-account-id> \
  --display-name=budget-shopnow-dev \
  --budget-amount=10USD \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```

::: {.warn}
**Watch out - a budget alerts; it does not enforce**

The same rule as the two clouds before: a budget is a sensor, not a brake. The enforcement layer on GCP is org policy (deny expensive SKUs), quotas, and the project-per-environment discipline that makes `gcloud projects delete shopnow-lab-eu` the cleanup button. Every lab in this book ends with that delete for the same reason the AWS and Azure labs did.
:::

## 8.5 The Running Example, Re-Planned for GCP

The map for Part II mirrors Part I so the deltas stay in focus: identity and federation ([Chapter 9](#ch9)), a network and virtual machines with real autoscaling ([Chapter 10](#ch10)), object storage and a managed PostgreSQL ([Chapter 11](#ch11)), Kubernetes on GKE Autopilot ([Chapter 12](#ch12)), containers without clusters on Cloud Run ([Chapter 13](#ch13)), the keyless pipeline ([Chapter 14](#ch14)) - and then the two chapters no single-cloud book could write: the capstone that runs shopnow on AWS, Azure, and GCP side by side ([Chapter 15](#ch15)), and the decision framework that says when any of this is worth it ([Chapter 16](#ch16)).

**See also:** [Chapter 9](#ch9) builds the permission system every gcloud call in this chapter leaned on, and [Chapter 10](#ch10) turns projects into networks and machines.
