# Chapter 6 - Azure Functions and Container Apps: The Serverless Toolbox {#ch6}

## 6.1 The Serverless Ladder

The AWS book's Lambda chapter solved a class of problem - small, event-shaped pieces of logic that should not own a server - and Azure solves it with a ladder rather than a single product. **Azure Functions** runs code: you deploy a function, the platform manages everything, and events come to you. **Container Apps** runs containers: a full HTTP service or background worker, packaged as an image, scaled by the platform, with no cluster to run. **AKS** runs clusters, for when you want the control of [Chapter 5](#ch5). Choosing is choosing by *unit of deployment* - function, container, cluster - and the ladder is walked in both directions more often than newcomers expect.

## 6.2 Azure Functions: Triggers, Bindings, and Plans

The Functions model is theLambda event model taken one step further: a **trigger** starts the function (HTTP request, Queue storage message, timer, Event Grid event, Service Bus message), and **bindings** wire inputs and outputs to services declaratively - a function that reads a queue and writes a blob declares both connections in configuration, not in code. The runtimes track mainstream versions (Python 3.12, Node 20, .NET as of this writing; the runtime-rotation discipline from the Lambda chapter applies identically), and the local loop is the **Azure Functions Core Tools**: `func init` scaffolds, `func start` runs against real local emulators, and `func azure functionapp publish` ships - though the pipeline in [Chapter 7](#ch7) replaces that with the CLI.

The plan you pick decides the behavior more than the code does. **Flex Consumption** is the modern default: per-execution billing, fast scale to zero *and* back, VNet integration, and instance-level control over concurrency. The older **Premium** plan (pre-warmed instances) and **Dedicated** (an App Service plan) remain for legacy postures. Creation and deployment are two commands away from a running HTTP endpoint:

```bash
az functionapp create \
  -g rg-shopnow-dev -n func-shopnow-webhook \
  --storage-account stshopnowdev \
  --flexconsumption-location westeurope \
  --runtime python --runtime-version 3.12 \
  --functions-version 4
```

Functions also carries a capability Lambda never grew: **Durable Functions**, an in-platform orchestrator for stateful, multi-step workflows (fan-out, human-in-the-loop, retries with state) - Azure's built-in answer to what the AWS book bolted on with Step Functions, and the reason "just a function" projects on Azure often stay on Functions longer.

**Deployment slots** round out the operational story: a `staging` slot receives the new version, warms up, and swaps into production in seconds - and the swap *back* is the rollback. Slots exist on Functions and on App Service; Container Apps expresses the same idea as revisions, which is the next section.

## 6.3 Container Apps: Containers Without a Cluster

**Container Apps** is what you get when the unit of deployment is a container but the unit of operations is *none*: a fully managed environment built on Kubernetes and Knative where you bring an image and the platform brings scaling, ingress, TLS, revisions, and scale-to-zero. The **environment** is the shared boundary (one VNet, one Log Analytics workspace), and each **container app** is a service with **revisions** - every configuration change freezes into a revision you can route traffic to, split, or roll back to, exactly the mechanism [Chapter 13](#ch13) presents as Cloud Run's superpower. Scaling is **KEDA**-based: HTTP concurrency by default, queue depth, CPU, or custom metrics on demand, with `minReplicas: 0` making the scale-to-zero story real and `minReplicas: 1` turning it off:

```bash
az containerapp env create \
  -g rg-shopnow-dev -n cae-shopnow -l westeurope

az containerapp create \
  -g rg-shopnow-dev -n shopnow-api --environment cae-shopnow \
  --image acrshopnowdev.azurecr.io/shopnow/api:v1 \
  --target-port 8080 --ingress external \
  --min-replicas 0 --max-replicas 10
```

Identity carries over from [Chapter 2](#ch2) unchanged: assign a user-assigned managed identity with `--user-assigned`, and the app talks to storage and databases with no secrets - the same `DefaultAzureCredential` code as the VM and the AKS pod. **Jobs** (the batch sibling of apps) run to completion on a schedule or event, covering the cron-and-queue workload class.

## 6.4 Choosing: Function, Container App, or Cluster

The honest decision procedure is short. A discrete event-shaped handler with business logic in a single language - webhook, queue processor, nightly report - is a **Function**; a real HTTP service or worker that already has a Dockerfile (and shopnow's API has had one since the Docker book) is a **Container App**; a platform for many services with team-owned configuration, service mesh ambitions, or strict network topology is **AKS**. Two migrations are cheap: Functions grow into Container Apps when one function becomes a service; Container Apps' manifests translate to AKS concepts when a platform team forms. The expensive migration is the reverse, which is why starting one rung too low on control beats starting one rung too high.

::: {.warn}
**Watch out - cold starts are a plan and a design decision, not a footnote**

Scale-to-zero is a cost tool with a latency bill: the first request after idle pays cold start on Flex Consumption and on `minReplicas: 0` Container Apps alike. The fixes are the same on both clouds and worth writing down now - minimum instances for the paths that must stay warm, startup CPU boost, and a health-check-friendly startup path - and the capstone in [Chapter 15](#ch15) measures exactly this delta on all three clouds.
:::

::: {.note}
**Best practice - slots and revisions are your rollback lever**

Whether the platform calls it a slot (Functions) or a revision (Container Apps), the pattern is identical: deploy to the cold path, verify, shift traffic, keep the previous version one click away. The AWS book used Lambda versions and aliases for this; treat slots/revisions as the same operational contract, and "rollback" stops being an incident and becomes a command.
:::

**See also:** [Chapter 2](#ch2) is the identity story these services inherit, [Chapter 7](#ch7) deploys both from GitHub Actions without stored credentials, and [Chapter 13](#ch13) gives the Container Apps model its Google Cloud deep dive.
