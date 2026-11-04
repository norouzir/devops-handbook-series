# Chapter 8 - Roles and Collections: Structuring Automation {#ch8}

## 8.1 The Role: Ansible's Unit of Reuse

A role packages a unit of automation - everything needed to configure nginx, harden SSH, or deploy the app - behind one call. Structurally it is a directory with conventional subdirectories, each optional, each loaded automatically: `tasks/` (the main task list, `main.yml`), `handlers/`, `defaults/` (the lowest-precedence variables, meant to be overridden), `vars/` (the higher-precedence, internal ones), `files/` and `templates/` (resolved by bare filename from within the role), `meta/` (role metadata and dependencies), and optionally `library/`, `lookup_plugins/`, and test scaffolding. Calling one is a line in a play - `roles: [nginx]` - or, with parameters, a `tasks:` entry under `ansible.builtin.include_role`/`import_role`; everything inside addresses the target host exactly as a flat playbook would.

```text
roles/nginx/
├── defaults/main.yml      # overridable: nginx_worker_processes, listen_port...
├── vars/main.yml          # internal: computed paths, constants
├── tasks/main.yml         # entrypoint: install, configure, service
├── handlers/main.yml      # reload/restart reactions
├── templates/site.conf.j2
├── files/index.html
└── meta/main.yml          # dependencies, min_ansible_version, galaxy_info
```

The design decision that separates good roles from piles of tasks is the **defaults/vars split**: everything an operator might legitimately want to tune lives in `defaults/` with a documented, namespaced name (`nginx_listen_port`, never `port`); everything that would break the role if changed lives in `vars/`. Namespacing the defaults is the interface contract - when two roles both ship a default named `port`, one of them silently wins and the review of that day is memorable. Prefix with the role name, document each default beside its definition, and the role becomes callable by strangers, which is the entire point of having roles.

## 8.2 Roles in Plays: Parameters, Dependencies, and Tags

Roles appear in plays as the `roles:` keyword (called once per play, before `tasks:` unless positions are tuned) or as explicit `import_role`/`include_role` tasks in the task list - the difference mirrors [Chapter 5](#ch5)'s import/include: static, parse-time composition versus dynamic, run-time composition (and only the dynamic form can loop). Parameters pass through the role call - `vars:` under the role entry or `- { role: nginx, nginx_listen_port: 8080 }` - and override `defaults/` for that invocation only, which is what makes one role serve multiple instances: nginx as the front proxy and as a second internal vhost, with different ports and templates, on the same host in one play.

Role *dependencies* (`meta/main.yml`: `dependencies:` with role names, parameters, and optional conditions) let a role declare its prerequisites - a `webapp` role depending on `nginx` and `tls` - and Ansible deduplicates repeated dependency calls per play. Dependencies are powerful and easy to overuse: a dependency graph three layers deep turns every bug hunt into a tour, so mature libraries keep dependencies shallow (one level), document them as part of the interface, and prefer plain task reuse or collection-level composition when the relationship is "uses" rather than "requires." Tags declared on a role apply to its contained tasks in the static path, which composes with the run-slicing habits from [Chapter 5](#ch5).

## 8.3 Collections: The Modern Distribution Format

Collections are the packaging format that replaced the monolithic Ansible 2.x repository: a namespace-scoped bundle of modules, plugins, roles, and docs, installed into a path your project controls and addressed by FQCN. `ansible-galaxy collection install community.postgresql` fetches from Galaxy (or an Automation Hub/private mirror); `requirements.yml` pins the set - with versions - so `ansible-galaxy collection install -r requirements.yml` reconstructs the toolchain on any machine, CI runner, or execution environment ([Chapter 10](#ch10) bakes exactly this file into images). A project's collection list is part of its public interface: reviewed like a dependency file in any language, upgraded deliberately, and never installed ad hoc onto a long-lived control node by hand.

```yaml
# requirements.yml
collections:
  - name: ansible.posix
    version: ">=1.6.0"
  - name: community.docker
    version: "==4.5.2"
  - name: amazon.aws
    version: ">=9.0.0"
  - name: git+https://github.com/org/internal-collection.git
    type: git
    version: main
```

Your own reusable content eventually deserves the same container. A collection layout (`ansible-galaxy collection init orgname.rolebundle`) holds multiple roles and custom plugins under one versioned, releasable package with a `galaxy.yml` manifest - installed from Git or a private hub by every consuming project. The design line to hold: *roles* organize a project's automation, *collections* distribute reusable automation across projects; reaching for a collection before a second project exists is premature packaging, and [Lab 5](#lab5) walks the honest path - role first, collection when the reuse is real.

## 8.4 The Anatomy of a Well-Run Role Library

House style for role libraries converges on a few habits that this book's examples follow. One role, one concern, idempotent end to end - a role you can run twice and read the summary as evidence. Every default documented in place, namespaced by role, typed, and non-empty in the default case so a bare invocation works. Templates and files referenced by bare name, roles never reaching outside their directory except through declared variables. `README.md` per role with a usage block, a defaults table, and the supported platforms - the role's front door. And `meta/main.yml` carrying `min_ansible_version` plus the platform matrix, so the toolchain contract from [Chapter 2](#ch2) is explicit rather than folklore.

::: {.note}
**Best practice - roles are contracts; write the tests before the users arrive**

A role that ships with a working example invocation, linted YAML, and a Molecule scenario ([Chapter 12](#ch12)) changes team dynamics: contributions arrive as patches to the contract instead of forks of the implementation. The test doubles as documentation of intended behavior - and the day the OS beneath the fleet upgrades a major version, the scenario is the alarm that rings before production does.
:::

## 8.5 Lab 5: From Playbook to Role to Collection

::: {.lab}
### Lab 5 - Refactor the nginx playbook into a reusable role, then a collection {#lab5}

1. Scaffold: `ansible-galaxy init roles/nginx`, and move Lab 3's tasks, handlers, and template into `tasks/`, `handlers/`, `templates/`; promote `listen_port`/`server_name` into `defaults/main.yml` as `nginx_listen_port`/`nginx_server_name`, keeping internal constants in `vars/`.
2. Rewrite `playbooks/webservers.yml` to call the role (once via `roles:`), and verify byte-for-byte behavior against Lab 3: same change contract, same handler timing, clean second run. Then call the role a *second time* in one play with different parameters (`nginx_listen_port: 8081`) and get a working second vhost - or document precisely why not.
3. Parameterize properly: add `nginx_sites` (a list of `{name, port, server_name}` dicts) iterated with a loop in the role, and express Lab 3's config as data in `group_vars` - proving the "diff between environments is data" claim from [Chapter 7](#ch7).
4. Pin the toolchain: write `requirements.yml` installing `ansible.posix` and `community.docker` with versions, run `ansible-galaxy collection install -r requirements.yml`, and convert every task in the role to FQCN - then run `ansible-lint` and fix what it flags before it does it for you.
5. Package the reuse: `ansible-galaxy collection init atlas/webstack`, move the role under `roles/nginx/`, add `galaxy.yml` metadata, build with `ansible-galaxy collection build`, install the artifact into `collections/`, and call it from a *fresh* test playbook by FQCN (`atlas.webstack.nginx`) - the same automation, now distributable.
:::

**See also:** [Chapter 9](#ch9) to keep the role's secrets out of Git, [Chapter 12](#ch12) to test the role before the fleet does, and [Appendix B](#appB) for the starter role skeleton this lab produces.
