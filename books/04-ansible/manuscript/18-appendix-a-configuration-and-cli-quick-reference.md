# Appendix A - Configuration and CLI Quick Reference {#appA}

## A.1 ansible.cfg: The Keys That Matter

```ini
[defaults]
inventory              = inventories/production     # default inventory path
host_key_checking      = False                      # lab convenience only!
forks                  = 20                         # parallel hosts
gathering              = smart                      # use fact cache when fresh
fact_caching           = ansible.builtin.jsonfile
fact_caching_connection = .ansible_cache
fact_caching_timeout   = 86400
callbacks_enabled      = ansible.posix.profile_tasks
collections_path       = ./collections
interpreter_python     = auto_silent                # silence discovery chatter
retry_files_enabled    = False

[privilege_escalation]
become                 = False
become_method          = sudo
become_user            = root

[ssh_connection]
pipelining             = True                       # the big latency win
ssh_args               = -o ControlMaster=auto -o ControlPersist=120s
```

Settings resolve in order: `ANSIBLE_CONFIG` (env var, a file path) → `ansible.cfg` in the current directory → `~/.ansible.cfg` → `/etc/ansible/ansible.cfg`. `ansible --version` names the file actually in force; when behavior differs between two people's laptops, the answer is in that line and a diff of the two configs.

## A.2 Variable Precedence, Condensed

From weakest to strongest - the full numbered list is in the official documentation; this is the working spine:

| Rank | Source | Typical use |
|------|--------|-------------|
| 1 (weakest) | Role `defaults/main.yml` | Overridable interface |
| 2 | Inventory `group_vars/all` | Fleet-wide defaults |
| 3 | Inventory `group_vars/<group>` | Group tuning (later-listed groups win) |
| 4 | Inventory `host_vars/<host>` | Per-host overrides |
| 5 | Play `vars_files`, play/block `vars` | Deployment configuration |
| 6 | Role `vars/main.yml`, role params | Role-internal and call-site values |
| 7 | `set_fact`, `register` | Run-computed values |
| 8 | Task `vars`, `include_vars` | Task-local and dynamic loads |
| 9 | `extra vars` (`-e`) | Operator overrides - always wins |

## A.3 The CLI Surface

| Command | Purpose | Canonical invocation |
|---------|---------|----------------------|
| `ansible` | Ad-hoc module run | `ansible webservers -m ansible.builtin.service -a "name=nginx state=restarted" -b` |
| `ansible-playbook` | Run playbooks | `ansible-playbook site.yml -i inventories/prod --check --diff` |
| `ansible-inventory` | Inspect merged inventory | `ansible-inventory -i inventories/prod --graph` |
| `ansible-doc` | Module/plugin docs | `ansible-doc community.postgresql.postgresql_db` |
| `ansible-galaxy` | Roles/collections | `ansible-galaxy collection install -r requirements.yml` |
| `ansible-vault` | Encrypt/view/rekey secrets | `ansible-vault encrypt_string '...' --name db_password` |
| `ansible-lint` | Style + best-practice gate | `ansible-lint --profile=production` |
| `ansible-navigator` | Run inside an EE | `ansible-navigator run site.yml --mode stdout` |
| `ansible-builder` | Build execution environments | `ansible-builder build -t atlas-ee:1.4.0` |

## A.4 Pattern Grammar

| Pattern | Meaning |
|---------|---------|
| `all` / `ungrouped` | Implicit groups |
| `web1` | Single host |
| `webservers` | Whole group |
| `web1:web2` | Union |
| `webservers:!staging` | Group minus group |
| `webservers:&production` | Intersection |
| `web*` / `~web\d+` | Wildcard / regex |

## A.5 Task Keywords Worth Memorizing

| Keyword | Effect |
|---------|--------|
| `register` | Capture the task result for later use |
| `when` | Per-host conditional (skip, not fail) |
| `loop` + `item` | Iterate a declared list |
| `notify` | Queue a handler (runs once, at play end) |
| `changed_when` / `failed_when` | Redefine the change/failure contract |
| `ignore_errors` | Continue the play on failure (host stays failed) |
| `no_log` | Suppress task output (credential tasks) |
| `check_mode: false` | Force a task to run even under `--check` |
| `delegate_to` / `run_once` | Place work precisely ([Chapter 14](#ch14)) |
| `tags` | Label for `--tags`/`--skip-tags` slicing |
