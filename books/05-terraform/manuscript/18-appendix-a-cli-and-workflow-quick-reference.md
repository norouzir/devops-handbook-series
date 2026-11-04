# Appendix A - CLI and Workflow Quick Reference {#appA}

## A.1 The Command Surface

```console
# lifecycle
terraform init [-upgrade] [-migrate-state]   # providers, modules, backend
terraform plan  [-out=tfplan] [-refresh=false] [-target=<addr>] [-replace=<addr>]
terraform apply [tfplan] [-auto-approve] [-refresh-only]
terraform destroy [-target=<addr>]

# inspection
terraform state list                         # all resource addresses
terraform state show <addr>                  # one resource's stored attributes
terraform show tfplan                        # human plan | -json for machines
terraform output [-json]                     # root outputs after apply
terraform providers                          # requirements tree / lock status
terraform graph | dot -Tsvg > graph.svg      # dependency graph

# state surgery (Chapter 7)
terraform state mv <src> <dst>
terraform state rm <addr>
terraform import <addr> <id>                 # classic import
terraform force-unlock <lock-id>             # after confirming no live run

# workspace (Chapter 9)
terraform workspace new|select|list|delete <name>

# test and policy (Chapter 11)
terraform test [-filter=tests/foo.tftest.hcl] [-verbose]
terraform apply tfplan -policies ./policy/   # Terraform Policy (GA, 1.17)
terraform plan -minimal-refresh              # cheaper refresh (1.17)
```

## A.2 The Flags That Carry Incidents

| Flag | Command | Meaning |
|------|---------|---------|
| `-out=tfplan` | plan | Save the computed plan; apply the file, not a re-plan |
| `-detailed-exitcode` | plan | 0 = no changes, 1 = error, 2 = changes (drift jobs key on 2) |
| `-refresh-only` | apply | Update state to match reality; propose nothing |
| `-refresh=false` | plan | Skip the refresh pass (speed) |
| `-target=<addr>` | plan/apply/destroy | Limit to one resource and its dependencies |
| `-replace=<addr>` | plan | Force recreation of one object (successor to `taint`) |
| `-parallelism=n` | plan/apply | Concurrent graph walk width (default 10) |
| `-var` / `-var-file` | plan/apply | Input values; explicit files over `*.auto.tfvars` |
| `-input=false` | init/plan/apply | Never wait for interactive prompts (CI mandatory) |
| `-lock=false` | plan/apply | Disable state locking - *never* in shared environments |

## A.3 Backend Configuration Keys (s3 shown; siblings rhyme)

```hcl
terraform {
  backend "s3" {
    bucket         = "atlas-tfstate-eu"   # storage bucket
    key            = "prod/network/terraform.tfstate"  # path = the address
    region         = "eu-central-1"
    use_lockfile   = true                 # native locking (1.10+)
    encrypt        = true                 # SSE at rest
    dynamodb_table = null                 # legacy locking; retired by use_lockfile
  }
}
```

The `key` *is* the state's identity: moving an environment's key is a state migration (`init -migrate-state`), not a rename. Azure (`azurerm`: `resource_group_name`, `storage_account_name`, `container_name`, `key`) and GCS (`gcs`: `bucket`, `prefix`) follow the same shape.

## A.4 Variable Precedence, Condensed

From weakest to strongest: `default` in the `variable` block → `terraform.tfvars` → `*.auto.tfvars` (alphabetical - banned by convention, [Chapter 9](#ch9)) → `-var-file` flags (later wins) → `-var` flags → `TF_VAR_<name>` environment variables. When two sources *should* disagree deliberately, name the files (`prod.tfvars`, `prod-secrets.tfvars`) and pass them explicitly in the pipeline - precedence by file order is precedence by accident.

## A.5 The Files, Their Fates

| File | Commit? | What it is |
|------|---------|------------|
| `.terraform/` | never | Working dir: providers, modules, plan leftovers |
| `.terraform.lock.hcl` | always | Pinned provider versions + checksums |
| `terraform.tfstate` (+ `.backup`) | never | The state database (secrets inside!) |
| `*.tfvars` (plain) | usually | Committed environment values |
| `*secret*.tfvars`, `*.auto.tfvars` | policy | Generated/injected, never committed |
| `tfplan` | never | Sensitive plan artifact, short life |
| `.terraform-version` | always | The pin that keeps laptops and CI honest |
