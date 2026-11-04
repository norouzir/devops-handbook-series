# Chapter 2 - Identity and Access: Microsoft Entra ID, RBAC, and Managed Identities {#ch2}

## 2.1 One Directory, Two Permission Systems

The AWS book spent its identity chapter on IAM because AWS has exactly one permission system. Azure has two, and confusing them is the most common identity mistake in the platform. **Microsoft Entra ID** (renamed from Azure AD in 2023; the new name is used throughout) is the tenant's directory and owns *tenant-plane* power through **Entra directory roles** such as Global Administrator and User Administrator - the ability to create users, register applications, and reset credentials. **Azure RBAC**, by contrast, governs *resources* - VMs, storage accounts, AKS clusters - through role assignments on the ARM hierarchy from [Chapter 1](#ch1). A Global Administrator is not a Contributor on anything; an Owner of the subscription may still be a plain user in the directory. The nearest AWS analogy: directory roles are like the powers of the management account's root, RBAC is IAM, and neither implies the other.

The professional posture mirrors the AWS book's root-user rule: directory-role holders are few, MFA-enforced, and time-boxed; everything daily happens in Azure RBAC, and everything programmatic happens through identities this chapter builds in [Section 2.3](#ch2) and [Section 2.4](#ch2).

## 2.2 RBAC: Roles, Scopes, and Inheritance

An Azure RBAC **role assignment** is a triple - *who* (principal), *what* (role definition), *where* (scope) - and scope is a strict ladder: management group, subscription, resource group, resource. Assignments inherit downward, so `Contributor` on `rg-shopnow-dev` grants it on every resource the group will ever contain, which is exactly why the resource-group-per-stack habit from [Chapter 1](#ch1) is also a security design. The built-in roles cover the daily vocabulary: **Owner** (everything plus delegate), **Contributor** (everything except grant access), **Reader** (see, not touch), plus thousands of service-specific roles that matter more than they first appear - see the warning below. The CLI round-trip is the fastest way to learn the model:

```bash
az role assignment list \
  --resource-group rg-shopnow-dev \
  --query '[].[principalName, roleDefinitionName, scope]' -o table

az role assignment create \
  --assignee <user-or-app-id> \
  --role "Virtual Machine Contributor" \
  --resource-group rg-shopnow-dev
```

::: {.warn}
**Watch out - Contributor cannot read your blobs**

Azure RBAC *control-plane* roles manage resources but say nothing about their *data*: `Contributor` on a storage account can delete it and still cannot read one blob, because blob reads need a data-plane role such as **Storage Blob Data Contributor**. AWS blends the two in its IAM actions, so this split catches everyone once. When a CLI call fails with `AuthorizationPermissionMismatch` on an otherwise healthy resource, suspect the data plane: `az role assignment create --role "Storage Blob Data Contributor" ...` is usually the fix.
:::

## 2.3 Users, Groups, and Service Principals

Humans in Entra ID authenticate with their organization identity - SSO, MFA, conditional access - and there is no equivalent of the long-lived IAM user with embedded keys, which is a genuine improvement worth naming. Access lands on **groups**, not individuals: assign a role to the group `grp-platform-devs` once, and membership changes do the rest - the same pattern as AWS Identity Center's groups, and just as non-negotiable. Code needs its own identity: an **app registration** is the application's directory object (the blueprints), and a **service principal** is its instance in *your* tenant (the thing you assign roles to). Where AWS would create a role with a trust policy, Azure creates a service principal - and where the AWS role's trust was "this AWS service may assume me," the Azure equivalent for pipelines is the **federated identity credential** of [Section 2.5](#ch2): an OIDC trust pointing at GitHub. Client secrets and certificates exist for the edge cases, but in October 2026 the default is federation, and this book never stores a client secret anywhere.

## 2.4 Managed Identities: Roles for Workloads

A **managed identity** is a service principal Entra ID manages for you: no credential to create, rotate, or leak, because the credentials never exist outside the platform. The **system-assigned** flavor is born with the resource and dies with it (the closest cousin of the EC2 instance profile), while the **user-assigned** flavor is a standalone identity you attach to one or many resources (the cousin of a reusable IAM role). The mechanics are invisible from the command line and near-identical to AWS from inside the machine: the workload asks the well-known address `http://169.254.169.254` for a token, and application code that uses a credential chain - `DefaultAzureCredential` in the Azure SDKs - picks it up with no changes between laptop, VM, and cluster:

```bash
az vm identity assign -g rg-shopnow-dev -n shopnow-web-01
az role assignment create \
  --assignee-object-id <mi-object-id> --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope $(az storage account show -g rg-shopnow-dev -n stshopnowdev --query id -o tsv)
```

::: {.note}
**Best practice - user-assigned for anything shared, system-assigned for anything alone**

System-assigned identities are the least config for a resource that stands alone; user-assigned identities shine when several resources share one identity or when the identity must outlive the machine that uses it - AKS in [Chapter 5](#ch5) and Container Apps in [Chapter 6](#ch6) both lean on user-assigned identities for exactly that reason. Either way the rule from the AWS book holds: *no workload ever holds a static credential*.
:::

## 2.5 Federated Credentials: OIDC for Pipelines

The last identity type is the one CI/CD runs on. A **federated identity credential (FIC)** attaches an external OIDC trust to a service principal or managed identity: *when GitHub Actions presents a token signed by `https://token.actions.githubusercontent.com` with subject `repo:org/shopnow:ref:refs/heads/main`, treat it as this identity.* No secret is stored, the trust is revocable per branch or per environment, and it is the direct sibling of the AWS OIDC role trust in the previous volume - same idea, different vocabulary, and the mid-2026 GitHub `sub` claim change that book documented applies here too ([Chapter 7](#ch7) shows the full setup and the exact subject formats). Between groups for humans, managed identities for workloads, and federated credentials for pipelines, the platform has no remaining excuse for a stored password - and neither does this book.

**See also:** [Chapter 1](#ch1) set the hierarchy these assignments attach to, [Chapter 5](#ch5) extends workload identity into Kubernetes, and [Chapter 7](#ch7) turns this section into a working pipeline.
