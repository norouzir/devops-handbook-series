# Chapter 2 - Installing Terraform and Your First Project {#ch2}

## 2.1 Getting the Binary: Supported Install Paths

Terraform ships as a single static Go binary, which makes installation a non-event and *pinning* the interesting part. Every supported path resolves to the same artifact from the official releases site, and the differences are only about who keeps it current. On Linux, HashiCorp's apt repository (`apt install terraform` after registering the key) and the equivalent yum/dnf repositories track releases promptly; on macOS, Homebrew (`brew tap hashicorp/tap && brew install hashicorp/tap/terraform`) is the standard route; on Windows, Chocolatey or a plain download into a directory on `PATH` works. If you prefer the build-from-source religion, `go install github.com/hashicorp/terraform@v1.17.0` also works, but the release binaries are the tested artifact.

In practice, most professional teams skip direct installs in favor of a *version manager*, because the interesting question is never "what is the latest Terraform" but "which Terraform does this repository expect". `tenv` (which manages Terraform, OpenTofu, Terragrunt, and Atmos), `tfenv`, and `asdf` all read a version file in the repository - `.terraform-version` or `opentofu-version` for `tenv`-family tools - and put the right binary on `PATH` per directory. This book uses `tenv` in examples because it covers both Terraform and OpenTofu with one mental model, but any pinning mechanism that ends with a version file in `git` is fine. The pin matters more than the tool: CI, your colleagues, and your future self all get the same binary, and [Chapter 12](#ch12) relies on it.

::: {.note}
**Best practice - pin the version, file the upgrade**

Pin the CLI per repository and treat upgrades as deliberate, scheduled work - Terraform's 1.x line has been famously stable in the language, but provider upgrades and state format interactions are where upgrades bite. The upgrade checklist lives in [Chapter 14](#ch14); the habit starts on day one with a version file.
:::

Verification is a one-liner and a habit: `terraform version` prints the binary version and warns audibly when a newer patch release exists. For the book you need 1.17.x or any 1.10+ release (1.10 introduced the ephemeral-resource and write-only features that [Chapter 10](#ch10) uses).

```console
$ tenv terraform install 1.17.0
$ terraform version
Terraform v1.17.0
on linux_amd64
```

## 2.2 The Shape of a Terraform Project

A Terraform project is a *directory* - Terraform has no file naming constraints beyond "ends in `.tf`" (plus JSON), and it concatenates every `.tf` file in the working directory into one configuration. That freedom is a trap as much as a feature: `main.tf` holding everything is the beginner default, and it stops being maintainable around forty resources. The layout this book uses from the start is deliberately boring and scales to real estates:

```text
atlas-infra/
├── versions.tf      # required Terraform + provider versions
├── providers.tf     # provider configuration
├── variables.tf     # input variable declarations
├── locals.tf        # computed shared values
├── outputs.tf       # values other code can consume
├── main.tf          # primary resources
├── terraform.tfvars # default variable values (NOT secrets)
└── .gitignore       # .terraform/, *.tfstate, *.tfvars (secret ones)
```

Two files in that tree deserve immediate respect. `versions.tf` declares the `required_version` constraint and the required providers with their version constraints - it is the difference between "works on my machine" and a contract. `.gitignore` must exclude `.terraform/` (the working directory: downloaded providers, modules, plan leftovers) and every state file (`terraform.tfstate`, `terraform.tfstate.backup`) - state files routinely contain secrets and are machine-generated, and committing one to `git` is a rite of passage nobody should survive through. [Chapter 10](#ch10) handles secrets properly; the `$ git log` sweep for accidentally committed state is Chapter 10's least favorite Emergency Room.

## 2.3 Your First Configuration: Real Resources, Zero Cloud Bill

The labs in this book provision real, inspectable resources with no cloud account and no bill, using the Docker provider - a community-maintained plugin that talks to your local Docker daemon and treats containers, images, networks, and volumes as first-class infrastructure. The pedagogical point is the same one the Ansible book's container-fleet trick made: the workflow is identical whether the API behind the provider belongs to Docker or to AWS, so everything you learn here transfers by replacing `docker_*` resources with your platform's.

The first configuration provisions one network and one nginx container wired to it:

```hcl
# versions.tf
terraform {
  required_version = ">= 1.10"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}
```

```hcl
# main.tf
resource "docker_network" "app" {
  name = "atlas-net"
}

resource "docker_container" "web" {
  name  = "atlas-web"
  image = "nginx:1.27-alpine"

  ports {
    internal = 80
    external = 8080
  }

  networks_advanced {
    name = docker_network.app.name
  }
}
```

The four-step rhythm that runs this - and that runs everything else in this book - is worth narrating slowly, because it never changes again:

```console
$ terraform init        # download providers, prepare backend, lock versions
$ terraform plan        # compute and display the proposed change set
$ terraform apply       # execute it (asks for confirmation, or -auto-approve)
$ terraform destroy     # tear down everything this configuration created
```

`terraform init` reads `versions.tf`, fetches the Docker provider into `.terraform/providers/`, and writes `.terraform.lock.hcl` recording the exact provider versions selected - the lock file is *your friend* and gets committed (Section 2.4). `terraform plan` builds a dependency graph, refreshes its view of reality from state, and prints the plan: one network to add, one container to add, nothing else. `terraform apply` shows the same plan, waits for `yes`, executes the creates in dependency order (network before container), and writes `terraform.tfstate` - the record that the container named `atlas-web` is now Terraform's business. Open another terminal and `docker ps`: the container is real, and `curl localhost:8080` returns nginx's welcome page. Now edit the port to `8081`, `plan` again - the diff shows exactly one update-in-place - and `apply` it. That read-plan-execute loop, with diffs you can predict before seeing them, is the entire skill; the rest of the book is its edge cases.

## 2.4 The Files Terraform Manages Around You

Three artifacts appear after the first run and each has a policy. `.terraform/` is a cache and working directory - never commit, always recreatable by `init`. `.terraform.lock.hcl` pins provider checksums and versions - always commit; it is what makes `init` on your colleague's laptop and in CI produce the same provider set, and it is updated deliberately with `terraform providers lock` or `-upgrade` when you *decide* to move ([Chapter 4](#ch4)). `terraform.tfstate` is the database of what Terraform manages - never commit (secrets plus concurrent-write corruption), always backed up by moving it to a remote backend, which is the very next milestone in [Chapter 7](#ch7). Until then, local state is fine for solo work, with one caution: any teammate who runs `apply` on a different copy of the state will create a second, divergent reality.

## 2.5 Lab 1: First Contact - Provision, Change, Predict, Destroy

::: {.lab}
### Lab 1 - First project with the Docker provider: the full lifecycle {#lab1}

1. Install Terraform 1.17.x via `tenv` (or your preferred manager), add `.terraform-version` to a fresh `atlas-infra` repository, and confirm `terraform version` agrees with the file.
2. Create the layout from Section 2.2 - `versions.tf`, `main.tf`, `.gitignore` (exclude `.terraform/` and `*.tfstate*`) - paste the two resource blocks, and run `terraform init`, reading its output line by line: provider fetched, lock file written.
3. Run `terraform plan` and read the *entire* plan before applying. Predict out loud what `apply` will do, then apply, confirm with `yes`, and verify with `docker ps` and `curl localhost:8080`.
4. Make three deliberate changes, predicting each plan before running it: change the external port to `8081` (expect in-place update), change the container name (expect destroy + create - and notice the plan *says so*), add a `labels` block with `env = "lab"` (expect update).
5. Inspect `terraform.tfstate` with `terraform state list` and `terraform state show docker_container.web` - find the port and the label in the JSON to see what "state" actually means.
6. Run `terraform destroy`, confirm, and verify the container is gone with `docker ps -a`. Then re-`apply` and get it back in one command: that round-trip, from empty to working and back, is the IaC promise in miniature.
:::

**See also:** [Chapter 3](#ch3) for the language these files are written in, [Chapter 4](#ch4) for what `init` actually downloaded, and [Chapter 7](#ch7) for why `terraform.tfstate` must never live in `git`.
