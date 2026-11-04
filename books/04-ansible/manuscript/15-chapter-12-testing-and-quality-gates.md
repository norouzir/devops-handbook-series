# Chapter 12 - Testing and Quality Gates {#ch12}

## 12.1 The Ladder: From Syntax to Behavior

Testing automation is a ladder, and each rung buys a specific kind of confidence. *Syntax and style* (`ansible-lint`, `yamllint`) catches the mistakes that end runs before they start and the drift that makes repositories unreadable. *Smoke tests* (`--syntax-check`, `--check --diff` against representative targets) prove the playbook parses, resolves, and would apply cleanly. *Functional tests* (Molecule) create a throwaway instance, apply the role or collection, and assert the resulting state - the only rung that answers "does this automation actually work?" before production is involved. *Integration and pipeline* rungs wire the above into CI on every change, with the same execution environment that production will use. Teams fail at testing by starting at the top rung; teams succeed by never skipping the bottom ones, because the cheap rungs catch most of what breaks.

The economics deserve stating plainly: a linted, checked, Molecule-tested role costs perhaps a day more to ship and saves that day the first time an OS minor upgrade lands, a dependency changes, or a new engineer misreads a default. Every pattern in this chapter exists to move failure discovery left - from production to CI, from CI to the laptop, from the laptop to the editor - and the ladder is climbed once per project, then maintained like any other part of the platform.

## 12.2 ansible-lint: The Rulebook as a Team Member

`ansible-lint` reads playbooks, roles, and collections, and enforces several hundred rules spanning YAML hygiene, FQCN discipline, name presence, idempotency hints, and risky patterns (`command` without guards, `shell` with variables, changed-when omissions). Its *profiles* grade strictness from `min` through `production`, so a team can adopt progressively: `--profile=production` in the gate, `--profile=shared` while a legacy repository is being healed. Rule tags organize the space (`command-instead-of-shell`, `fqcn`, `schema`, `var-naming`), `ansible-lint --list` documents what is enforced, and per-line `# noqa` pragmas exist for the rare legitimate exception - with the same review weight as a `nolint` in any language.

```console
$ ansible-lint                          # whole project, configured profile
$ ansible-lint --profile=production roles/nginx/
$ ansible-lint --fix roles/nginx/       # autofix the safe subset
```

The policy decisions that make lint a gate rather than wallpaper: it runs in CI on every pull request and *fails* the run; new exceptions require a noqa comment with a reason, not a disabled rule in config; and upgrades of the lint tool are tested like everything else, because new rules will flag old habits and the team should decide once, in review, rather than discover them during an incident. `yamllint` usually rides alongside for pure YAML style; `ansible-lint` already integrates it, and one configured source of truth beats two disagreeing ones.

## 12.3 Molecule: Functional Tests for Roles and Collections

Molecule is the functional test harness for reusable automation: a *scenario* defines the lifecycle - create (instances via a driver: Docker/Podman, or a cloud), prepare, converge (apply the role), verify (assertions), destroy - and `molecule test` runs it end to end. Scenarios live beside the role (`roles/nginx/molecule/default/`), the default verifier is Ansible itself (assertion tasks, which keeps the tool surface small), and multi-scenario layouts support different platforms or application versions side by side.

```yaml
# roles/nginx/molecule/default/molecule.yml (excerpt)
driver:
  name: docker
platforms:
  - name: nginx-instance
    image: geerlingguy/docker-ubuntu2404-ansible:latest
    pre_build_image: true
provisioner:
  name: ansible
verifier:
  name: ansible
```

```yaml
# roles/nginx/molecule/default/verify.yml
---
- name: Verify
  hosts: all
  tasks:
    - name: Service is active
      ansible.builtin.command: systemctl is-active nginx
      changed_when: false
      register: svc
      failed_when: svc.stdout != "active"

    - name: Default page answers on the configured port
      ansible.builtin.uri:
        url: "http://localhost:{{ nginx_listen_port }}"
      register: page
      failed_when: page.status != 200
```

The design habits that make Molecule tests worth their runtime: test the *contract*, not the implementation - the verify stage asserts what a consumer of the role relies on (service active, page answers, config file mode) rather than which package version got installed; use prepared images (`pre_build_image: true`) so scenario time is spent on the role, not on building instances; and keep scenarios fast enough to run on every pull request - a Molecule suite over ten minutes stops being run, and an unrun test is decoration. For collections, the same scenarios sit under `extensions/molecule/` or per-role directories and run through `tox-ansible` across the matrix of Ansible versions the collection claims to support.

## 12.4 CI: The Gate That Never Sleeps

The pipeline composes the ladder, cheapest first: lint (`ansible-lint`), smoke (`--syntax-check`), then `--check --diff` against ephemeral targets (the container fleet of [Lab 1](#lab1) is precisely this), then Molecule for the changed roles, then - where the estate allows - a real apply against a staging inventory. The pipeline must run inside the estate's execution environment ([Chapter 10](#ch10)), because "it works on the CI runner's pip install" is the same works-on-my-machine failure this book retired two chapters ago; secrets arrive through the CI's secret store into vault ids ([Chapter 9](#ch9)), and the [Appendix B](#appB) artifact shows the complete workflow file for GitHub Actions.

```yaml
# .github/workflows/ansible.yml (excerpt - full artifact in Appendix B)
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Lint
        run: ansible-lint --profile=production
      - name: Syntax and check-mode smoke test
        run: |
          ansible-playbook playbooks/site.yml -i inventories/dev --syntax-check
          ansible-playbook playbooks/site.yml -i inventories/dev --check --diff
```

Two boundary questions finish the design. *What about drift detection?* A scheduled CI (or controller) job running `--check --diff` against staging is a drift alarm - it answers "does reality still match the repository?" without changing anything, and the incidents it prevents are the silent kind. *What about testing the EEs themselves?* The image build pipeline runs `ansible-galaxy collection list`, a syntax-check, and a minimal playbook inside the built image before tagging it - the environment is an artifact, and artifacts get tests.

::: {.note}
**Best practice - the gate is the deal, not the suggestion**

A quality gate only works when it is boringly non-negotiable: CI failure means no merge, emergency merges are patched back through CI within the day, and the gate's own flakiness is treated as a sev-2 on the pipeline. The first time the team skips the gate "just this once" is the day it stops being a gate - and the runbooks of [Chapter 14](#ch14) quietly assume it always held.
:::

**See also:** [Chapter 8](#ch8) for the roles these tests protect, [Chapter 10](#ch10) for the images the pipeline runs inside, and [Chapter 9](#ch9) for how secrets reach CI without entering it.
