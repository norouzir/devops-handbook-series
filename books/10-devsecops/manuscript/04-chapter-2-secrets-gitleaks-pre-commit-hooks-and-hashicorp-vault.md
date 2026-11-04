# Chapter 2 - Secrets: Gitleaks, Pre-Commit Hooks, and HashiCorp Vault {#ch2}

## 2.1 The Anatomy of a Leaked Secret

Secrets are the highest-value, lowest-effort target in the entire threat model. A database password or a cloud API key is a complete bypass of every control in [Table 1.1](#ch1): no exploit needed, no malware, just read the file and log in. The public record is a museum of exactly this failure - Toyota's 2019 hardcoded access key exposed the data of roughly 3.1 million customers after years sitting in a public repository, and post-incident scans of GitHub routinely find tens of thousands of live cloud credentials in supposedly private commits. Two properties make the problem structural rather than sloppy. First, **git history is forever**: deleting a credential in a later commit does not remove it from the objects anyone can fetch, and every fork, clone, and mirror keeps the old commits alive. Second, **secrets proliferate**: a credential pasted into a Slack thread, a ticket, a log line, or a Docker layer is a second incident waiting for its own discovery date.

The engineering response has two halves that this chapter builds in order. **Stop new leaks at the source** - a scanner on every commit so a secret never lands in history in the first place - and **stop storing secrets in files at all**, moving them to a platform whose entire job is issuing, auditing, rotating, and revoking credentials: HashiCorp Vault. The first half is cheap and universal; the second is the professional platform that [Chapter 3](#ch3) and [Chapter 7](#ch7) build on.

::: {.warn}
**Watch out - rotating after a leak is not optional**

The moment a credential may have been observed - pushed to any remote, pasted anywhere, printed in a log - it is burned, forever, regardless of whether the repo is private or how fast you deleted the commit. Rotating is the only remediation, and history rewriting (`git filter-repo` or BFG) only cleans future clones. If a production cloud key ever touched a public repo in any commit, assume it is on an automated scanner's list within minutes, because those scanners exist and they are fast.
:::

## 2.2 Stopping Leaks at the Source: Gitleaks and Pre-Commit

**Gitleaks** is the de facto open-source secrets scanner: a single static binary that pattern-matches staged changes, full histories, and directory trees against a curated ruleset of credential formats (AWS keys, Stripe tokens, private key blocks, and dozens more). Install it for your platform, then wire it into the developer loop with **pre-commit**, the hook framework the series has used before:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.3          # pin the current gitleaks v8 release
    hooks:
      - id: gitleaks
```

```bash
pre-commit install                    # activate hooks in this clone
pre-commit run gitleaks --all-files   # baseline the existing tree once
gitleaks detect --source . -v         # scan the full git history
```

From this point, a staged AWS key dies in the hook with the offending line and rule named, before it can reach a remote. Running `gitleaks detect` across the history is the one-time *archaeology* step every existing repository needs: it reads every commit's full diff and reports anything that ever landed. For CI enforcement, the `gitleaks/gitleaks-action` step or a plain job step runs the same binary against each pull request, which turns the hook from a courtesy into a policy - hooks can be skipped with `--no-verify`, CI cannot.

::: {.note}
**Best practice - baseline, then fail the build**

A brand-new policy over an old repository produces hundreds of findings, and a rule that blocks everything blocks nothing (it gets disabled by morning). The working pattern: fix or accept the historical findings once, then make CI fail on any *new* finding. Gitleaks supports exactly this with an allowlist in `.gitleaks.toml` for accepted false positives - and every allowlist entry gets a comment saying who accepted it and why, so the file stays an audit artifact rather than a dumping ground.
:::

## 2.3 Vault: The Platform for Secrets

With leaks stopped at the source, the remaining problem is *where secrets live when the application needs them*. Checking them into a config file was the leak; a staging area of plaintext `.env` files is the same leak with extra steps. **Vault** is a single server whose data model makes the right behavior the easy behavior: secrets are written to and read from a namespaced path, every read is authenticated against a policy, every access is written to an append-only audit log, and credentials can be issued with a time-to-live so they expire without a human remembering to rotate.

For learning, Vault runs in **dev mode** - an in-memory, auto-unsealed server on localhost that exists to make the CLI fluent, and only that:

```bash
vault server -dev                        # prints a root token and VAULT_ADDR
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='<root token from the banner>'
vault status

vault secrets enable -path=shopnow kv-v2          # versioned key-value engine
vault kv put shopnow/dev/db username=shopnow_app password='S3cure-Dev-Pass'
vault kv get -field=password shopnow/dev/db
vault kv get -version=1 shopnow/dev/db            # every write is versioned
vault kv rollback -version=1 shopnow/dev/db       # and every deletion is recoverable
```

The **KV v2** engine is the workhorse: reads, writes, versioning, soft delete, and a metadata API, all under one path prefix. Dev mode is for exactly this chapter's lab - the moment a real secret exists, Vault moves to a real deployment with TLS and auto-unseal backed by cloud KMS, the operational details of which are a deployment concern rather than a DevSecOps concept.

## 2.4 Policies, Tokens, and AppRole

Everything in Vault is authorized by a **policy** - a set of HCL rules granting capabilities (`read`, `create`, `update`, `delete`, `list`, `sudo`) on path globs:

```hcl
# shopnow-app.hcl
path "shopnow/data/dev/*" {
  capabilities = ["read"]
}
path "shopnow/metadata/*" {
  capabilities = ["list"]
}
```

```bash
vault policy write shopnow-app shopnow-app.hcl
vault token create -policy=shopnow-app -ttl=1h   # a short-lived bearer token
```

Human and CI access then rides on one of two authentication mechanisms. **AppRole** is the machine-to-machine answer: a role pairs a `role-id` (not secret, like a username) with a `secret-id` (one-time or limited-use, like a password), and logging in with both yields a token constrained by the role's policies and TTL. It is the baseline answer for servers that cannot use a stronger identity. The stronger identity, when one exists, is the workload itself: **OIDC auth** lets a GitHub Actions workflow prove its identity to Vault using the same federation the cloud books used for AWS, Azure, and GCP - no stored credential anywhere:

```bash
vault auth enable jwt
vault write auth/jwt/config \
  oidc_discovery_url=https://token.actions.githubusercontent.com \
  bound_issuer=https://token.actions.githubusercontent.com
vault write auth/jwt/role/shopnow-ci \
  role_type=jwt \
  bound_subject='repo:acme/shopnow:environment:production' \
  user_claim=github token_policies=shopnow-app token_ttl=30m
```

In the workflow, `hashicorp/vault-action` v3 authenticates with the job's OIDC token and injects only the secrets that role's policy allows - one repository, one policy, one set of paths, no static credentials in GitHub settings at all.

## 2.5 Dynamic Secrets: Credentials That Expire Themselves

The most Vault-native idea is the **dynamic secret**: instead of storing a shared password, Vault creates a fresh, time-limited credential on demand and destroys it on lease expiry. For the PostgreSQL database the series has used since the Kubernetes book:

```bash
vault secrets enable database
vault write database/config/shopnow-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles="shopnow-readonly" \
  connection_url="postgresql://{{username}}:{{password}}@db:5432/shopnow?sslmode=disable" \
  username=vaultadmin password='Admin-Pass'
vault write database/roles/shopnow-readonly \
  db_name=shopnow-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl=1h max_ttl=24h

vault read database/creds/shopnow-readonly     # a fresh DB user, alive for 1h
```

Every call returns a different, randomly named database user that Vault created and will drop when the lease ends. A leaked pod env-dump now contains a credential that is already dead, the database never holds a long-lived shared app password to rotate, and Vault's audit log answers "who read the database, when, from which role" - three of [Chapter 1](#ch1)'s four adversary wants neutralized by one mechanism.

::: {.lab}
### Lab 1 - Run Vault, Write a Policy, and Prove Least Privilege {#lab1}

1. Start `vault server -dev`, export `VAULT_ADDR` and the printed root token, and `vault secrets enable -path=shopnow kv-v2`.
2. Write two secrets: `shopnow/dev/db` and `shopnow/prod/db` (distinct passwords). Confirm `vault kv get` reads both.
3. Create `shopnow-app.hcl` granting `read` on `shopnow/data/dev/*` and `list` on `shopnow/metadata/*`; `vault policy write` it.
4. Issue a token with that policy (`vault token create -policy=shopnow-app -ttl=30m`), export it as `VAULT_TOKEN` in a second shell, and verify: reading `shopnow/dev/db` succeeds, reading `shopnow/prod/db` fails with `permission denied`, and `vault kv put` fails anywhere - the token can read, nothing more.
5. Enable AppRole for `shopnow-app`, fetch a `role-id` and a single-use `secret-id`, and `vault write auth/approle/login` with both to obtain a fresh token without the root token in sight.
6. Break it on purpose: edit the policy to add `update` on `shopnow/data/prod/*`, re-issue the token, and watch a dev-identity token gain production write - then revert. You have just witnessed why policies are reviewed like code.
:::

**See also:** [Chapter 3](#ch3) hardens the CI environment these secrets are injected into; the federation pattern returns in the cloud books' CI/CD chapters and is assembled end to end in [Chapter 7](#ch7); [Appendix B](#appB) compresses every Vault command from this chapter into one table.
