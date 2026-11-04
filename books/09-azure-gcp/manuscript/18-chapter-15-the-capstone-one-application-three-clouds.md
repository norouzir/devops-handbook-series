# Chapter 15 - The Capstone: One Application, Three Clouds {#ch15}

## 15.1 The Assignment

The earlier volumes have been building to this chapter without saying so. The same small platform - **shopnow**: one API container, one PostgreSQL database, one assets bucket, one pipeline, all of it introduced in the Docker book and carried through every volume since - now exists three times:

- **AWS**, from *AWS for DevOps Engineers*: EC2 and VPC foundations, EKS with IRSA, the GitHub Actions pipeline with `configure-aws-credentials` v6;
- **Azure**, from Part I: the Bicep stack, AKS with workload identity, the pipeline of [Chapter 7](#ch7);
- **Google Cloud**, from Part II: the Autopilot cluster of [Chapter 12](#ch12) or the Cloud Run service of [Chapter 13](#ch13), behind the pipeline of [Chapter 14](#ch14).

The capstone is not "translate the app three times" - the app never changed. It is the disciplined exercise of running *the same thing* under three ownership models, and writing down what actually differed. That record is worth more than any vendor comparison page, because every line of it is something your own hands did.

## 15.2 What Turned Out to Be Identical

Start with the surprises in the good direction. The **application container** is the same digest everywhere - the OCI image built once travels across all three registries without a rebuild. The **Kubernetes manifests** for the EKS, AKS, and GKE deployments differ in three annotation lines (the IRSA role, the Azure workload-identity client ID, the GKE service-account annotation) and nothing else - Gateway and Ingress shapes aside, a Deployment is a Deployment. The **pipeline skeleton** is one YAML shape: request the OIDC token, exchange it with the cloud's action (`configure-aws-credentials` v6, `azure/login` v3, `google-github-actions/auth` v3), then deploy with the cloud's verb. And the **security architecture** is the same diagram drawn three times: no stored credentials anywhere, workload identity to the data tier, least-privilege grants on the pipeline identity. That convergence is the decade's real story: the hyperscalers standardized on Kubernetes, OCI, OpenTelemetry, and OIDC, and the portability of 2026 is real at exactly those four layers.

## 15.3 What Genuinely Differed

Then the honest list. The **vocabulary** differs everywhere - role/managed identity/service account for one concept, security group/NSG/firewall tags for another, and Appendix A is the translation table this chapter assumes. The **IAM models** differ in kind, not just name: AWS's identity-plus-resource-policy duality, Azure's control-plane/data-plane split ([Chapter 2](#ch2) - the `Contributor` who cannot read a blob), GCP's single uniform ladder ([Chapter 9](#ch9)). The **network models** differ structurally: AWS's regional VPC with per-pod VNet addressing, Azure's regional VNet with CNI overlay, GCP's *global* VPC with regional subnets ([Chapter 10](#ch10)) - three answers to the same question, with real consequences for IP planning and multi-region design. The **serverless runtimes** differ most: EKS/Lambda is a Kubernetes-plus-functions pairing, Azure's Container Apps and GCP's Cloud Run are twins that do the whole job with no cluster, and the concurrency models (one-request Lambda, tunable Cloud Run) change the performance math ([Chapter 13](#ch13)). And the **defaults** differ in direction: AKS's free control plane, GKE Autopilot's pod-based billing, EKS's per-cluster fee - three pricing philosophies wearing infrastructure.

| Dimension | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Hierarchy atom | Account | Subscription | Project |
| Identity for workloads | IAM role / IRSA | Managed identity | Service account + WIF |
| Kubernetes | EKS (control plane billed) | AKS (free tier control plane) | GKE Autopilot (pod-billed) |
| Serverless container | Fargate / App Runner | Container Apps | Cloud Run |
| Object storage | S3 | Blob Storage | Cloud Storage |
| Managed PostgreSQL | RDS | Flexible Server | Cloud SQL |
| Registry | ECR | ACR | Artifact Registry |
| CI trust object | OIDC role + `sub` claim | Federated credential (FIC) | WIF pool + provider |
| IaC of record | Terraform | Bicep (Terraform for multi-cloud) | Terraform |

::: {.note}
**Best practice - the table is a map, not a verdict**

Every row above has a footnote that matters - GKE Standard bills like a cluster, AKS Standard tier carries an SLA fee, Fargate changes the EKS row's economics - and the footnote-level differences are exactly the ones your workload's shape decides. Use the table to know *where to look* when a number surprises you, not to pick a winner in a meeting.
:::

## 15.4 Egress: The Multi-Cloud Tax

The cost line no table survives is traffic **between** clouds: every byte that leaves AWS for Azure, or Azure for GCP, pays the internet egress rate on both ends, and inter-cloud replication or fan-out architectures pay it forever. The design rule the capstone teaches in one sentence: *keep the data gravity inside one cloud per data domain* - the database, the queue, and the object store serving one application live together, and cross-cloud links are for control planes (your repository, your CI) and for humans, not for the request path. The "multi-cloud resilience" architecture that keeps three databases in sync across three providers pays the tax on every write and inherits three consistency models; [Chapter 16](#ch16) puts that architecture where it belongs.

## 15.5 Lab 6: Deploy, Measure, Compare, Delete

::: {.lab}
### Lab 6 - The Three-Cloud Evening {#lab6}

1. **Provision the three stacks** with what the book already built: the AWS stack from its volume's chapters (or the smallest honest stand-in - Fargate or App Runner), the Azure stack from [Chapter 7](#ch7)'s lab, the GCP stack from [Chapter 13](#ch13)'s lab. Same image digest, same database schema, same health endpoint.
2. **Measure the same five things on each**: time from `git push` to healthy endpoint (pipeline latency), p95 latency of `/healthz` from *your* location, cold-start latency after five minutes idle, the price of one hour of steady state from the cost explorer or pricing calculator, and the number of *resources you had to create by hand* to go from zero to endpoint.
3. **Fill the comparison table yourself** - the five rows, three columns, with your numbers, not the vendors'. Then write the two-line summary you would show a team choosing a cloud next month.
4. **Break each on purpose**: stop the cluster (each cloud has its verb now), deploy a bad revision (each has its rollback verb), revoke the pipeline's trust object (and restore it) - the muscle memory is the deliverable.
5. **Delete all three**, fully: resource groups on Azure (`az group delete`), projects on GCP (`gcloud projects delete`), stacks on AWS (the cleanup chapters' steps) - then verify each bill shows the flat line, which is the last and most important metric of the evening.
:::

::: {.warn}
**Watch out - "the same app" is never "the same platform services"**

The capstone keeps the *application* identical and lets the platforms differ, because forcing identical services is where multi-cloud projects die: the queue is SQS, Service Bus, and Pub/Sub; the identity stores are three different things; the "portable" database is only as portable as its Postgres-compatible core. Portable is a property of *layers* - containers, Kubernetes, OpenTelemetry, Terraform - not of service catalogs, and the sooner the comparison table says so, the sooner the cloud strategy becomes a decision instead of a debate.
:::

**See also:** [Chapter 16](#ch16) turns this chapter's measurements into a decision framework, [Chapter 7](#ch7) and [Chapter 14](#ch14) are the two pipeline halves of the evening, and the *AWS for DevOps Engineers* volume is the third pipeline's home.
