# Appendix A - The AWS → Azure → GCP Service Map {#appA}

This appendix is the translation table the whole book assumes: the AWS column names the concept from *AWS for DevOps Engineers*, and the other two columns say what the platform calls it and where in this book it lives. Names drift and products get renamed; when a row looks wrong, the console is the source of truth and this table is the index.

## The Core Vocabulary

| Concept | AWS | Azure | Google Cloud | In this book |
| --- | --- | --- | --- | --- |
| Isolation / billing boundary | Account | Subscription | Project | [Ch. 1](#ch1), [Ch. 8](#ch8) |
| Org-level guardrails | Organizations + SCPs | Management groups + Azure Policy | Organization + org policies | [Ch. 1](#ch1), [Ch. 8](#ch8), [Ch. 9](#ch9) |
| Resource grouping | Tags (by convention) | Resource group | Labels + project structure | [Ch. 1](#ch1), [Ch. 3](#ch3) |
| Identity directory | IAM (+ Identity Center) | Microsoft Entra ID | Cloud Identity / Google Workspace | [Ch. 2](#ch2), [Ch. 9](#ch9) |
| Role for a machine | IAM role (instance profile) | Managed identity (system/user-assigned) | Service account (attached) | [Ch. 2](#ch2), [Ch. 9](#ch9), [Ch. 12](#ch12) |
| Pod-level identity | IRSA | Workload identity federation | Workload Identity for GKE | [Ch. 5](#ch5), [Ch. 12](#ch12) |
| CI trust object | OIDC role + `sub` claim | Federated identity credential (FIC) | WIF pool + provider | [Ch. 7](#ch7), [Ch. 14](#ch14) |
| Region | Region (e.g. `eu-central-1`) | Region (e.g. `westeurope`) | Region (e.g. `europe-west3`) | [Ch. 1](#ch1), [Ch. 8](#ch8) |
| Availability zone | AZ (letters shuffle per account) | Availability zone (stable 1/2/3) | Zone (`-a`, `-b`, `-c`) | [Ch. 1](#ch1), [Ch. 8](#ch8), [Ch. 10](#ch10) |

## Compute, Containers, and Serverless

| Capability | AWS | Azure | Google Cloud | In this book |
| --- | --- | --- | --- | --- |
| Virtual machines | EC2 | Virtual Machines | Compute Engine | [Ch. 3](#ch3), [Ch. 10](#ch10) |
| Burstable small VM | `t3` / `t4g` | B-series | E2 (+ custom types) | [Ch. 3](#ch3), [Ch. 10](#ch10) |
| Autoscaling group | Auto Scaling Group | VM Scale Set (VMSS) | Managed Instance Group (MIG) | [Ch. 3](#ch3), [Ch. 10](#ch10) |
| Block storage | EBS (gp3) | Managed disks (Premium v2) | Persistent Disk / Hyperdisk | [Ch. 3](#ch3), [Ch. 10](#ch10) |
| Managed Kubernetes | EKS | AKS | GKE (Autopilot / Standard) | [Ch. 5](#ch5), [Ch. 7](#ch7), [Ch. 12](#ch12) |
| Serverless containers | Fargate / App Runner | Container Apps | Cloud Run | [Ch. 6](#ch6), [Ch. 13](#ch13) |
| Functions | Lambda | Azure Functions (Flex Consumption) | Cloud Run functions | [Ch. 6](#ch6), [Ch. 13](#ch13) |
| Container registry | ECR | ACR | Artifact Registry | [Ch. 7](#ch7), [Ch. 14](#ch14) |
| Registry build service | - (Actions/CodeBuild) | `az acr build` (ACR Tasks) | Cloud Build | [Ch. 7](#ch7), [Ch. 14](#ch14) |

## Network, Storage, and Data

| Capability | AWS | Azure | Google Cloud | In this book |
| --- | --- | --- | --- | --- |
| Software-defined network | VPC (regional) | VNet (regional) | VPC (global; subnets regional) | [Ch. 4](#ch4), [Ch. 10](#ch10) |
| Instance firewall | Security group | NSG (+ ASGs) | Firewall rules (+ network tags) | [Ch. 4](#ch4), [Ch. 10](#ch10) |
| Private service access | VPC endpoints | Private endpoints | Private Service Connect / PGA | [Ch. 4](#ch4), [Ch. 10](#ch10) |
| Managed NAT | NAT Gateway | NAT Gateway / managed egress | Cloud NAT / Direct VPC egress | [Ch. 4](#ch4), [Ch. 10](#ch10), [Ch. 13](#ch13) |
| Object storage | S3 | Blob Storage | Cloud Storage | [Ch. 4](#ch4), [Ch. 11](#ch11) |
| Archive tier | Glacier tiers | Cool/Cold/Archive | Nearline/Coldline/Archive | [Ch. 4](#ch4), [Ch. 11](#ch11) |
| Presigned URL | S3 presigned | User-delegation SAS | Signed URL (v4) | [Ch. 4](#ch4), [Ch. 11](#ch11) |
| Managed PostgreSQL | RDS | Flexible Server | Cloud SQL (+ AlloyDB) | [Ch. 4](#ch4), [Ch. 11](#ch11) |
| DB private connect | Subnet groups / RDS Proxy | VNet integration | PSC + Auth Proxy | [Ch. 4](#ch4), [Ch. 11](#ch11), [Ch. 13](#ch13) |

## Delivery, Operations, and Cost

| Capability | AWS | Azure | Google Cloud | In this book |
| --- | --- | --- | --- | --- |
| CI/CD of record | GitHub Actions + OIDC role | GitHub Actions + FIC | GitHub Actions + WIF | [Ch. 7](#ch7), [Ch. 14](#ch14) |
| Infrastructure as code | Terraform | Bicep (Terraform for multi-cloud) | Terraform | [Ch. 3](#ch3), [Ch. 15](#ch15), [Ch. 16](#ch16) |
| Metrics & dashboards | CloudWatch | Azure Monitor | Cloud Monitoring | *Prometheus & Grafana* volume |
| Log search | CloudWatch Logs | Log Analytics | Cloud Logging | *Elastic Stack* volume |
| Budgets / cost tools | Budgets + Cost Explorer | Cost Management budgets | Budgets + billing export | [Ch. 1](#ch1), [Ch. 8](#ch8), [Ch. 16](#ch16) |
| Config / policy engine | Config + SCPs | Azure Policy | Org policy + Asset Inventory | [Ch. 1](#ch1), [Ch. 9](#ch9) |
| Secrets | Secrets Manager | Key Vault | Secret Manager | [Ch. 5](#ch5), [Ch. 12](#ch12) |
| Browser shell | CloudShell | Cloud Shell | Cloud Shell | [Ch. 1](#ch1), [Ch. 8](#ch8) |
