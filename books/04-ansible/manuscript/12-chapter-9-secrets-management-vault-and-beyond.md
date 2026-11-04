# Chapter 9 - Secrets Management: Vault and Beyond {#ch9}

## 9.1 The Secret Problem in a Git-Driven Tool

Ansible automates with credentials - database passwords, API tokens, private keys - and every value it uses is, by default, a plain string in a file you are about to `git push`. The challenge has two halves: keep secrets out of plaintext in the repository, and keep them out of logs, run summaries, and screenshots at execution time. Ansible's built-in answer to the first half is Vault, an AES-256 (AES256 in current versions) symmetric encryption scheme integrated into the variable system; the second half is handled by the engine's `no_log` machinery plus the habits in this chapter. The rule that decides everything else: *a repository that contains any plaintext credential is already compromised* - Git history is forever, forks are cheap, and `git filter-branch` is not a remediation plan.

Vault encrypts *data*, not files as such: a vault-encrypted YAML file is just a variable file whose entire content is ciphertext, while `ansible-vault encrypt_string` encrypts a single value inline inside an otherwise readable file. The inline form is the better default for teams - it keeps structure reviewable (you can see that `db_password` exists, which hosts it applies to, and review everything around it) while the value itself is opaque; whole-file encryption suits genuinely secret-shaped data such as private keys. Vault-encrypted values decrypt transparently at run time when the run is given the vault password - from `--ask-vault-pass`, from `--vault-password-file`, or from the `vault_password_file` setting - and fail with an unmistakable decryption error when they are not.

## 9.2 The Vault CLI and the Single-Password Lifecycle

The `ansible-vault` subcommand covers the full lifecycle: `create` (opens an editor, saves encrypted), `encrypt`/`decrypt` (convert whole files in place), `encrypt_string` (emit an inline-encrypted value), `view`/`edit` (read or modify without leaving ciphertext on disk in the plaintext sense), and `rekey` (re-encrypt everything under a new password). `encrypt_string`'s output carries a label that preserves the variable name through review:

```console
$ ansible-vault encrypt_string 'S3cr3t-Passw0rd!' --name 'db_password'
Encryption successful
db_password: !vault |
  $ANSIBLE_VAULT;1.2;AES256;atlas-prod
  37323663353334626439323664316437633334343334386465363565646563366338326261656665
  ...
```

The single-password model - one vault password for the whole project, stored in a password manager, handed to CI through a secret variable - is where every team should start, because its operational surface is one secret with one rotation procedure. Its costs are equally real: everyone who can run the playbooks can decrypt everything, and the password itself becomes the crown jewel. Mitigate with scope (separate vault passwords per environment, next section), with rotation (`rekey` after any suspected exposure - and treat `rekey` as routine after personnel changes, not as an incident response), and with the discipline that vault passwords never appear in playbooks, `group_vars`, or shell histories.

## 9.3 Multiple Vault Identities: Per-Environment Secrets

`--vault-id` generalizes the single password into *identities*: each encrypted blob records the label of the identity that produced it, and a run may present several identities - the label is matched against the content, order expresses priority. The pattern that fits environments: `group_vars/production/vault.yml` encrypted with identity `prod`, `group_vars/staging/vault.yml` with `staging`, and developers' nightly runs present only the identity they legitimately hold. Secrets stop being all-or-nothing; a CI runner that deploys staging cannot decrypt production values even though it runs the same playbooks against the same repository.

```console
$ ansible-vault encrypt_string 'prod-db-pass' --vault-id prod@prompt --name db_password
$ ansible-playbook site.yml --vault-id staging@~/.vault-staging --vault-id prod@~/.vault-prod
```

The `label@source` grammar puts the password source after the label - `prompt`, a file path, or an executable script - and the *script* form is the production answer: a small program that fetches the current password from the team's password manager (or a cloud KMS) at run time, so no vault password is ever stored on disk next to the repository it protects. Rotation becomes rotating the password in the manager and `rekey`-ing the repository in one maintenance window; the runner images and CI variables stay untouched.

## 9.4 no_log, Trust, and the Log-Leakage Half of the Problem

