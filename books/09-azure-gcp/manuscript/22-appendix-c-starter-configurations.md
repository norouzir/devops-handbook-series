# Appendix C - Starter Configurations {#appC}

This appendix holds the configurations worth copying into a repository as-is: the identity bootstraps for both clouds' keyless pipelines ([Chapter 7](#ch7), [Chapter 14](#ch14)), a minimal Bicep stack for Container Apps, a Cloud Run service definition, and the portable Kubernetes manifest whose three identity annotations are the only cloud-specific lines. Every file is complete; fill in the values in `UPPER_SNAKE`.

## C.1 Azure: Bootstrap the Keyless Pipeline Identity

```bash
#!/usr/bin/env bash
# azure-ci-bootstrap.sh — app registration, role, and GitHub OIDC trust.
set -euo pipefail
ORG_REPO="ORG/REPO"             # e.g. example-org/shopnow
BRANCH="main"
RG="rg-shopnow-prod"

APP_ID=$(az ad app create --display-name sp-shopnow-ci --query appId -o tsv)
az ad sp create --id "$APP_ID"
az role assignment create --assignee "$APP_ID" \
  --role "Container Apps Contributor" --resource-group "$RG"

cat > fic.json <<EOF
{
  "name": "fic-github-${BRANCH}",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:${ORG_REPO}:ref:refs/heads/${BRANCH}",
  "audiences": [ "api://AzureADTokenExchange" ]
}
EOF
az ad app federated-credential create --id "$APP_ID" --parameters fic.json && rm fic.json

echo "AZURE_CLIENT_ID=$APP_ID   # set as a repository variable (not a secret)"
echo "AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)"
```

## C.2 Azure: Minimal Bicep for Container Apps with a Managed Identity

```bicep
// aca.bicep — one environment, one app, identity attached, no secrets.
param location string = resourceGroup().location
param name string
param image string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: { appsNetworkProfile: {} }
}

resource mi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-07-31-preview' = {
  name: 'mi-${name}'
  location: location
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${mi.id}': {} } }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8080 }
    }
    template: {
      containers: [ {
        name: 'api'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
      } ]
      scale: { minReplicas: 0, maxReplicas: 10 }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output miClientId string = mi.properties.clientId
```

Deploy: `az deployment group create -g rg-shopnow-prod -f aca.bicep -p name=shopnow-api image=<acr>.azurecr.io/shopnow/api:v1`.

## C.3 GCP: Bootstrap the WIF Pool and the Pipeline Identity

```bash
#!/usr/bin/env bash
# gcp-ci-bootstrap.sh — SA, grants, WIF pool, GitHub provider, binding.
set -euo pipefail
PROJECT_ID="PROJECT_ID"
ORG_REPO="ORG/REPO"
SA="sa-shopnow-ci"

gcloud iam service-accounts create "$SA" --project="$PROJECT_ID"
for ROLE in roles/artifactregistry.writer roles/run.developer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="$ROLE" --quiet
done

gcloud iam workload-identity-pools create gha-pool --location=global --project="$PROJECT_ID"
PROJNUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=gha-pool --project="$PROJECT_ID" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${ORG_REPO}'"

gcloud iam service-accounts add-iam-policy-binding \
  "${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJNUM}/locations/global/workloadIdentityPools/gha-pool/attribute.repository/${ORG_REPO}"

echo "provider: projects/${PROJNUM}/locations/global/workloadIdentityPools/gha-pool/providers/github"
```

## C.4 GCP: A Cloud Run Service as YAML

```yaml
# service.yaml — the declarative form of Chapter 13's deploy.
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: shopnow-api
  labels:
    cloud.googleapis.com/location: europe-west3
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "0"
        autoscaling.knative.dev/maxScale: "10"
        run.googleapis.com/startup-cpu-boost: "true"
    spec:
      serviceAccountName: sa-shopnow-api@PROJECT_ID.iam.gserviceaccount.com
      containers:
        - image: europe-west3-docker.pkg.dev/PROJECT_ID/shopnow/api:v1
          ports: [ { containerPort: 8080 } ]
          resources:
            limits: { cpu: "1", memory: 512Mi }
  traffic:
    - percent: 100
      latestRevision: true
```

Deploy with `gcloud run services replace service.yaml` - the same file the pipeline can `kubectl`-style diff and apply.

## C.5 The Portable Manifest with Three Identity Annotations

```yaml
# k8s/deployment.yaml — identical on EKS, AKS, and GKE except one block.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: shopnow-api
  namespace: shopnow
  annotations:
    # EKS (IRSA):    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/irsa-shopnow-api
    # AKS:           azure.workload.identity/client-id: MI_CLIENT_ID
    # GKE:           iam.gke.io/gcp-service-account: sa-shopnow-api-gke@PROJECT.iam.gserviceaccount.com
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shopnow-api
  namespace: shopnow
spec:
  replicas: 2
  selector: { matchLabels: { app: shopnow-api } }
  template:
    metadata:
      labels: { app: shopnow-api }
      # AKS only, additionally: azure.workload.identity/use: "true"
    spec:
      serviceAccountName: shopnow-api
      containers:
        - name: api
          image: shopnow/api:v1   # overridden per cloud by the pipeline
          ports: [ { containerPort: 8080 } ]
          resources:
            requests: { cpu: 100m, memory: 128Mi }   # required on GKE Autopilot
            limits:   { memory: 512Mi }
          readinessProbe: { httpGet: { path: /healthz, port: 8080 } }
```

The three commented lines are the capstone's punchline in code: the entire cloud-specific surface of the workload, three annotations long.
