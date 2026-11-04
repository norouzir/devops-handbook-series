# Chapter 13 - Cloud Run and Event-Driven Serverless {#ch13}

## 13.1 A Container, an HTTPS URL, Zero Servers

**Cloud Run** is the platform this series has been circling since the Docker book: you give it a container image, it gives you an HTTPS endpoint on a real domain, scales from zero to whatever the traffic needs, and charges only while requests are being served. It is the same value proposition as Azure Container Apps ([Chapter 6](#ch6)) - and the two are the closest pair of services in this book - but Cloud Run is the older, deeper implementation, and it remains the most direct expression of the serverless idea on any cloud. Deploying shopnow is one command; Cloud Build builds from source when you use `--source`, so not even Docker is required locally:

```bash
gcloud run deploy shopnow-api \
  --source=. \
  --region=europe-west3 \
  --allow-unauthenticated=false \
  --service-account=sa-shopnow-api@shopnow-dev-eu.iam.gserviceaccount.com
```

Two settings from that command deserve their paragraph. The **service account** attaches the workload identity of [Chapter 9](#ch9) to the service - the container talks to storage and databases as that SA, no keys - and the **invoker** IAM role decides who may call the endpoint: `roles/run.invoker` for specific identities, `allUsers` only when the endpoint is genuinely public. Cloud Run also splits cleanly into **services** (long-lived, HTTP-driven, what this chapter deploys) and **jobs** (run-to-completion batch, the cron-and-queue sibling with the same packaging).

The setting that most distinguishes Cloud Run from the AWS book's Lambda is **concurrency**: one instance serves up to 1,000 concurrent requests (80 by default), where a Lambda instance serves exactly one. Request-based billing stays the same - you pay for request-serving time - but the instance economics differ fundamentally: an efficient service with concurrency at 80 may need a handful of instances where a Lambda deployment needs dozens, and tuning `--concurrency` (with `--cpu` and `--memory`) is the platform's main performance knob.

## 13.2 Revisions and Traffic Splitting

Every deploy freezes into an immutable **revision**: same code, same configuration, a new number, old revisions untouched. Traffic is then a routing table you edit at will - which turns canary deployment, staged rollout, and rollback from pipeline features into platform primitives:

```bash
gcloud run services update-traffic shopnow-api \
  --region=europe-west3 \
  --to-revisions=shopnow-api-00007=10,shopnow-api-00006=90   # 10% canary

gcloud run revisions rollback shopnow-api-00006 --region=europe-west3   # the whole way back

gcloud run services update-traffic shopnow-api --tag=pr-412   # a private preview URL per revision
```

The **tag** line is the feature frontend teams love: every revision can carry a URL, which makes "deploy the pull request, share the link, then promote or delete it" a two-command workflow. Container Apps expressed the same idea as revisions and labels in [Chapter 6](#ch6); here it is the native grain of the platform, and the pipeline in [Chapter 14](#ch14) builds on it.

## 13.3 Event-Driven: Cloud Run functions and Eventarc

The event-driven half of the platform grew up and merged into Cloud Run. **Cloud Run functions** - the current name for what Cloud Functions 2nd gen became - are functions deployed *on* Cloud Run infrastructure: an HTTP function is a Cloud Run service, an event function is a Cloud Run service wired to a trigger, and the packaging is a standard container or source build. The triggers come from **Eventarc**, the routing layer that connects sources to services: a Pub/Sub message, a bucket's `object finalized` event, an audit log entry, a Cloud Scheduler cron - each becomes a delivery to your service with retries and the delivery identity handled by the platform. The Lambda chapter's event-model lesson translates directly: the shape of the trigger decides the shape of the code, and a queue-processor on GCP is usually a Cloud Run function subscribed to a Pub/Sub subscription with a retry policy that matters more than the code does.

## 13.4 Private Access, Sidecars, and the Database

The private story completes the picture. **Direct VPC egress** routes a service's outbound traffic through your VPC from [Chapter 10](#ch10) - the successor to the older Serverless VPC connector, which is deprecated; new designs use direct egress, full stop. Inbound stays IAM-gated unless you deliberately expose. The database connection of [Chapter 11](#ch11) has its platform-native form here: the **Cloud SQL Auth Proxy as a sidecar** (multi-container services support sidecars) or the Unix-socket path when the service carries `roles/cloudsql.client` - and both approaches keep the database's private IP private while the service reaches it through the platform.

::: {.warn}
**Watch out - scale-to-zero meets connection-per-request**

A service that opens a fresh database connection per request, scaled from zero on Monday morning by a traffic spike, presents the database with a connection storm and the deployment with a 500-error ribbon. The fixes are platform-native: `--min-instances=1` for the paths that must never be cold, a connection pool sized to `concurrency`, and the Unix-socket path to Cloud SQL, which makes a local socket rather than a TCP handshake per hop. The same warning appeared in [Chapter 6](#ch6) for Azure; it applies on every serverless platform in this book.
:::

## 13.5 Lab 5: Deploy, Canary, Roll Back

::: {.lab}
### Lab 5 - Cloud Run in Twenty Minutes, With a Canary {#lab5}

1. Deploy from source: `gcloud run deploy shopnow-api --source=. --region=europe-west3` and take the URL the command prints; `curl` the `/healthz` path.
2. Lock it down: `gcloud run services set-iam-policy` to remove `allUsers` if the first deploy opened it, and grant `roles/run.invoker` to your own identity - then verify anonymous access fails with 403.
3. Identity: redeploy with the service account from [Section 13.1](#ch13) and confirm the service reads the assets bucket with no stored credentials.
4. The canary: push a change (bump a version header in the response), `update-traffic` to 90/10 as in [Section 13.2](#ch13), curl until you observe both revisions answering, then shift to 100 and watch the old revision go idle.
5. The preview URL: tag a revision, open the tagged `*.run.app` URL (the tag appears between triple dashes in the hostname), and delete the tag when done.
6. Cost and cleanup: set `--min-instances=0 --max-instances=2` for the demo, observe the bill-shaped behavior in `gcloud run services describe`, then `gcloud run services delete shopnow-api --region=europe-west3` - the service was one object, and deletion is one command.
:::

::: {.note}
**Best practice - treat `--concurrency` as the knob Lambda never gave you**

Right-sizing on Cloud Run is a two-variable search - concurrency per instance and instance CPU/memory - and the payoff is large: raising concurrency from 1 to 80 can cut an order of magnitude off instance count for a light API. Measure with the request-latency percentile you care about, then let the platform scale; the AWS book's Lambda memory-sizing exercise becomes, here, a concurrency exercise with the same method.
:::

**See also:** [Chapter 6](#ch6) is the Azure twin of this platform, [Chapter 12](#ch12) is the Kubernetes route when a cluster becomes the right answer, and [Chapter 14](#ch14) replaces this chapter's terminal deploys with the pipeline.
