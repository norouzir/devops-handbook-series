# Appendix D - Troubleshooting Guide {#appD}

Organized by symptom, like the AWS volume's guide: what you see first, what usually causes it, and the command that confirms it. The cross-cloud section at the end collects the OIDC failures all three pipelines share.

## Azure

| Symptom | Usual cause | Confirm / fix |
| --- | --- | --- |
| `AADSTS700213: No matching federated identity record found` on `azure/login` | FIC subject mismatch: branch vs environment format, wrong org/repo, or the 2026 `sub` claim change | Read the token's `sub` in the job log; `az ad app federated-credential list --id <app-id>`; update the FIC to match exactly ([Ch. 7](#ch7)) |
| `AuthorizationPermissionMismatch` on a storage operation with `Contributor` held | Data plane needs a data role; control-plane roles do not read blobs | `az role assignment create --role "Storage Blob Data Contributor" --scope <account-id>` ([Ch. 2](#ch2)) |
| `ResourceGroupNotFound` / resource "disappeared" | CLI pointed at the wrong subscription, or the RG was deleted recursively | `az account show` before blaming the platform; `az group list -o table` |
| New VM is internet-reachable but "I never opened anything" | `az vm create` built an implicit VNet, public IP, and NSG | `az network nic list-effective-nsg`; rebuild the stack with explicit network ([Ch. 3](#ch3), [Ch. 4](#ch4)) |
| `az login` loops or lands in the wrong tenant | Browser session cached another tenant | `az login --tenant <tenant-id>` or `az login --use-device-code`; then `az account list` |
| AKS pod stuck `Pending`, events say "plugin Overlay failed" or quota | Subnet/quota exhaustion or zones unavailable for the size | `az aks show` node pool config; `az vm list-usage -l westeurope` |
| Container App always cold, users complain of latency | `minReplicas: 0` plus a heavy image | `az containerapp update --min-replicas 1`; check startup CPU ([Ch. 6](#ch6)) |
| Functionapp deploy works, function 500s in the portal | Runtime version drift (local vs plan) or missing app setting | `az functionapp config appsettings list`; pin the runtime ([Ch. 6](#ch6)) |
| RG delete hangs for many minutes | Normal - deletion is recursive and ordered, disks and PG servers are slow | `az resource list -g <rg>` to watch it drain; do not interrupt |

## Google Cloud

| Symptom | Usual cause | Confirm / fix |
| --- | --- | --- |
| `Project 'xxx' not found` everywhere | Typed the project *name*; commands want the project *ID* | `gcloud projects list --format='table(project_id, name)'`; use the left column ([Ch. 8](#ch8)) |
| `UNAUTHENTICATED: Invalid audience` on the auth step | Provider resource name wrong: project number vs ID, missing `providers/` segment | `gcloud iam workload-identity-pools providers describe github ...` and paste `name` verbatim ([Ch. 14](#ch14)) |
| `Invalid identity token` after a GitHub-side change | The 2026 `sub` claim change hit the attribute mapping/condition | Update the provider mapping or condition, not the workflow ([Ch. 9](#ch9), [Ch. 14](#ch14)) |
| `Permission denied on 'run.services.create'` | CI SA lacks `roles/run.developer`, or actAs missing on the runtime SA | Rehearse with `--impersonate-service-account`; add the exact role ([Ch. 9](#ch9)) |
| `docker push` denied | Local docker not configured for the regional host, or missing `artifactregistry.writer` | `gcloud auth configure-docker europe-west3-docker.pkg.dev` |
| Pod `CrashLoopBackOff` with credential errors on GKE | Workload Identity binding/annotation mismatch | Check the KSA annotation and the `add-iam-policy-binding` member string `PROJECT.svc.id.goog[ns/sa]` ([Ch. 12](#ch12)) |
| Autopilot rejects the Deployment | Missing/undersized `requests` - Autopilot requires them | Add honest requests/limits; the event says which resource ([Ch. 12](#ch12)) |
| Cloud SQL: `connection refused` from Cloud Run | Public IP absent and private path not configured | Use the Auth Proxy sidecar or Unix socket + `roles/cloudsql.client` ([Ch. 11](#ch11), [Ch. 13](#ch13)) |
| Bucket 403 with "the right" role on the user | Bucket has its own policy, or uniform access hides ACL assumptions | `gcloud storage buckets get-iam-policy gs://<bucket>` ([Ch. 9](#ch9), [Ch. 11](#ch11)) |
| Budget alert never fired | Alert thresholds are percentages of a monthly amount; spend was front-loaded or budget attached to the wrong billing account | `gcloud billing budgets list --billing-account=<id>`; add a 50% threshold |

## Cross-Cloud: The OIDC Family

| Symptom | Meaning | The move |
| --- | --- | --- |
| Token requested but no permission after login | Trust object exists; roles/permissions are on the wrong identity | AWS: check the role's trust `sub`; Azure: check the FIC + role assignment; GCP: check the WIF binding member |
| Worked in spring, failed in summer | The 2026 GitHub `sub` claim change (org/repo IDs folded in) | Update the trust object per cloud: role condition, FIC subject, WIF mapping/condition - all three documented in [Ch. 7](#ch7) and [Ch. 14](#ch14) |
| `id-token: write` missing | Workflow never received a token to exchange | Add the `permissions` block; the auth step fails first, everything after it is noise |
| Subject matches but still denied | Audience mismatch (`api://AzureADTokenExchange` vs provider resource name) | Audience is fixed per cloud and shown in the error; do not invent one |
| Pipeline works from `main`, fails from a PR | Trust object pins one ref, or environment protection blocks | Add the environment-scoped FIC/provider for PRs, or accept the gate - it is a feature |
