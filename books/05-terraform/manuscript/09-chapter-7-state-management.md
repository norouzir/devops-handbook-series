# Chapter 7 - State Management {#ch7}

## 7.1 What State Actually Is

`terraform.tfstate` is Terraform's database: a JSON document mapping each resource *address* in your configuration to the real-world object's *identifier* plus every attribute the provider reported at last apply. The plan diff of [Chapter 6](#ch6) is computed against this record; the graph's parallelism, the "0 to destroy" reassurance, and `terraform output` all read from it. Three properties of state drive every policy in this chapter. State is *authoritative for the diff* - what is not in state does not exist to Terraform, and what is in state but not in configuration is scheduled for destruction (that is how deletion from code becomes deletion of infrastructure). State is *sensitive* - it stores the full attribute set of every managed object, including secrets that providers return (database passwords, private keys), regardless of `sensitive` markers, which affect display only. And state is *concurrency-hostile* - two applies against one state file corrupt it, which is why locking exists.

## 7.2 Remote Backends and Locking

A *backend* answers two questions: where state lives, and who serializes writes. The `terraform` block's `backend` stanza (initialized with `terraform init` - it will offer to migrate existing state) moves state from your laptop to shared storage:

```hcl
terraform {
  backend "s3" {
    bucket       = "atlas-tfstate-eu"
    key          = "prod/network/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true          # native S3 locking via lock files (Terraform 1.10+)
    encrypt      = true
  }
}
```

The workhorse backends in 2026: `s3` (AWS, now with native lockfile locking - the old DynamoDB table dance is retired), `azurerm` (Azure blob with blob leases for locking), `gcs` (Google), `kubernetes`/`consul` for in-platform storage, `pg` for anything with Postgres, and `local` for solo work and labs. On top of any backend sit the *state platforms* - HCP Terraform workspaces and Terraform Enterprise - which add locking, run history, remote execution, and policy gates ([Chapter 13](#ch13)). The choice rule is boring: whatever your team already trusts for durable, access-controlled, encrypted storage; the *mandatory* part is remote-plus-locking for anything shared.

::: {.note}
**Best practice - one state per blast radius**

Partition state by change frequency and blast radius, not by convenience: network and clusters in one state, per-team application stacks in their own, per-environment always. A single global state makes every plan slow (full refresh) and every mistake expensive; a sensible partition makes `apply` parallel across teams and an incident local. [Chapter 9](#ch9) turns this into a layout.
:::

## 7.3 The State Command Family: Surgery With Rules

`terraform state` is the toolkit for correcting the state-to-reality mapping. `state list` enumerates addresses (the first command to run in any state confusion); `state show <address>` renders one resource's stored attributes; `state pull`/`state push` move raw state (with `push` disabled by safety interlocks - force-pushing over a newer version requires `-force` and a very good story). The editing pair: `state mv <src> <dst>` re-addresses an object *without touching real infrastructure* - the tool behind renames and refactors, and largely superseded by declarative `moved` blocks; and `state rm <address>` *forgets* an object - Terraform stops managing it, and nothing in the real world changes. Half the "Terraform deleted my X" folklore is `state rm` followed by a separate, manual deletion, and the other half is `state rm` on something you *meant* to keep managed.

```console
$ terraform state list
docker_network.app
docker_container.web

$ terraform state mv docker_container.web docker_container.proxy
Move "docker_container.web" to "docker_container.proxy"
Successful move!

$ terraform state rm docker_container.web
Removed docker_container.web
Successfully removed 1 resource instance(s).
```

::: {.warn}
**Watch out - `state rm` is not delete, and delete is not `state rm`**

`state rm` unlinks the record; the object keeps running, unmanaged. Deleting the resource *block* from configuration (without a `removed` block) does the opposite of what beginners expect in one direction only: the next plan schedules the *destruction* of the real object. Removing something from Terraform's care while it keeps running = `state rm` (or the declarative `removed` block below). Deleting the object entirely = remove the block and let the plan destroy it.
:::

## 7.4 Importing: Adoption Without Destruction

*Import* teaches Terraform about infrastructure that already exists. The classic flow - `terraform import <address> <id>` plus hand-writing the resource block - is now the low-level path. The declarative `import` block (Terraform 1.5+) expresses intent in configuration, and `terraform plan -generate-config-out=generated.tf` writes a first-draft resource block from the imported object's attributes:

```hcl
import {
  to = docker_container.legacy
  id = "legacy-web"
}
```

```console
$ terraform plan -generate-config-out=generated.tf
$ # review, reformat, fold into modules; then apply the import plan
```

The discipline that keeps imports honest: the resource block must be written to *match reality* (fields sourced from data sources or variables exactly as they exist), or the first post-import plan proposes "correcting" a production object you merely meant to adopt. Import is also the foundation of the *strangler-fig migration* - adopting an estate cloud-by-cloud, state-by-state - and of escaping the console without a rebuild.

## 7.5 `removed` Blocks: Unmanaging By Design

Since Terraform 1.7, the declarative counterpart of `state rm` is the `removed` block: commit the intent, let the plan show it, review it like any other change:

```hcl
removed {
  from = docker_container.sandbox

  lifecycle {
    destroy = false        # keep the object running, just stop managing it
  }
}
```

`destroy = false` unlinks; `destroy = true` (the default) destroys the object as part of the apply. The block belongs in configuration review like any deletion - which is exactly the point: unmanaging production objects stops being a tribal secret and becomes a diff.

## 7.6 Recovering From State Disasters

The four states of state trouble, and the moves: *lost* (backend deleted) - restore from versioning (S3 bucket versions, blob snapshots) which is why `encrypt` and versioning are non-negotiable; *corrupt* - Terraform writes `terraform.tfstate.backup` before every write, and backends snapshot similarly, so roll back to the last good copy; *divergent* (state says one thing, reality another) - `refresh-only` apply to accept reality, or a normal plan to restore the configuration, per [Chapter 6](#ch6); *locked* (a crashed run left the lock behind) - inspect `terraform force-unlock <lock-id>` *only after* confirming no run is actually in flight. And the meta-move: because remote backends version state, none of these are data-loss events if the platform was set up with any care at all - state hygiene is an insurance policy written in [Chapter 9](#ch9)'s layout and collected here.

## 7.7 Lab 3: State Clinic - Move, Forget, Adopt

::: {.lab}
### Lab 3 - State surgery on a live (disposable) estate {#lab3}

1. From the Chapter 6 project, rename the container resource in configuration *without* a `moved` block; run plan and observe the destroy/create. Revert. Now add `moved { from = docker_container.web  to = docker_container.web2 }`, re-plan: zero changes to infrastructure, pure re-addressing. Apply.
2. Hand-edit nothing; instead run `terraform state mv` on a throwaway copy of the project (local backend) and diff the two approaches in `state list`. Note which one survives code review: the `moved` block is in git, the CLI move is in your shell history.
3. Adopt-by-import: create a container *outside* Terraform (`docker run -d --name stray nginx`), add an empty-shaped `docker_container.stray` block, write an `import` block for it, and use `plan -generate-config-out` to draft its configuration; reconcile the draft (ports, image digest) until the post-import plan is clean.
4. Unmanage on purpose: add a `removed` block with `destroy = false` for one container, plan, verify the plan shows removal-from-management and *no destroy*, apply, and confirm with `docker ps` that it still runs - and `state list` that Terraform forgot it.
5. Break and repair: `mv terraform.tfstate terraform.tfstate.hidden`, run plan, and read the from-nothing proposal; restore the file, re-plan, confirm the diff returns to zero. You have now seen both halves of a divergent state and know the repair direction for each.
:::

**See also:** [Chapter 9](#ch9) for partitioning state across environments, [Chapter 10](#ch10) for the secrets-inside-state problem, and [Chapter 14](#ch14) for refactoring estates with `moved` at scale.
