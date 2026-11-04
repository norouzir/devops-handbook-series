# Chapter 14 - CI/CD to GCP: Artifact Registry and GitHub Actions {#ch14}

## 14.1 Artifact Registry: The Registry That Replaced Two

**Artifact Registry** is the GCR story settled: regional, multi-format repositories (Docker, OCI, npm, Python, Maven) under one product, after Container Registry's sunset retired the old `gcr.io` hosting path. Repos are created per format and region, and image names carry the full regional host:

```bash
gcloud artifacts repositories create shopnow \
  --repository-format=docker --location=europe-west3

gcloud auth configure-docker europe-west3-docker.pkg.dev
docker tag shopnow/api:v1 europe-west3-docker.pkg.dev/shopnow-dev-eu/shopnow/api:v1
docker push europe-west3-docker.pkg.dev/shopnow-dev-eu/shopnow/api:v1
```

The region in the hostname is the whole naming discipline - `europe-west3-docker.pkg.dev/<project>/<repo>/<image>` - and it means the registry is where the workload is, which keeps pulls fast and egress boring. Pushing from CI needs `roles/artifactregistry.writer` on the repository for the deploying identity, which is the first of the pipeline's three grants.

## 14.2 Workload Identity Federation, Once Per Repository

The trust setup of [Chapter 9](#ch9) becomes pipeline plumbing exactly once per repository, and this section is the script. The pipeline runs as a dedicated service account - the auditable identity - granted three roles and impersonated by the federated pool member:

```bash
PROJECT=shopnow-dev-eu
SA=sa-shopnow-ci@${PROJECT}.iam.gserviceaccount.com

gcloud iam service-accounts create sa-shopnow-ci
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" --role="roles/run.developer"
# actAs: the CI SA may deploy services that run as the runtime SA of Chapter 13
gcloud iam service-accounts add-iam-policy-binding \
  sa-shopnow-api@${PROJECT}.iam.gserviceaccount.com \
  --member="serviceAccount:$SA" --role="roles/iam.serviceAccountUser"

POOL=projects/$(gcloud projects describe $PROJECT --format='value(projectNumber)')/locations/global/workloadIdentityPools/gha-pool

gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=gha-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='example-org/shopnow' && assertion.ref=='refs/heads/main'"

gcloud iam service-accounts add-iam-policy-binding $SA \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL}/attribute.repository/example-org/shopnow"
```

Three details carry the whole security argument. The **attribute condition** admits exactly one repository at one ref - the trust boundary is the condition, not a secret. The **`workloadIdentityUser` member** is the `principalSet` form, which admits *the repository* rather than one branch - swap it for the full `google.subject` string when you want branch-level trust. And the mid-2026 GitHub `sub` claim change that reshaped the Azure chapter's FIC lands here on the *mapping*: `google.subject=assertion.sub` copies whatever GitHub puts in `sub`, so after the change the token's subject form shifts and the condition (which matches on `repository` and `ref` claims) is the part that keeps working. A pipeline failing with `Invalid identity token` after a GitHub-side change has its first suspect in the provider, not the workflow.

## 14.3 The Workflow: Auth, Build, Deploy

The workflow is the twin of [Chapter 7](#ch7)'s - same skeleton, different vocabulary - and it is worth reading the symmetry: both request `id-token: write`, both log in with an action that exchanges the OIDC token, both end in a platform deploy verb:

```yaml
name: deploy-gcp
on:
  push:
    branches: [main]
    paths: ["api/**"]

env:
  IMAGE: europe-west3-docker.pkg.dev/shopnow-dev-eu/shopnow/api

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v7

      - name: Authenticate to GCP (WIF, no keys)
        uses: google-github-actions/auth@v3
        with:
          project_id: shopnow-dev-eu
          workload_identity_provider: projects/123456789/locations/global/workloadIdentityPools/gha-pool/providers/github
          service_account: sa-shopnow-ci@shopnow-dev-eu.iam.gserviceaccount.com

      - name: Build and push
        run: gcloud builds submit --tag "$IMAGE:${{ github.sha }}" api/

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy shopnow-api --region=europe-west3 \
            --image="$IMAGE:${{ github.sha }}" --quiet

      - name: Smoke test
        run: curl -fsS --max-time 10 "$(gcloud run services describe shopnow-api --region=europe-west3 --format='value(status.url)')/healthz"
```

`google-github-actions/auth@v3` is the current major and the book's pinned version; it writes Application Default Credentials that every later `gcloud` step inherits - no `gcloud auth` dance in the steps. For GKE targets, the deploy step swaps to `gcloud container clusters get-credentials` plus `kubectl apply` with the manifests of [Chapter 12](#ch12), and the same auth step covers both - the credential is the workflow's, not the target's.

## 14.4 Rollback, Promotion, and the Build-Once Discipline

Rollback on Cloud Run is the revision mechanics of [Chapter 13](#ch13) called from the pipeline: `gcloud run services update-traffic --to-revisions=<prev>=100`, or the `revisions rollback` verb - and because the image digest built on `main` is the only artifact that travels, promotion across environments (and, for the ambitious, across regions and clouds) is a *deploy configuration* change, never a rebuild. GitHub Environments gate it exactly as in [Chapter 7](#ch7): `environment: production` carries the reviewers, the branch restrictions, and the wait, while the WIF condition carries the trust. The capstone in [Chapter 15](#ch15) runs three of these pipelines side by side and lets the bills judge.

## 14.5 Cloud Build or GitHub Actions?

The honest decision rule for this series' readers: **orchestrate in GitHub Actions, build where it is cheapest**. Cloud Build is a fine builder - in-region, private pools for VPC-bound builds, per-step billing - and this book has used it twice for exactly that (`gcloud builds submit` from a workflow step). But the orchestration layer - environments, approvals, OIDC, the matrix across clouds - lives in the platform the repository already speaks, and splitting orchestration across three clouds' builders is how multi-cloud repos become three repos in a trench coat. Keep one workflow shape, swap the deploy step per target, and the capstone is an afternoon instead of a quarter.

::: {.warn}
**Watch out - `UNAUTHENTICATED: Invalid audience` means the provider path is wrong**

The WIF exchange validates the token's audience against the provider's full resource name - pool, location, and provider all spelled out, `projects/<number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>`. A project *ID* where the *number* belongs, a missing `providers/` segment, or a copied example with the wrong region produces `Invalid audience` or `UNAUTHENTICATED` on the auth step. Print the provider with `gcloud iam workload-identity-pools providers describe` and paste its `name` field into the workflow verbatim; the error never lies about the path.
:::

**See also:** [Chapter 7](#ch7) is the Azure twin with the FIC instead of the pool, [Chapter 9](#ch9) owns the federation mechanics, [Chapter 13](#ch13) owns the revision mechanics the rollback step uses, and [Chapter 15](#ch15) is where all three pipelines meet.
