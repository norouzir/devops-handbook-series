# Chapter 9 - Identity and Access: IAM, Service Accounts, and Workload Identity Federation {#ch9}

## 9.1 One Policy Model for Every Resource

GCP's IAM is the most uniform of the three clouds: one policy model, applied at every point of the hierarchy from [Chapter 8](#ch8) - organization, folder, project, and *individual resources*. A policy is a set of **bindings**: a **role** granted to a **member** at a **scope**. The organization policy descends, a project policy descends, and a single Cloud Storage bucket can carry its own binding without inventing a second system - which is the structural difference from AWS, where identity policies and resource policies are two dialects, and the closest thing to Azure's single RBAC ladder of [Chapter 2](#ch2). Inspecting any level uses the same verb:

```bash
gcloud projects get-iam-policy shopnow-dev-eu \
  --format="table(bindings.role, bindings.members)" 
gcloud storage buckets get-iam-policy gs://shopnow-assets-eu
```

## 9.2 Members, Roles, and the Basic-Role Trap

**Members** are typed by prefix, and the prefixes matter: `user:` for humans, `group:` for Google Groups (the assignment unit professionals use, exactly as on the other two clouds), `serviceAccount:` for workload identities, and `principalSet:`/`principal://` for federated external identities - the prefix that carries the OIDC pipeline story in [Section 9.4](#ch9) and [Chapter 14](#ch14). **Roles** come in three families. **Basic roles** (`roles/owner`, `roles/editor`, `roles/viewer`) are the legacy blunt instruments: `editor` is the "write anything on the project" role that AWS never had a name for because AWS never dared, and new bindings should not use it. **Predefined roles** are the fine-grained library - `roles/storage.objectViewer`, `roles/run.invoker`, thousands of service-scoped entries, the AWS managed-policy analog - and **custom roles** compose individual permissions when a predefined shape does not fit. Bindings can also carry **conditions**, CEL expressions evaluated at request time, which quietly enable things the other clouds need extra machinery for: time-boxed grants (`request.time < timestamp("2026-12-31T23:00:00Z")`) and resource-name scoping in one line.

::: {.warn}
**Watch out - `editor` is how GCP projects rot**

Every tutorial, every quickstart, and half of Google's own older docs grant `roles/editor` to move on, and a year later nobody remembers why a service account can write every bucket in the project. The fix is mechanical: `gcloud projects get-iam-policy` plus a search for `roles/editor`, then replace each binding with the two or three predefined roles the workload actually exercises - `roles/storage.objectAdmin` plus `roles/cloudsql.client` beats `editor` in every audit, every time.
:::

## 9.3 Service Accounts: The Identity for Workloads

A **service account (SA)** is the IAM identity for code - the Google Cloud name for what AWS called a role and Azure called a managed identity, with the same design goal: *no static credential near the workload*. SAs come in two flavors: **user-managed** (you create them, `sa-shopnow-api@shopnow-dev-eu.iam.gserviceaccount.com`, you attach them to VMs, GKE workloads, and Cloud Run services) and **service agents** (Google-created identities the platform uses on your behalf, recognizable by the `@*.gserviceaccount.com` Google-owned domain). Attaching an SA to compute is the everyday verb:

```bash
gcloud iam service-accounts create sa-shopnow-api --display-name="shopnow API"

gcloud compute instances create shopnow-web-01 \
  --zone=europe-west3-a --machine-type=e2-small \
  --service-account=sa-shopnow-api@shopnow-dev-eu.iam.gserviceaccount.com \
  --scopes=cloud-platform
```

The subtle permission is **actAs**: running *as* an SA requires `roles/iam.serviceAccountUser` *on that SA*, separate from whatever the SA itself may do - so "who may deploy as this identity" and "what may this identity do" are auditable separately. And the tool that makes least-privilege testing cheap is **impersonation**: grant `roles/iam.serviceAccountTokenCreator` to yourself on the SA, and every gcloud command accepts `--impersonate-service-account` - the `sts assume-role` of GCP, and the cleanest way to *test* the SA's exact permissions before granting them to a pipeline.

::: {.note}
**Best practice - impersonate before you grant**

`gcloud storage ls --impersonate-service-account=sa-shopnow-api@...` either works or fails with the exact missing permission - a one-line rehearsal of the pipeline's permission set, before that set exists. The habit converts IAM debugging from "grant broadly, retry" into "rehearse, read, grant once", and it is the single biggest workflow difference a GCP newcomer should steal.
:::

The thing that must *not* happen is **downloading a key**: SA key files are static, long-lived credentials - the embedded-keys anti-pattern this series has refused since the IAM chapter of the AWS book. Workloads get identities by *attachment* (the SA on the VM, the K8s service account of [Chapter 12](#ch12), the Cloud Run service identity of [Chapter 13](#ch13)); the one legitimate key-shaped thing in this book is nothing at all.

## 9.4 Workload Identity Federation: OIDC from Outside

For identities that live *outside* GCP - a GitHub Actions workflow above all - **Workload Identity Federation (WIF)** is the zero-credential bridge, and it is GCP's most explicit statement of the pattern this book has now built on both other clouds. You create an **identity pool** (a namespace for external identities) and a **provider** inside it that trusts GitHub's token issuer, with **attribute mappings** copying token claims into GCP attributes and an **attribute condition** deciding which repositories may proceed:

```bash
POOL=projects/123456789/locations/global/workloadIdentityPools/gha-pool
PROVIDER=$POOL/providers/github

gcloud iam workload-identity-pools create gha-pool --location=global
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=gha-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='example-org/shopnow'"
```

The pipeline then runs as either of two shapes. **Direct WIF** grants roles to the federated member itself - `principalSet://iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/gha-pool/attribute.repository/example-org/shopnow` - with no SA to impersonate. **SA impersonation** grants `roles/iam.workloadIdentityUser` on a service account to the same member, and the workflow logs in *as* that SA - the shape [Chapter 14](#ch14) uses because it keeps one auditable identity per pipeline. The mid-2026 GitHub `sub` claim change documented in the AWS and Azure chapters lands here as an *attribute* issue: mappings reference `assertion.sub`, so after the change your mapping or condition may need the new subject form, and a pipeline that fails with `Invalid identity token` after a GitHub-side change has earned itself a look at the provider config before anything else.

## 9.5 Least Privilege as a Workflow, Not a Wishlist

The tools that keep IAM honest ship with the platform. The **IAM Recommender** watches actual usage and proposes narrower roles - the Access Analyzer sibling from the AWS book. The **Policy Troubleshooter** answers the question every engineer asks at 2 a.m. - *why* was this denied, which binding, which condition - by name instead of by guesswork. Audit logs (Admin Activity always on, Data Access opted in per service) close the loop. The workflow that ties them together: rehearse with impersonation, grant the narrow predefined role, let the Recommender trim what the logs prove is unused, and keep the **group** as the only human-facing assignment unit.

**See also:** [Chapter 8](#ch8) defined the hierarchy these policies attach to, [Chapter 12](#ch12) and [Chapter 13](#ch13) attach service accounts to the two runtimes this book runs shopnow on, and [Chapter 14](#ch14) turns [Section 9.4](#ch9) into a working pipeline.