Encryption protects the repository; `no_log: true` protects the run. A task marked `no_log` suppresses its arguments and results from the console, from callback logs, and from controller job output - the standard marking for any task whose arguments include credentials (`user` with a password, `uri` with a token, `command` calling a CLI that takes secrets in argv). The blunt-instrument caveat is real: `no_log` hides *everything* about the task, including the error you need while debugging, so pair it with explicit failure messages (`failed_when` + a message that names the evidence without the secret) rather than sprinkling it everywhere. Since the data-tagging rewrite in ansible-core 2.19 ([Chapter 6](#ch6)), the engine also tracks *trust* - values originating from untrusted sources are tagged as such, and templating refuses some silent-mutation paths that used to launder untrusted input into module arguments - which closes a class of injection bugs that pre-2.19 playbooks had to survive on conventions alone.

::: {.warn}
**Watch out - logs are the second repository**

The repository is not the only place plaintext secrets leak: run logs, error messages that echo `stdout`, `--diff` output of file tasks containing credentials, controller job exports, and screenshots in incidents all leak. Adopt three habits: `no_log` on credential-carrying tasks; templates that do not render secrets into files readable by other users (`mode: "0600"`, and mind the diff); and a standing rule that debugging a failing credential task starts with `--start-at-task` plus a *redacted* copy of the value - never with turning `no_log` off on production.
:::

## 9.5 Beyond Vault: External Secret Stores

When an organization already runs a secrets platform - HashiCorp Vault, a cloud KMS-backed manager, CyberArk, Kubernetes secrets on the platform side - Ansible should *consume* it rather than shadow it. Lookup plugins bridge the worlds at run time: `community.hashi_vault.hashi_vault` fetches a path from HashiCorp Vault with token/AppRole auth; cloud collections ship their own (`amazon.aws` secretsmanager, SSM parameter store lookups); `kubernetes.core.k8s` reads cluster secrets; and a generic `lookup('ansible.builtin.env', ...)` covers CI-injected values. The lookup runs on the control node (or inside the execution environment - [Chapter 10](#ch10)), the target sees only the resolved value, and the repository carries a *reference* (`vault_kv2_path: atlas/prod/db`) instead of an encrypted blob - audit moves to the secrets platform, where it belongs.

```yaml
- name: Fetch the database password from HashiCorp Vault
  ansible.builtin.set_fact:
    db_password: "{{ lookup('community.hashi_vault.hashi_vault',
                            'secret=atlas/prod/db:password',
                            auth_method='approle',
                            role_id=lookup('ansible.builtin.env', 'VAULT_ROLE_ID'),
                            secret_id=lookup('ansible.builtin.env', 'VAULT_SECRET_ID')) }}"
  no_log: true
```

The choice between Vault-the-Ansible-feature and vault-the-platform is architectural, not ideological. Ansible Vault fits teams whose source of truth is the repository and whose threat model is "no plaintext in Git"; external stores fit organizations that need central lease/audit/rotation semantics across many tools. The anti-pattern both avoid: a plaintext `secrets.yml` in Slack "just for the on-call engineer" - which is the failure mode the whole chapter exists to prevent.

## 9.6 Lab 6: Vault-Protected Automation Through a Quality Gate

::: {.lab}
### Lab 6 - Encrypt, rotate, and run through CI without a single plaintext value {#lab6}

1. Take the Lab 5 role and introduce a secret: `nginx_htpasswd_user`/`nginx_htpasswd_password` rendered into a basic-auth file by the role. Encrypt the password with `ansible-vault encrypt_string --name nginx_htpasswd_password` into `group_vars/webservers/vault.yml`, and mark the rendering task `no_log: true`.
2. Run the playbook three ways to internalize the contract: without a vault password (observe the decryption error), with `--ask-vault-pass`, and with `--vault-password-file ~/.vault-lab` - then add `vault_password_file` to your *local, unversioned* config and confirm `./build.sh`-style naked runs keep working.
3. Split identities: create `prod` and `staging` vault identities, encrypt the two environments' password values separately, and prove a run that presents only `staging` cannot decrypt the `prod` group's variables - reading the error message carefully, because you will see it in CI logs one day.
4. Rotate for real: `ansible-vault rekey` the encrypted files under a new password, update the password file, rerun, and confirm convergence - the whole rotation should take under five minutes, which is the point.
5. Close the loop in CI: add a GitHub Actions workflow ([Appendix B](#appB) has the artifact) that installs the toolchain, runs `ansible-lint`, runs the playbook with `--check --diff` against the container fleet with the vault password injected as a CI secret via an executable `--vault-id prod@script`, and fails the pull request on any lint or check-mode error - the secret value itself never appears in the log.
:::

**See also:** [Chapter 6](#ch6) for how encrypted values merge with ordinary variables, [Chapter 10](#ch10) for baking secret-fetching plugins into execution environments, [Chapter 12](#ch12) for the linting half of the quality gate, and [Appendix B](#appB) for the CI artifact.
