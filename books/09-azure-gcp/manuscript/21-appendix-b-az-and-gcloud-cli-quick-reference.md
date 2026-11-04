# Appendix B - az and gcloud CLI Quick Reference {#appB}

This appendix collects the invocations that recur across the book, organized by service. All commands assume az CLI 2.x and the current gcloud CLI, a signed-in session ([Chapter 1](#ch1), [Chapter 8](#ch8)), and the book's defaults (`westeurope`, `europe-west3`). Replace the example identifiers with your own.

## Session and Context

| Task | az | gcloud |
| --- | --- | --- |
| Sign in | `az login` (add `--use-device-code` headless) | `gcloud auth login` |
| Who / where am I? | `az account show` | `gcloud config list` |
| List boundaries | `az account list -o table` | `gcloud projects list` |
| Switch context | `az account set -s <sub-id>` | `gcloud config set project <id>` |
| Named profile | - (env `AZURE_CONFIG_DIR`, or `az login -t <tenant>`) | `gcloud config configurations create/activate <name>` |
| Impersonate a workload | - (managed identity from within the workload) | `--impersonate-service-account=<sa>` |

## Identity and Access

| Task | az | gcloud |
| --- | --- | --- |
| My directory identity | `az ad signed-in-user show` | `gcloud auth list` |
| List role assignments | `az role assignment list --resource-group <rg>` | `gcloud projects get-iam-policy <project> --format=table(bindings.role, bindings.members)` |
| Grant a role | `az role assignment create --assignee <id> --role <role> --resource-group <rg>` | `gcloud projects add-iam-policy-binding <project> --member=<member> --role=<role>` |
| Create workload identity | `az identity create -g <rg> -n <name>` | `gcloud iam service-accounts create <name>` |
| Federate GitHub (OIDC) | `az ad app federated-credential create --id <app-id> --parameters fic.json` | `gcloud iam workload-identity-pools providers create-oidc github ...` |

## Compute

| Task | az | gcloud |
| --- | --- | --- |
| Create a small VM | `az vm create -g <rg> -n <vm> --image Ubuntu2404 --size Standard_B2s --generate-ssh-keys` | `gcloud compute instances create <vm> --zone=europe-west3-a --machine-type=e2-small --image-family=debian-12 --image-project=debian-cloud` |
| List VMs | `az vm list -d -o table` | `gcloud compute instances list` |
| Start / stop / delete | `az vm start/stop/delete -g <rg> -n <vm>` | `gcloud compute instances start/stop/delete <vm> --zone=<zone>` |
| SSH | `az ssh vm --ip <ip>` (or Bastion) | `gcloud compute ssh <vm> --zone=<zone>` |
| Instance template / group | `az vmss create -g <rg> -n <vmss> --image Ubuntu2404 --instance-count 2` | `gcloud compute instance-groups managed create <mig> --template=<tpl> --size=2 --region=europe-west3` |
| Resize | `az vm resize -g <rg> -n <vm> --size Standard_B2ms` | new template + `gcloud compute instance-groups managed rolling-action start-update` |

## Kubernetes

| Task | az | gcloud |
| --- | --- | --- |
| Create managed cluster | `az aks create -g <rg> -n <aks> --zones 1 2 3 --enable-oidc-issuer --enable-workload-identity --enable-cluster-autoscaler --min-count 2 --max-count 5` | `gcloud container clusters create-auto <gke> --region=europe-west3 --release-channel=regular` |
| Get kubeconfig | `az aks get-credentials -g <rg> -n <aks>` | `gcloud container clusters get-credentials <gke> --region=europe-west3` |
| Attach registry | `az aks update -g <rg> -n <aks> --attach-acr <acr>` | (pull via ImagePullSecrets or workload identity) |
| Upgrade | `az aks upgrade -g <rg> -n <aks> --kubernetes-version <next-minor>` | handled by release channel; force with `gcloud container clusters upgrade` |
| Stop the dev cluster | `az aks stop -g <rg> -n <aks>` | (scale to zero instead: Autopilot bills pods, not nodes) |
| Delete | `az aks delete -g <rg> -n <aks> -y` | `gcloud container clusters delete <gke> --region=europe-west3 -q` |

## Storage and Database

| Task | az | gcloud |
| --- | --- | --- |
| Create object store | `az storage account create -g <rg> -n <st> --sku Standard_ZRS --allow-blob-public-access false` | `gcloud storage buckets create gs://<bucket> --location=europe-west3 --uniform-bucket-level-access` |
| Upload / list | `az storage blob upload -d <file> -c <container> -n <name> --auth-mode login` | `gcloud storage cp <file> gs://<bucket>/<path>` |
| Sync a directory | `az storage blob sync -c <container> --account-name <st> -s ./site` | `gcloud storage rsync ./site gs://<bucket>/site` |
| Presign / sign URL | `az storage blob generate-sas ...` (user delegation) | `gcloud storage sign-url --uri=gs://<bucket>/<obj> --duration=15m` |
| Managed PostgreSQL | `az postgres flexible-server create -g <rg> -n <psql> --vnet <vnet> --subnet <snet>` | `gcloud sql instances create <psql> --database-version=POSTGRES_16 --no-assign-ip --availability-type=REGIONAL` |
| DB firewall / access | (VNet rules by default) | Auth Proxy or IAM auth |

## Serverless and Registry

| Task | az | gcloud |
| --- | --- | --- |
| Deploy container, serverless | `az containerapp create -g <rg> -n <app> --environment <env> --image <img> --target-port 8080 --ingress external` | `gcloud run deploy <svc> --image=<img> --region=europe-west3` |
| Deploy from source | `az acr build -r <acr> -t <img> .` then `az containerapp update` | `gcloud run deploy <svc> --source=. --region=europe-west3` |
| Split traffic | `az containerapp ingress traffic update -n <app> --revision-weight <rev>=10` | `gcloud run services update-traffic <svc> --to-revisions=<rev>=10` |
| Roll back | `az containerapp revision rollback -n <app> -g <rg> --revision <rev>` | `gcloud run revisions rollback <rev> --region=europe-west3` |
| Push an image | `az acr login -n <acr>` then `docker push <acr>.azurecr.io/<img>` | `gcloud auth configure-docker <region>-docker.pkg.dev` then `docker push <region>-docker.pkg.dev/<project>/<repo>/<img>` |

## Cost and Cleanup

| Task | az | gcloud |
| --- | --- | --- |
| Current spend view | `az costmanagement query ...` (or portal Cost Management) | `gcloud billing accounts list` + console budgets |
| Create a budget | `az consumption budget create --budget-name <b> --amount 10 --time-grain Monthly --category Cost` | `gcloud billing budgets create --billing-account=<id> --display-name=<b> --budget-amount=10USD` |
| What exists? | `az resource list -g <rg> -o table` | `gcloud asset search-all-resources --scope=projects/<project>` |
| Delete a boundary | `az group delete -n <rg> -y` | `gcloud projects delete <project-id>` |
