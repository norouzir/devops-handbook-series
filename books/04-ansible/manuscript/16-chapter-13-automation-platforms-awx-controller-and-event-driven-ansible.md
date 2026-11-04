# Chapter 13 - Automation Platforms: AWX, Controller, and Event-Driven Ansible {#ch13}

## 13.1 What a Platform Adds Beyond the CLI

Everything so far runs from a terminal, which is precisely right for engineers and precisely wrong for an organization. An automation platform wraps the same engine with the things organizations need: role-based access control (who may run what, against which inventories), credential storage and injection (secrets the humans never see), scheduling, audit logs of every job, self-service forms for non-engineers, and workflow orchestration that chains job templates with approval gates. The engine is unchanged - your playbooks, roles, inventories, and execution environments from Parts I and II are the platform's raw material - which is the design property that makes platform adoption low-risk: a repository that is clean under `ansible-lint` and reproducible in an EE is already platform-ready.

The landscape, as of this writing, has three layers. **AWX** is the open-source upstream: a web UI, REST API, and task runner on Kubernetes (the `awx-operator` manages deployments). **Red Hat Ansible Automation Platform (AAP)** is the supported product built on that upstream - automation controller plus private automation hub plus Event-Driven Ansible plus, in the 2.6 and 2.7 releases (2025-2026), the automation orchestrator and a self-service automation portal. **CI pipelines** ([Chapter 12](#ch12)) occupy a fourth, lighter niche that overlaps the lower end of platform territory. One naming change matters operationally: the `awx.awx` collection was removed from the Ansible community package in 2024-2025 era votes and is no longer distributed with it - AWX itself continues as an active upstream (its modernization effort continues through 2026), but managing it via Ansible now means installing the collection explicitly from its own distribution channels.

## 13.2 AWX and the Controller: The Object Model

The platform's object model is small and worth learning once, because AAP's controller uses it nearly verbatim. **Projects** are the checked-out repositories (Git, with revisions and update policies). **Inventories** are the [Chapter 3](#ch3) machinery - static files or dynamic plugins - hosted with credentials. **Credentials** are typed secret bundles (machine SSH keys, vault passwords, cloud tokens) injected into jobs without user visibility. **Job templates** bind a project, a playbook, an inventory, credentials, and an execution environment into a runnable unit, optionally parameterized by *surveys* (the self-service form). **Schedules** and **notifications** make templates operational; **workflow job templates** chain templates into graphs with success/failure/always edges and approval nodes - the review gate between staging and production, visible and auditable.

The design translation from everything this book has taught is direct and deliberate. The repository keeps every behavior; the platform stores only *references and secrets*. Job templates replace shell aliases; surveys replace "edit the vars and hope"; RBAC replaces shared SSH accounts; the audit log replaces the reconstruction of who ran what from shell histories. Teams migrating from cron + CLI usually start by wrapping their existing `site.yml` unchanged in a job template - correctness first - and then exploit the platform's strengths (surveys, schedules, workflows) where the CLI habits were weakest.

## 13.3 Choosing Between CI and a Platform

The decision is about actors and audit, not about YAML. CI wins when every actor is an engineer, every change is a merge, and the pipeline is the audit trail - the [Chapter 12](#ch12) gate is the whole story, and adding a platform would add state without adding accountability. A platform wins when non-engineers must trigger automation safely (surveys), when schedules and approvals need a first-class UI, when credential custody must be centralized, or when the estate is large enough that job parallelism, retries, and fleet-wide visibility are daily needs. Most organizations end with both: CI as the quality gate on every change, the platform as the operational surface for scheduled and human-triggered runs - and the same EEs and repositories behind both, which keeps the two stories consistent.

::: {.warn}
**Watch out - two sources of truth drift apart**

The moment automation runs from both CI and a platform, the platform's project revisions, inventories, and EEs can drift from what the repository and CI believe. Keep the platform *stateless by design*: projects pinned to branches and tags (never detached copies), inventories sourced from the same dynamic plugins, EEs pulled from the same registry digests, and platform configuration itself managed as code (the controller/AWX APIs and collections - installed explicitly - or a configuration-management role) so that rebuilding the platform is a pipeline run, not an archaeology project.
:::

## 13.4 Event-Driven Ansible: Rules, Sources, and Actions

Event-Driven Ansible (EDA) inverts the direction of invocation: instead of a human or a schedule deciding when automation runs, *events* do - monitoring alerts, webhooks, ticket-queue changes, cloud streams. The unit of automation is a **rulebook** (YAML): it declares *sources* (event producers - `ansible.eda.webhook`, `ansible.eda.alertmanager`, Kafka streams, polling sources), *rules* that match conditions against event payloads, and *actions* - run a playbook (via `run_job_template` against a controller, or a plain `run_playbook`), set facts, post events, or shutdown. The **EDA controller** (part of AAP; the community runs rulebooks through `ansible-rulebook`) hosts rulebook activations - long-running processes that listen, match, and act.

```yaml
---
- name: Remediate disk pressure
  hosts: all
  sources:
    - ansible.eda.webhook:
        host: 0.0.0.0
        port: 5000
  rules:
    - name: Log rotation on disk-pressure alert
      condition: event.payload.alertname == "DiskPressure" and event.payload.severity == "warning"
      actions:
        - run_job_template:
            name: log-rotate-cleanup
            organization: Default
```

The operational discipline EDA demands is the same one real-time systems always demand: rules must be *idempotent in effect* (the same alert firing three times should converge, not multiply - the playbooks it calls are the idempotent artifacts of Part I), *bounded* (a rule that remediates by adding capacity must have a ceiling), and *auditable* (each action links to the event that caused it). The sweet spot, as of this writing, is remediation and enrichment: the well-understood, previously-runbooked responses - restart the hung service, clean the rotated logs, drain the full disk - encoded once, executed in seconds, with the pager reserved for what genuinely needs a human.

## 13.5 AAP 2.6/2.7 and the Enterprise Layer

For readers evaluating the subscription layer: AAP 2.6 (GA late 2025) introduced the **automation orchestrator** - workflow orchestration across controller and EDA with a stronger approval and audit spine - and the **self-service automation portal** that surfaces curated job templates as guarded, form-driven actions for non-engineer consumers; AAP 2.6 also moved the platform onto a unified installer and updated component versions throughout. AAP 2.7 (announced mid-2026) continues the consolidation - portal and orchestrator maturing, EDA and controller integrations tightening, and the operator experience converging on Kubernetes-native deployment. The evaluation lens this book has built applies unchanged: the subscription buys support, certified content through automation hub, the portal/orchestrator layer, and scale guarantees - and every technical mechanism underneath (projects, templates, EEs, rulebooks) is the one you already run from the community stack.

**See also:** [Chapter 3](#ch3) for the dynamic inventories platforms host, [Chapter 10](#ch10) for the EEs every layer runs, [Chapter 12](#ch12) for the CI layer that coexists with a platform, and [Chapter 14](#ch14) for the fleet-scale patterns these platforms orchestrate.
