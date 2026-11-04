# Chapter 5 - Playbooks: Plays, Tasks, and Handlers {#ch5}

## 5.1 The Anatomy of a Playbook

A playbook is a YAML file containing one or more *plays*; a play maps a target (hosts, plus execution policy) to an ordered list of *tasks*; a task is a human-readable name plus a module invocation. That three-level structure is the whole language - everything else in Part I decorates it - and the reading order of a play matters: `name`, `hosts`, then the policy keys (`become`, `vars`, `serial`, `strategy`), then `pre_tasks`, `roles`/`tasks`, `handlers`, `post_tasks`. Ansible executes tasks strictly in listed order, hosts in parallel batches; the play ends when every host has finished every task or failed beyond recovery, and then the next play begins.

```yaml
---
- name: Baseline web tier
  hosts: webservers
  become: true
  vars:
    http_port: 80
  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Deploy site config
      ansible.builtin.template:
        src: site.conf.j2
        dest: /etc/nginx/conf.d/site.conf
        mode: "0644"
      notify: Reload nginx

    - name: Ensure nginx is running and enabled
      ansible.builtin.service:
        name: nginx
        state: started
        enabled: true

  handlers:
    - name: Reload nginx
      ansible.builtin.service:
        name: nginx
        state: reloaded
```

