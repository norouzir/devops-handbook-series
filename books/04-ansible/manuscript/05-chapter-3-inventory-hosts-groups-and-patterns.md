# Chapter 3 - Inventory: Hosts, Groups, and Patterns {#ch3}

## 3.1 The Inventory Is the Model of Your Estate

The inventory is the bridge between "machines that exist" and "machines this automation governs," and it deserves the same design care as any data model. At its simplest it is a list of hostnames; in practice it is a hierarchy of groups that encodes your topology - environments, roles, regions, datacenters - because every later tool in the book targets hosts through these groups. Inventory lives in INI or YAML (YAML wins once nesting appears), one or many files, static or generated; Ansible merges everything an inventory source provides into one namespace at run time. The rule that keeps large estates sane: *the inventory describes what exists; it does not contain why or how* - variables encode the why, and roles encode the how.

```yaml
# inventories/prod/hosts.yml
all:
  children:
    webservers:
      hosts:
        web1: { ansible_host: 10.0.1.11 }
        web2: { ansible_host: 10.0.1.12 }
    dbservers:
      hosts:
        db1: { ansible_host: 10.0.2.21 }
    europe:
      children:
        webservers: {}
      hosts:
        db1: {}
    production:
      children:
        europe: {}
```

Nested groups (`children`) are where the model pays off: `production` above contains `europe`, which contains `webservers`, so `-l production` and `-l webservers` are both meaningful targets and a host may legitimately belong to several overlapping groups. Two implicit groups always exist - `all` and `ungrouped` - and group names should be lowercase, hyphen-free by convention, and stable, because playbooks, variables, and documentation all come to depend on them. There is no single right taxonomy; there is only the one your team agrees to and encodes, which is why [Appendix B](#appB) ships one defensible starting shape.

## 3.2 Connection Variables and the Per-Host Dialect

Each host may need its own dialect: address, port, user, privilege-escalation method, Python interpreter, connection plugin. These are just variables, and the ones Ansible reads by convention (`ansible_host`, `ansible_port`, `ansible_user`, `ansible_connection`, `ansible_python_interpreter`, `ansible_become`) are connection variables; they can live inline in the inventory, in `host_vars/`, or in `group_vars/` - [Chapter 6](#ch6) covers the precedence mechanics, and the practical rule is that per-host facts go in `host_vars/`, per-group dialect goes in `group_vars/`, and the inventory file itself stays as close to pure topology as the estate allows. Mixed fleets are normal: Linux over SSH, Windows over WinRM (`ansible_connection: winrm`), containers over the Docker connection plugin, and API-only targets through `local` or a platform-specific connection - all in one inventory, all addressed uniformly by playbooks.

::: {.warn}
**Watch out - the interpreter discovery surprise**

On the first run against a host with an unusual Python layout, ansible-core's interpreter discovery may pick a system Python that lacks your dependencies - or warn that it picked one. Pin it deliberately in inventory (`ansible_python_interpreter: /usr/bin/python3`) for anything nonstandard, and read `ansible <host> -m setup | grep ansible_python` when module imports fail on exactly one host while the rest of the fleet behaves.
:::

## 3.3 Host and Group Variables: Directories That Scale

`group_vars/` and `host_vars/` directories (next to the inventory file, or in the playbook directory) keep variable data in files named after the group or host, which scales - an estate with forty variables per group does not belong in one YAML file. Ansible applies *all* matching files in a directory (`group_vars/webservers.yml` and `group_vars/webservers/` both work, the directory form lets a group's variables be split by concern), and every group and host may have them. The canonical pairing that keeps deployments honest: inventory directories carry topology and connection data, while environment-level service configuration lives beside it and is selected by group membership rather than by editing playbooks.

```text
inventories/
├── production/
│   ├── hosts.yml               # topology: groups + hosts + connection vars
│   ├── group_vars/
│   │   ├── all.yml             # fleet-wide defaults
│   │   ├── webservers.yml      # web tier: ports, package names
│   │   └── production.yml      # env-level: domain, tls settings
│   └── host_vars/
│       └── db1.yml             # per-host: size, replication role
└── staging/
    ├── hosts.yml
    └── group_vars/
        └── all.yml
```

The staging/production pair above shows the pattern this book uses everywhere: same groups, same playbooks, different values. The variable-merging order between overlapping groups is the "closest to the host wins" rule made precise in [Chapter 6](#ch6); what matters structurally is that nothing in a playbook ever hardcodes a value that differs between environments.

## 3.4 Patterns: Selecting Targets Without Editing Anything

A *pattern* is the `-l`/`hosts:` expression that selects hosts, and it composes: `all`, `webservers`, `web1`, `web1:web2` (union), `webservers:!staging` (except), `webservers:&europe` (intersection), wildcards (`web*`), regexes (`~web\d+`), and group intersection chains that read like set algebra because they are set algebra. Patterns make one playbook serve many purposes without edits: `ansible-playbook site.yml -l production` runs the estate, `-l webservers:&europe` runs a slice, `-l web1` is a canary. The discipline that makes patterns safe is the same one that makes inventory safe - stable, meaningful group names - which is why naming is the inventory's public API and churn there is a breaking change for every consumer.

::: {.note}
**Best practice - one canary host per tier, always**

Whatever the group structure, reserve one host per meaningful tier as the explicit canary target (`-l web1`), and make rolling rollouts ([Chapter 14](#ch14)) start there by convention. Change reviews read better when the question "where does this land first?" has a one-token answer, and incidents shrink when the blast radius of a pattern typo is one known host instead of `all`.
:::

## 3.5 Dynamic Inventory: The Estate as a Query

Static files describe an estate that changes slowly; clouds and cluster schedulers change it constantly, and hand-editing YAML to chase reality is how inventories rot. *Inventory plugins* query a source - a cloud API, a Kubernetes cluster, a database, or your CMDB - and materialize hosts and groups at run time; `ansible-inventory --list` renders the merged result so you can see exactly what a run would target. Enabling one is a matter of an `aws_ec2.yml`-style plugin config in the inventory directory (and the matching collection installed); the plugin defines how tags, regions, or labels map to groups, so the topology logic lives in one reviewed file instead of in a cron job that rewrites YAML. When no plugin fits, the classic fallback is an executable *inventory script* that prints JSON in the inventory schema - still supported, still useful behind enterprise APIs, and now mostly replaced by plugins plus `composed`/`keyed_groups` mapping.

```yaml
# inventories/aws/aws_ec2.yml - AWS EC2 dynamic inventory
plugin: amazon.aws.aws_ec2
regions:
  - eu-central-1
filters:
  tag:Managed: "ansible"
keyed_groups:
  - key: tags.Role
    prefix: role
  - key: tags.Env
    prefix: env
hostnames:
  - tag:Name
```

The keyed groups above turn EC2 tags `Role=web`, `Env=prod` into groups `role_web` and `env_prod` automatically - the estate's own metadata becomes the inventory taxonomy, which is the whole trick. Cache settings on the plugin (`cache: true` with a plugin such as `jsonfile`) keep API quota sane during heavy runs, and `--graph`/`--list` flags on `ansible-inventory` are your window into what the plugin decided.

## 3.6 Lab 2: Static, Layered, and Dynamic Inventory in One Hour

::: {.lab}
### Lab 2 - Inventory engineering from files to a dynamic source {#lab2}

1. Rebuild the Chapter 2 container fleet as a *layered* inventory: create `inventories/lab/hosts.yml` with groups `webservers` (web1, web2) and `dbservers` (db1, a third container), plus parent groups `dev` and `all`; verify with `ansible-inventory -i inventories/lab --graph`.
2. Move connection variables out of the inventory into `group_vars/all.yml` (`ansible_user`, `ansible_port` map) and one `host_vars/db1.yml` override; run `ansible all -m ping` to prove nothing broke, then `ansible-inventory --host db1` to see the merged view.
3. Exercise patterns until they are reflexes: `ansible "webservers:!web2" -m command -a "hostname"`, `ansible "all:&dbservers" -m ping`, and a wildcard run; record which pattern would be your canary target and why.
4. Go dynamic: install `community.docker` (`ansible-galaxy collection install community.docker`), write an inventory plugin config using `community.docker.docker_containers` pointed at your local Docker daemon, and run `ansible-inventory -i inventories/docker/docker.yml --list` - your two containers should appear as hosts with no static file involved.
5. Add a `keyed_groups` entry that groups containers by a Docker label (`ansible` vs `inventory-lab`), rerun the graph, and delete one container before a ping run - observing honestly which inventory model (static or dynamic) reflects reality faster, and what that implies for your cloud estate.
:::

**See also:** [Chapter 6](#ch6) for variable precedence across these directories, [Chapter 14](#ch14) for hybrid estates at fleet scale, and [Appendix B](#appB) for a complete inventory skeleton to copy.
