# Appendix B - Starter Automation {#appB}

Four artifacts that recur in nearly every estate, complete enough to adopt and adapt. They assume the project layout of [Chapter 2](#ch2) and the conventions of Part I.

## B.1 A Two-Tier Site Playbook

```yaml
---
# playbooks/site.yml - the estate in one file ([Chapter 14](#ch14))
- name: Baseline all hosts
  hosts: all
  become: true
  roles:
    - role: atlas.baseline.common
      tags: [baseline]

- name: Configure database tier
  hosts: dbservers
  become: true
  roles:
    - role: atlas.postgres.server
      tags: [db]

- name: Configure web tier with rolling waves
  hosts: webservers
  become: true
  serial: 2
  max_fail_percentage: 0
  roles:
    - role: atlas.webstack.nginx
      tags: [web]
    - role: atlas.webstack.app
      tags: [app]
  post_tasks:
    - name: Health check after each wave
      ansible.builtin.uri:
        url: "http://127.0.0.1:{{ app_port }}/healthz"
      failed_when: false   # surface as warning; assert at fleet level
  handlers:
    - name: Reload app fleet coordinator
      ansible.builtin.service:
        name: app-coordinator
        state: reloaded
```

## B.2 The nginx Role Skeleton (from Lab 5)

```yaml
# roles/nginx/defaults/main.yml
nginx_listen_port: 80
nginx_server_name: "{{ inventory_hostname }}"
nginx_worker_processes: "{{ ansible_facts['processor_vcpus'] | default(2) }}"
nginx_sites: []          # [{name, port, server_name}]
```

```yaml
# roles/nginx/tasks/main.yml (excerpt)
---
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
  tags: [packages]

- name: Render site configurations
  ansible.builtin.template:
    src: site.conf.j2
    dest: /etc/nginx/conf.d/{{ item.name }}.conf
    mode: "0644"
  loop: "{{ nginx_sites }}"
  loop_control:
    label: "{{ item.name }}"
  notify: Reload nginx
  tags: [config]
```

## B.3 The Execution Environment Definition

```yaml
# execution-environment.yml - built with `ansible-builder build -t atlas-ee:1.4.0`
---
version: 3
images:
  base_image:
    name: ghcr.io/ansible/community-ansible-dev-tools:v25.5.0
dependencies:
  galaxy: requirements.yml
  python:
    - netaddr
    - jmespath
additional_build_steps:
  append_final:
    - LABEL org.opencontainers.image.source="https://git.example.com/atlas/automation"
```

## B.4 GitHub Actions: Lint, Check, Molecule

```yaml
# .github/workflows/ansible.yml
name: ansible-quality-gate
on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint-and-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Install toolchain
        run: pip install "ansible-core>=2.21,<2.22" ansible-lint ansible-dev-tools
      - name: Install collections
        run: ansible-galaxy collection install -r requirements.yml
      - name: Lint (production profile)
        run: ansible-lint --profile=production
      - name: Syntax check
        run: ansible-playbook playbooks/site.yml -i inventories/dev --syntax-check
      - name: Start container targets
        run: |
          docker run -d --name web1 -p 2201:22 --hostname web1 geerlingguy/docker-ubuntu2404-ansible
          docker run -d --name web2 -p 2202:22 --hostname web2 geerlingguy/docker-ubuntu2404-ansible
      - name: Check-mode rehearsal
        run: ansible-playbook playbooks/site.yml -i inventories/dev --check --diff
        env:
          ANSIBLE_VAULT_PASSWORD: ${{ secrets.VAULT_PASSWORD }}

  molecule:
    runs-on: ubuntu-latest
    needs: lint-and-smoke
    steps:
      - uses: actions/checkout@v6
      - name: Install toolchain
        run: pip install ansible-dev-tools
      - name: Test changed roles
        run: |
          for role in $(git diff --name-only origin/main... | cut -d/ -f2 | sort -u); do
            [ -d "roles/$role/molecule" ] && molecule test -s default --scenario-name "$role" || true
          done
```

The vault password enters as a CI secret consumed by the vault-id mechanism of [Chapter 9](#ch9); the container targets give the check-mode rehearsal real hosts; and the Molecule job limits itself to roles the pull request actually touched. All three layers of the [Chapter 12](#ch12) ladder in one file.