Two lines of discipline turn the above from a snippet into a house style. Every task gets a `name`, because the run log is the document your future self reads at 2 a.m. and `Task[3/17]` is not evidence of anything. Every module gets its FQCN, per [Chapter 4](#ch4), because short names are ambiguous the day a second collection enters the dependency tree. The `---` document marker is optional for a single-document playbook but belongs in the house style anyway - linters expect it, and files that grow multiple documents later do not change shape.

## 5.2 Register, Handlers, and the Language of Change

`register` captures a task's result into a variable for later inspection - the JSON the module returned, including `changed`, `failed`, `stdout`, and whatever else the module reports - and it is the foundation of every conditional in [Chapter 7](#ch7). Handlers are the other half of the change contract: a task *notifies* a handler by name, and the handler runs once, at the end of the play, and only if at least one notifying task reported `changed` on that host. The division of labor is precise and worth memorizing: *tasks declare desired state; handlers declare reactions to actual change*. A restart hidden in a task restarts on every run whether anything changed or not; the same restart as a handler fires exactly when the config it depends on actually moved.

Handlers have a few sharp edges worth knowing before they bite. Notified handlers run after all tasks in the play (or in the current block), not immediately - when ordering matters, a `meta: flush_handlers` task forces the queue to drain at that point. Handler names must be unique within a play, and listening handlers (`listen: reload webstack`) let one notify line trigger several reactions, which scales better than five `notify:` entries. `force_handlers: true` (play or CLI) makes handlers run even when a later task fails - sometimes exactly what you want to roll back a half-applied change, sometimes the way you restart a service on a broken config; choose deliberately, not by default.

## 5.3 Tags: Deliberate Subsets of a Run

Tags label tasks, roles, plays, and imports so a run can be sliced after the fact: `--tags "nginx,config"` runs only labeled work, `--skip-tags slow` runs everything else, and `--list-tags` shows the map. Tags answer operational moments - "apply just the TLS changes," "re-run only the service restarts" - without a fork in the repository, and the conventions that keep them useful are small: tag *capabilities* (`config`, `packages`, `deploy`), not hostnames or ticket numbers; tag at the role or block level where possible so labels stay coarse; and accept that tags are a run-time filter, not an architecture - if a playbook permanently needs half of itself skipped, the playbook is two plays and should be edited, not flagged.

```yaml
tasks:
  - name: Render vhost configuration
    ansible.builtin.template:
      src: vhost.conf.j2
      dest: /etc/nginx/conf.d/vhost.conf
    tags: [config]
  - name: Sync application payload
    ansible.builtin.copy:
      src: dist/
      dest: /srv/app/
    tags: [deploy]
```

The inverse pitfall deserves its own warning: tags *filter* tasks but handlers notified by filtered tasks still queue, and `always` is a magic tag that survives `--skip-tags` - both correct behaviors, both surprising the first time. When a tagged run must also guarantee its preconditions, prefer re-running the whole play over accumulating clever tag sets; the run you can explain is the run you can trust.

## 5.4 Order, Concurrency, and the Shape of a Run

A play's policy keys tune how hosts execute, and four of them matter from day one. `serial` caps how many hosts process the play simultaneously - `serial: 2` or `serial: "25%"` batches a fleet into waves, the foundation of rolling updates in [Chapter 14](#ch14). `strategy: free` lets hosts run ahead independently instead of waiting at each task barrier (`linear` is the default and keeps hosts in lockstep, which is usually what review and debugging want). `max_fail_percentage` and `any_errors_fatal` tune when a play gives up as hosts fail, replacing the default of stopping a wave at the first failure. `run_once` executes a task on one representative host - inventory-wide fact registration and cluster-wide one-shots - met fully in [Chapter 14](#ch14) with its `delegate_to` companion.

::: {.note}
**Best practice - pre_tasks and post_tasks are load-bearing structure**

Reserve `pre_tasks` for validation that must precede everything (service checks, `wait_for`, read-only probes) and `post_tasks` for verification that must follow (health checks, smoke tests). A playbook whose success statement is "all tasks ran" is weaker than one whose final task is a positive assertion that the service actually answers - and the difference costs two keyword lines.
:::

## 5.5 Structure at Scale: imports, includes, and the Playbook of Playbooks

Real estates do not put every task in one file. `import_playbook` composes a *site* playbook out of per-service playbooks - the `site.yml` that answers "run everything" - while `import_tasks`/`include_tasks` split long task lists into files by concern (users, packages, hardening). The distinction that matters at this stage: *imports* are processed when the playbook is parsed (static - tags and conditionals apply to every imported task, file names must be literal) while *includes* are processed when reached (dynamic - per-host decisions, looped includes, runtime-computed file names). Part I keeps to static imports for structure and leaves the dynamic cases to [Chapter 7](#ch7), where conditionals and loops give them their purpose; the error to avoid early is nesting tags inside dynamic includes and expecting them to behave like the static case.

## 5.6 Lab 3: A Templated Service with Handlers, Tags, and Verification

::: {.lab}
### Lab 3 - nginx on the container fleet, end to end {#lab3}

1. Using the Chapter 2 container fleet, write `playbooks/webservers.yml` targeting `webservers` with `become: true`: install `nginx` via `ansible.builtin.package`, deploy a `site.conf.j2` template rendering `server_name` and `listen` port from group variables, and `notify: Reload nginx`.
2. Implement the `Reload nginx` handler with `ansible.builtin.service` (state `reloaded`), then prove the change contract: run the playbook twice - first run shows `changed=3`-ish and the handler firing; second shows all `ok` and no handler. Change one variable in `group_vars/webservers.yml`, rerun, and confirm exactly the template task and the handler fire.
3. Add `meta: ansible.builtin.flush_handlers` between the template task and a `Start nginx` service task, deliberately change the config again, and observe the reload happening *before* the start - then explain why the ordering matters for a first-boot case.
4. Tag the tasks (`packages`, `config`, `service`), and exercise the run-time slices: `--list-tags`, `--tags config`, `--skip-tags packages`; note which slices are safe against a running service and which silently depend on earlier tasks having run.
5. Close the loop like an operator: add a `post_tasks` block with `ansible.builtin.uri` asserting `http://{{ ansible_host }}:80` returns 200, break the template on purpose (bad port), and watch the run fail honestly - then fix it with `--check --diff` first and confirm the second run is clean.
:::

**See also:** [Chapter 6](#ch6) for the variables and templates this playbook consumes, [Chapter 7](#ch7) for conditionals and failure control, and [Chapter 8](#ch8) when this playbook deserves to become a role.
