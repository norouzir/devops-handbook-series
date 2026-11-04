# Chapter 4 - Networking and Storage: VNets, NSGs, Blob, and Managed Databases {#ch4}

## 4.1 VNets: The Network You Own

A **VNet** is the AWS VPC analog with one structural difference: address spaces are declared on the VNet and carved into **subnets**, each regional, each in exactly one VNet. Routing needs no tables for the happy path - system routes handle intra-VNet and internet egress - and **route tables** (UDRs) appear only when you steer traffic at a firewall appliance, exactly when they do on AWS. The **NSG** is the security group, with two twists that change daily life. First, it attaches to *subnets or NICs* rather than living only on the instance, so a subnet-level NSG becomes the enforcement layer every resource inherits. Second, rules can reference **application security groups (ASGs)** - named groups of NICs like `asg-web` and `asg-db` - instead of security-group IDs, which makes rules read as policy instead of plumbing:

```bash
az network nsg rule create -g rg-shopnow-dev --nsg-name nsg-shopnow \
  -n allow-http-from-web --priority 110 --direction Inbound \
  --source-asgs asg-shopnow-web --destination-asgs asg-shopnow-db \
  --destination-port-range 5432 --protocol Tcp --access Allow
```

**Service tags** replace the AWS prefix-list habit (`VirtualNetwork`, `AzureCloud`, `Storage.WestEurope` as address sources), **peering** works like VPC peering - private, non-transitive, per-region in price - and hub-and-spoke with Azure Firewall is the mature shape at scale. For reaching Azure *services* privately, **private endpoints** (the interface-endpoint analog) put a VNet-internal IP in front of the storage account or database from [Section 4.3](#ch4), and **service endpoints** are the older, cheaper gateway-style cousin. For reaching VMs, **Azure Bastion** is the Session Manager analog: browser SSH/RDP with no public ports on the VM at all.

## 4.2 Storage Accounts: Blob, Tiers, and the Keys That Are Too Powerful

The **storage account** is the umbrella namespace - Blob (objects), Files, Queues, Tables - and Blob's **containers** are the buckets. The S3 vocabulary maps almost one-to-one: **access tiers** Hot, Cool, Cold, Archive stand in for Standard through Glacier, **lifecycle management policies** are the S3 lifecycle in JSON, **versioning** and **soft delete** protect against both fat fingers and ransomware, and **user-delegation SAS tokens** are presigned URLs signed with your Entra identity rather than an account key:

```bash
az storage account create -g rg-shopnow-dev -n stshopnowdev \
  --sku Standard_ZRS --kind StorageV2 --allow-blob-public-access false
az storage container create --account-name stshopnowdev -n uploads --auth-mode login
az storage blob upload --account-name stshopnowdev -c uploads -f asset.png -n assets/asset.png --auth-mode login
```

The security posture differs from AWS in a way worth internalizing: the account's two **keys** unlock *everything* - every service, every container, every operation - so the professional default is `--allow-shared-key-access false` on the account and Entra RBAC for all human access ([Chapter 2](#ch2)'s data-plane roles). On top of that, **public access** defaults to disabled for new accounts, **public access prevention** can forbid it account-wide, and **immutable storage** with time-based retention policies answers the S3 Object Lock use case.

For static hosting, the storage account's **static website** feature exposes the `$web` container on an `*.web.core.windows.net` endpoint - the S3-website-redirect equivalent, custom domains over CDN included. It is the fastest "ship the shopnow frontend" path in Part I, and the guided exercise below uses exactly that.

::: {.warn}
**Watch out - the account key is root for the account**

Leak a storage account key and every blob, queue, table, and file share in the account is read *and written* by whoever has it - there is no per-service scoping to soften the blow, short of rotating the key and breaking everything that used it. Disable shared-key access, use user-delegation SAS with short expiry for the one-off download, and hand applications managed identities from [Chapter 2](#ch2) instead of keys.
:::

## 4.3 Azure Database for PostgreSQL: The Managed Database

**Flexible Server** is the RDS of Azure: automated backups with point-in-time restore, a maintenance window you schedule, storage that autogrows, and high availability in two shapes - same-zone (fast failover) and zone-redundant (a standby in another zone). Creation is refreshingly one-command, and the two flags that matter most are the network answer and the HA answer:

```bash
az postgres flexible-server create \
  -g rg-shopnow-dev -n psql-shopnow-dev \
  --tier GeneralPurpose --sku-name Standard_D2ds_v4 \
  --version 16 --zone 1 --ha-enabled ZoneRedundant \
  --vnet vnet-shopnow --subnet snet-db
```

`--vnet` integrates the server into the network from [Section 4.1](#ch4) - private addressing, NSG rules, no public endpoint to forget about - which is the configuration the AWS book reached for with subnet groups and private subnets. Two Azure-native extras are worth adopting on day one: **Microsoft Entra authentication** for PostgreSQL (log in as your Entra identity, no passwords at all) and storage autogrow, which quietly removes the disk-full incident class. The single-server product this replaced is retired; anything older than Flexible Server is a migration ticket, not a choice.

## 4.4 Guided Exercise: A Static Site with Versioning and a Lifecycle

Between the labs of [Chapter 3](#ch3) and [Chapter 5](#ch5), a ten-minute walk-through of the storage chapter's pieces: create the account as in [Section 4.2](#ch4), enable `az storage blob service-properties update --static-website --index-document index.html`, push the shopnow landing page into `$web`, open the primary endpoint, then upload a second version of `index.html` with versioning on (`az storage account blob-service-properties update --enable-versioning true`) and watch `az storage blob list` keep both. Finish with a lifecycle policy JSON that cools `$web`'s leftovers to Cool after 90 days, apply it with `az storage account management-policy create`, and delete the resource group - the whole site was one account, which was the point.

::: {.note}
**Best practice - NSGs and ASGs make rules readable, so use them where people read them**

A rule saying "asg-shopnow-web to asg-shopnow-db on 5432" documents its own intent; a rule saying "10.1.2.0/24 to 10.1.3.0/24" documents an IP plan that will outlive its explanation. The AWS book's security-group-name discipline becomes, on Azure, ASG discipline - and because NSGs live at the subnet boundary, the platform team can enforce the shape once instead of auditing every NIC.
:::

**See also:** [Chapter 3](#ch3) put the first VM on a network like this one, [Chapter 5](#ch5) runs Kubernetes on it and extends identity into pods, and [Chapter 6](#ch6) lets Functions and Container Apps connect to the same database privately.
