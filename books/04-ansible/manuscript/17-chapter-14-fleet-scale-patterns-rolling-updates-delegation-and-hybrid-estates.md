# Chapter 14 - Fleet-Scale Patterns: Rolling Updates, Delegation, and Hybrid Estates {#ch14}

## 14.1 Rolling Updates: serial as the Unit of Safety

A fleet-wide change is a controlled sequence of small, verifiable changes, and `serial` is the control: `serial: 2` (or `"10%"`) slices the play into waves, each wave applying the full task list and - this is the design point - each wave's *failure* stopping the rollout with the blast radius capped at the wave. The pattern composes with everything from [Chapter 7](#ch7): pre_tasks verify readiness, the tasks apply, post_tasks assert health (`uri` against the instance, a smoke endpoint, a queue depth), and a failing wave leaves earlier waves converged and later waves untouched. The runbook question that matters is what happens *next*: either a human reads the failure and decides, or a `rescue` block automated the rollback (re-render the previous template revision, re-run) - both are correct, improvisation is not.

```yaml
- name: Rolling app deploy
  hosts: webservers
  serial: 2
  max_fail_percentage: 0
  tasks:
    - name: Drain from load balancer
      ansible.builtin.uri:
        url: "http://lb1.internal:8080/api/members/{{ inventory_hostname }}/drain"
        method: POST
      delegate_to: localhost
      run_once: false

    - name: Deploy new release
      ansible.builtin.include_role:
        name: atlas.webstack.app

    - name: Verify the app answers locally
      ansible.builtin.uri:
        url: "http://127.0.0.1:{{ app_port }}/healthz"
      register: health
      failed_when: health.status != 200

    - name: Rejoin load balancer
      ansible.builtin.uri:
        url: "http://lb1.internal:8080/api/members/{{ inventory_hostname }}/enable"
        method: POST
      delegate_to: localhost
```

The example above is the canonical shape - drain, deploy, verify locally, rejoin - and its details are where fleets differ: the load-balancer API (a platform call through `uri`, or a template re-render on the LB host via `delegate_to`), the health assertion (local first, then cluster-level), and the wave size (one host for stateful services, a percentage for stateless fleets). `max_fail_percentage: 0` makes the intent explicit: any failure anywhere stops the rollout - the correct posture when the cost of proceeding is unknown.

## 14.2 delegate_to and run_once: Precision Placement of Work

`delegate_to` executes a task *on a different host than the loop of the play* while keeping the variable context of the original host - the load-balancer calls above run on the control node (`delegate_to: localhost`) but speak about `inventory_hostname`; a database command runs on `db1` while the play walks `webservers`. `run_once` executes a task on exactly one host of the group (the first available) and registers its result for all - leader-style one-shots: service discovery registration, a migration applied once, a cluster-wide notification. Together they express the coordination layer of fleet automation: the *configuring* tasks stay idempotent and per-host, while the *orchestrating* tasks (scale the LB, apply one migration, announce the change) are placed precisely once.

The two sharp edges are visible in every fleet's history. First, delegation changes where facts and connections come from - `ansible_facts` inside a delegated task are the *target's* context only if you say `delegate_facts: true`, and the default (original host's context) is usually what you want but exactly what surprises everyone once. Second, `run_once` tasks still *notify handlers per host* unless guarded, and a `run_once` task with `delegate_to` is the combination that makes one host's failure strand the others' assumptions - wrap such tasks in the assertions of [Chapter 7](#ch7) so the failure is loud at the moment it matters.

## 14.3 Hybrid Estates: Linux, Windows, Network, and Cloud in One Model

Real fleets are heterogeneous, and the inventory model absorbs them without changing the engine. **Windows** hosts connect over WinRM (`ansible_connection: winrm`, credentials from vault, `ansible.windows` collection) and use their native module family (`ansible.windows.win_package`, `win_service`, `win_updates`); the play grammar is identical, which means the rolling-update pattern above applies to a Windows fleet with different module names. **Network devices** speak SSH/CLI or API through vendor collections (`cisco.ios`, `junipernetworks.junos`, `arista.eos`) with `connection: ansible.netcommon.network_cli`, resource modules that render running-config as data, and the same blocks/rescue rollback patterns. **Cloud resources** are just API targets - dynamic inventories from [Chapter 3](#ch3) plus the cloud collections - and **containers/Kubernetes** complete the picture (`community.docker`, `kubernetes.core`), letting one playbook configure the host, its container runtime, and the workloads upon it.

The design discipline that makes hybrid manageable is dialect isolation: per-platform differences live in group variables and role-internal conditionals (`when: ansible_facts['os_family'] == ...`), never in the *play's* control flow - a play reads the same for Linux and Windows hosts, and the roles resolve the dialect, which keeps the fleet's site.yml a single readable story. Shared services (monitoring, backup, TLS) get platform-neutral interfaces (a common variable contract, per-platform role implementations), and new platforms join the estate by adding groups and implementations - not by forking the playbooks.

::: {.note}
**Best practice - one site.yml to describe the estate**

Fleet-scale repos converge on a `site.yml` that composes the whole estate - plays per tier, roles per service, serial and failure policy per tier - so that `ansible-playbook site.yml --check --diff` is the estate's *full* rehearsal and its drift check. Subsets come from `-l` patterns and tags ([Chapter 3](#ch3), [Chapter 5](#ch5)); the moment "run everything we manage" has no single command, drift has somewhere to hide.
:::

## 14.4 Import, include, and the Runtime Shape of Large Repositories

At fleet scale the structural choices of [Chapter 5](#ch5) stop being style and become behavior. *Imports* (`import_playbook`, `import_tasks`, `import_role`) compose at parse time: the composed graph is visible to `--list-tasks`/`--list-tags`, tags and `when` stamp through every contained task, and the cost is rigidity - file names and conditions must be literal. *Includes* (`include_tasks`, `include_role`, `include_vars`) compose at run time, per host, with loops and computed names - the flexibility the rolling pattern above uses (`include_role` inside the wave) and the dialect-switching of [Chapter 6](#ch6) (`include_vars` by OS family). The rule that keeps large repositories sane: *imports for architecture* (the site.yml spine, stable subsystems), *includes for runtime decisions* (per-host dialects, conditional subsystems, looped instantiations) - and a hard ban on mixing the two for the same decision, which is the single most reliable source of "why did this tag not work" tickets.

## 14.5 Operating the Fleet: Drift, Decommissioning, and the Long Game

The fleet-scale endgame is operational, and three practices close this book's arc. **Drift management**: the scheduled `--check --diff` run of [Chapter 12](#ch12) becomes a fleet institution - a periodic rehearsal whose diff is reviewed like a change, whose "empty diff" is the fleet's certificate of health, and whose findings feed the repository rather than being fixed by hand on the target. **Decommissioning** is automation's farewell: the `state: absent` invocations of every module this book has used - users removed, keys revoked, DNS and LB members withdrawn, the host dropped from inventory - run as a reviewed playbook, because a machine deleted by hand is a machine whose memory lives on in monitoring, backups, and someone's muscle memory. **The long game** is the upgrade cadence: community package and core upgrades rehearsed in an EE ([Chapter 10](#ch10)), gated by the tests of [Chapter 12](#ch12), applied to the fleet with the rolling patterns of this chapter - the toolchain maintained with the same seriousness as the estate it maintains.

**See also:** [Chapter 7](#ch7) for the failure machinery the waves ride on, [Chapter 13](#ch13) for orchestrating these patterns through a platform, and [Appendix B](#appB) for the site.yml skeleton that composes the whole estate.
