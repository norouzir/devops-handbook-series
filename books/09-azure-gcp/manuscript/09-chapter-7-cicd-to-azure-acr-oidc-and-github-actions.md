# Chapter 7 - CI/CD to Azure: ACR, OIDC, and GitHub Actions {#ch7}

## 7.1 ACR: The Registry and Its Build Engine

**Azure Container Registry (ACR)** is the ECR of Part I: private Docker/OCI registries with a name that is also the endpoint - `acrshopnowdev.azurecr.io` - and tiers (Basic, Standard, Premium) that mainly buy throughput and geo-replication. Two habits distinguish ACR practice. First, `az acr build` builds *in the registry* from source - it uploads the build context and runs the docker build on ACR's own infrastructure, so a CI runner needs neither Docker nor a daemon:

```bash
az acr create -g rg-shopnow-dev -n acrshopnowdev --sku Standard
az acr build -r acrshopnowdev -t shopnow/api:v1 .
az acr login -n acrshopnowdev    # only needed for local docker push/pull
```

Second, images are named by repository path and immutably tagged - `shopnow/api:v1` - and the pipeline convention this book carries across all three clouds is *build once, promote the digest*: the same image digest goes dev, staging, production, and only the deployment configuration changes.

## 7.2 Keyless by Default: OIDC from GitHub Actions

This is [Chapter 2](#ch2)'s federated credential turned into pipeline plumbing, and it is the same three moves as the AWS book's OIDC chapter - a trust object in the cloud, a workflow that requests a token, and an action that exchanges it. On Azure the trust object is a **federated identity credential** on an app registration (or managed identity), and the workflow exchanges the token with **`azure/login` v3**:

```bash
APP_ID=$(az ad app create --display-name sp-shopnow-ci --query appId -o tsv)
az ad sp create --id $APP_ID
az role assignment create --assignee $APP_ID \
  --role "Container Apps Contributor" --resource-group rg-shopnow-prod

cat > fic.json <<'EOF'
{
  "name": "fic-github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:example-org/shopnow:ref:refs/heads/main",
  "audiences": [ "api://AzureADTokenExchange" ]
}
EOF
az ad app federated-credential create --id $APP_ID --parameters fic.json
```

Two subject formats cover nearly every pipeline: `repo:<org>/<repo>:ref:refs/heads/main` pins a branch, and `repo:<org>/<repo>:environment:production` pins a GitHub Environment - the pair that lets production deploys inherit the environment's protection rules. And the mid-2026 change the AWS book documented - GitHub folding organization and repository identifiers into the OIDC token's `sub` claim - landed on Azure with the same effect: tokens issued after the change carry the new subject form, trust objects created before it must be updated, and `azure/login` v3 is the release line that handles the new format. If a pipeline that worked in May fails in July with an invalid-subject error, [Section 7.5](#ch7) is the fix.

## 7.3 The Pipeline: Login, Build, Deploy, Verify

The workflow below is the Part I template - the GCP twin appears in [Chapter 14](#ch14) with the same skeleton and different vocabulary. Note what is *absent*: no `secrets`, no stored credentials, only the two IDs that name the identity:

```yaml
name: deploy-azure
on:
  push:
    branches: [main]
    paths: ["api/**"]

permissions:
  id-token: write      # request the OIDC token
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v7

      - name: Azure login (OIDC, no secrets)
        uses: azure/login@v3
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          enable-AzPSSession: false

      - name: Build and push image
        run: |
          az acr build -r acrshopnowdev \
            -t shopnow/api:${{ github.sha }} .

      - name: Deploy to Container Apps
        run: |
          az containerapp update -g rg-shopnow-prod -n shopnow-api \
            --image acrshopnowdev.azurecr.io/shopnow/api:${{ github.sha }}

      - name: Smoke test
        run: curl -fsS --max-time 10 "$APP_URL/healthz"
```

The variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`) are identifiers, not secrets - safe to live in repository variables. Rollback is one revision away (`az containerapp revision rollback`), and promotion is the build-once pattern: the digest built on `main` is what `environment: production` deploys.

## 7.4 Environments, Slots, and the Promotion Path

GitHub **Environments** give the workflow its guardrails: `environment: production` can require reviewers, restrict to protected branches, and gate by a wait timer - and because the FIC subject pins the environment, the token minted for `production` cannot deploy anything else. The platform side has its own vocabulary for the same idea: slots on Functions ([Chapter 6](#ch6)) and revisions with traffic split on Container Apps stage and verify before the public sees the change. The full promotion path - branch merge, environment approval, revision warm-up, traffic shift, instant rollback - is exactly the pipeline the AWS book built on EKS, wearing Azure clothes.

## 7.5 Lab 3: A Pipeline with No Stored Credentials

::: {.lab}
### Lab 3 - OIDC from GitHub to Container Apps, End to End {#lab3}

1. Foundation: `rg-shopnow-prod`, `cae-shopnow-prod` (a Container Apps environment), `acrshopnowdev`, and an initial `shopnow-api` created by hand with a placeholder image - the pipeline will own it from the next push.
2. Identity: create the app registration and service principal, assign **Container Apps Contributor** on `rg-shopnow-prod`, and add the FIC with the `environment:production` subject from [Section 7.2](#ch2).
3. Repository: set `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` as repository variables, create the `production` GitHub environment with a required reviewer, and commit `.github/workflows/deploy-azure.yml` from [Section 7.3](#ch3).
4. Push to `main`, watch the run request its OIDC token, log in, build in ACR, and deploy - then verify the revision is live with `az containerapp revision list`.
5. Prove the negative: search the repository's secrets for anything Azure-shaped and find nothing - the credential lived in the token minted per run.
6. Break and roll back: deploy an image that fails `/healthz`, then `az containerapp revision rollback` and watch traffic return to the previous revision.
7. The subject-change drill: add a second FIC whose subject uses the post-2026 `sub` format, delete the old one, and re-run - a rehearsal for the day GitHub flips the format on your real repository.
:::

::: {.warn}
**Watch out - `AADSTS700213`: the FIC subject did not match**

The login step fails with `AADSTS700213: No matching federated identity record found` when the token's `sub` and the FIC's `subject` disagree by one character - branch vs environment format, wrong org, or the pre/post-2026 claim change. Read the failing token's `sub` from the job log, run `az ad app federated-credential list --id <app-id>`, and diff the two strings; the fix is always an update to the FIC (`az ad app federated-credential update`), never a workaround with secrets.
:::

**See also:** [Chapter 5](#ch5) is the cluster this pipeline can also target, [Chapter 6](#ch6) explains the revision mechanics the rollback step used, [Chapter 9](#ch9) - the *GitHub Actions* volume - owns the workflow syntax itself, and [Chapter 14](#ch14) runs the same pipeline on GCP.
