# Chapter 1 - The Azure Landscape: Tenants, Subscriptions, and the az CLI {#ch1}

## 1.1 The Hierarchy: Tenant, Management Group, Subscription, Resource Group

Azure organizes everything into a five-level hierarchy, and the fastest way for an AWS-native engineer to internalize it is to map each level to its nearest AWS cousin and then note where the analogy breaks. At the top sits the **tenant**: one dedicated instance of Microsoft Entra ID, the identity directory. This is the piece with no clean AWS equivalent - AWS keeps identity per-account inside IAM, while Azure keeps one directory for an entire organization and every subscription below it trusts that directory. **Management groups** sit above subscriptions and carry policies and inheritance the way AWS Organizations carries SCPs: a policy set at the top denies costly resources everywhere beneath it, no matter what any identity says. The **subscription** is the billing, quota, and access boundary and plays the role of the AWS account - but it is *enrolled in* the tenant rather than owning its own directory, which is why a company can have forty subscriptions sharing one identity plane. Inside a subscription, every resource must live in exactly one **resource group** - a container you delete as a unit. AWS has no structural equivalent (its answer is tagging discipline); the resource group is Azure's answer, and it changes how you think about cleanup, because deleting it deletes everything inside.

Two habits follow from the hierarchy, and both appear through the book. First, *the subscription is the blast-radius boundary you actually buy*: labs, staging, and production get separate subscriptions, because quotas, budgets, and RBAC all stop at that line. Second, *the resource group is a lifecycle statement, not a folder*: everything in `rg-shopnow-prod` is expected to die together, which makes it the natural unit for the Bicep deployments of [Chapter 3](#ch3) and for every cleanup step in this book's labs.

::: {.warn}
**Watch out - a resource group delete is recursive and unrecoverable**

`az group delete` removes the group *and every resource inside it* - VMs, disks, databases, everything - with no recycle bin. There is no S3-style versioning for infrastructure. The professional pattern is one resource group per stack per environment, so a mistake deletes a stack, not a platform; and production resource groups get guarded by Azure RBAC and locks (`az lock create --lock-type CanNotDelete`) rather than by hope.
:::

## 1.2 Regions and Availability Zones

A **region** is a deployment geography - `westeurope` (Amsterdam) and `germanywestcentral` (Frankfurt) are two of the dozens - and inside most regions, three or more **availability zones**, physically separate datacenter clusters with independent power and networking. Two details differ from AWS in ways that matter. First, zone identity is *stable*: zone `1` means the same physical zone for every subscription in a region, so a colleague's "zone 3 had an incident" is meaningful in a way that `us-east-1a` never is on AWS, where the letters shuffle per account. Second, regions come in official **region pairs** - geographies paired for platform-level disaster recovery (for the two regions above, North Europe pairs with Sweden Central and West Europe with Germany West Central) - so paired-region replication choices are one decision, not a design exercise. Not every service or VM size exists in every region, and prices differ between them: before designing around a capability, `az account list-locations` and the region-products page are worth thirty seconds.

All Azure examples in this book use `westeurope` - deliberately next door to the `eu-central-1` Frankfurt Region the AWS book used, so the series' examples sit in one neighborhood. Substitute your own region consistently, because a resource created in one region is invisible to a CLI pointed at another: the same "it disappeared!" false alarm as AWS, with the same cure.

## 1.3 The az CLI and First Sign-In

The **az CLI** is the book's steering wheel, exactly as the AWS CLI was in the previous volume: the portal is for looking, the CLI is for doing, and Bicep in [Chapter 3](#ch3) is the CLI's declarative older sibling. Install it for your platform (the Microsoft docs own the moving details), then sign in and verify:

```bash
az login                 # opens a browser; add --use-device-code on a headless box
az account show          # the subscription your commands will hit
az ad signed-in-user show   # who you are in the tenant (Entra ID)
```

`az login` authenticates you against the tenant and lists the subscriptions you can reach; the one marked `isDefault` receives every subsequent command. That default lives in a config file you manage with `az configure -d`, and like the AWS CLI the tool takes `-o json|table|tsv` and `--query` (the same JMESPath dialect as AWS) on every command:

```bash
az configure -d location=westeurope group=rg-shopnow-dev output=json
az vm list -d --query '[].[name, powerState, hardwareProfile.vmSize]' -o table
```

::: {.note}
**Best practice - the CLI is two APIs in one tool**

Every `az` command is a thin wrapper over either the **Azure Resource Manager** (ARM) control plane or the **Microsoft Graph** identity plane, and the prefix tells you which: `az resource`/`az vm`/`az group` talk to ARM, `az ad`/`az role` talk to Graph. When the portal shows a setting the CLI seems not to have, `az resource show --ids <id>` dumps the raw ARM object - the same "describe it and read the JSON" reflex the AWS book taught, and just as often the fastest route to understanding.
:::

## 1.4 The Free Grant and the First Budget

New Azure accounts start with a free credit for the first thirty days plus a rotating set of always-free service allowances, and the exact shape of that offer changes often enough that this book does not copy the numbers: read the official free-account page once, then do what the AWS book taught on day one - *budget visibility before the first resource*. Azure budgets live in Cost Management and alert at threshold percentages you choose; the CLI path needs a JSON body, which is one reason most teams create the first budget in the portal and only automate it later:

```bash
az consumption budget create \
  --budget-name budget-shopnow-dev --amount 10 --time-grain Monthly \
  --category Cost --resource-group rg-shopnow-dev \
  --notifications '{"alerts":{"enabled":true,"operator":"GreaterThanThreshold","threshold":80,"contact-emails":["ops@example.com"]}}'
```

::: {.warn}
**Watch out - a budget is not a spending cap**

Like the AWS billing alarm, an Azure budget notifies; it does not stop the meter. The guards that actually bite are Azure Policy (a management-group rule that denies expensive SKUs or untagged resources), quota limits, and the resource-group discipline from [Section 1.1](#ch1). Every lab in this book ends with an explicit cleanup step for the same reason the AWS labs did.
:::

## 1.5 Resource Groups as the Unit of Housekeeping

Everything the running example creates lives in resource groups named for the stack and the environment - `rg-shopnow-dev` for the labs, `rg-shopnow-prod` for the deployment pipeline in [Chapter 7](#ch7) - because the group name is the delete button and the access boundary in one. Tags still matter inside the group (`az tag create --resource-id <id> --tags project=shopnow owner=platform env=dev`), because cost reports and cleanup scripts in a large subscription cut by tag, not by group. And when a group grows too many unrelated resources, that is the design telling you the stack has outgrown its lifecycle: split the group at the next Bicep change, not after the next incident.

The book's running example starts here and grows one service per chapter, mirroring the AWS volume so the deltas stay visible: a couple of web servers ([Chapter 3](#ch3)) in a network you own ([Chapter 4](#ch4)), static assets and a database ([Chapter 4](#ch4)), a Kubernetes deployment (AKS, [Chapter 5](#ch5)), serverless glue (Functions and Container Apps, [Chapter 6](#ch6)), a keyless deploy pipeline ([Chapter 7](#ch7)) - and then Part II does it all again on Google Cloud, with the capstone ([Chapter 15](#ch15)) putting the two pictures and the AWS one side by side.

**See also:** [Chapter 2](#ch2) builds the identity and permission system every `az` command silently leaned on, and [Chapter 3](#ch3) turns this chapter's hierarchy into actual machines with Bicep.
