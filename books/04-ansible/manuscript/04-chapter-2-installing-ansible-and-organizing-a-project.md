# Chapter 2 - Installing Ansible and Organizing a Project {#ch2}

## 2.1 Choosing the Distribution: Package 14 and ansible-core 2.21

Two PyPI distributions matter, and choosing between them deliberately prevents months of quiet confusion. `ansible-core` is the engine: the executor, the CLI entry points (`ansible`, `ansible-playbook`, `ansible-vault`, and friends), and a small set of `ansible.builtin` modules and plugins. `ansible` - the community package - is the engine plus a curated, versioned set of community collections; the current line is package 14 (based on ansible-core 2.21, current as 14.3.x at this writing), with minor releases landing about every four weeks and each major pairing announced with a porting guide. Install the community package unless you have a specific reason not to: the `ansible.builtin` content alone cannot manage packages, clouds, or much of anything real, and half of a beginner's frustration is hunting for modules that live one collection away.

The install target matters as much as the package. Always install into a virtual environment - `python3 -m venv` plus `pip install ansible` - or into a container; never into the system Python of your workstation, where the resolver will eventually fight your OS. The control node wants a modern CPython (the 2.21 line sits firmly in the 3.12+ era; the official support matrix in the release and maintenance page of the docs is the authoritative word per release) and nothing else beyond SSH client plumbing. If you want the batteries-included developer setup in one command, `pip install ansible-dev-tools` brings the lint/test/build constellation - `ansible-lint`, `molecule`, `ansible-builder`, `ansible-creator`, `ansible-navigator` - versioned to work together, which is exactly what [Chapter 12](#ch12) assumes.

## 2.2 Verifying the Install and Meeting the CLI

Verification is a one-liner and a habit: `ansible --version` prints the core version, the configured `ansible.cfg` location, the Python interpreter, and the `jinja2`/`yaml` library versions - read it once per environment, because it answers half of all "which Ansible ran that?" mysteries. `ansible-doc -l` lists installed modules, `ansible-doc <name>` renders a module's documentation with examples, and `-s` gives the short form; the docs ship with the tool, and the habit of checking them before writing a task saves more time than any tutorial. `ansible-galaxy collection list` shows the collections in play, and after installing package 14 you will see dozens - `community.general`, `ansible.posix`, `community.docker`, `kubernetes.core` - which is the curated set doing its job.

The two entry points you will use constantly are `ansible` for ad-hoc commands and `ansible-playbook` for playbooks, and both share the same option grammar: `-i` selects inventory, `-m` names a module, `-a` passes arguments, `-b` asks for privilege escalation, `--check` and `--diff` preview changes, and `-l` limits the run to a subset. [Chapter 4](#ch4) works the ad-hoc surface properly; for now, one command proves the plumbing end to end:

```console
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install ansible
$ ansible --version
ansible [core 2.21.5]
  config file = /home/ops/atlas/ansible.cfg
  configured module search path = ['/home/ops/.ansible/plugins/modules']
  ansible python module location = .venv/lib/python3.12/site-packages/ansible
$ ansible localhost -m ansible.builtin.ping
localhost | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

## 2.3 Project Layout and ansible.cfg Discovery

Ansible finds its configuration by walking up from the current directory to the first `ansible.cfg` (environment variables `ANSIBLE_CONFIG` override it, and `~/.ansible.cfg` and `/etc/ansible/ansible.cfg` are the fallbacks), which makes the project-local file the correct home for everything a repository needs to be reproducible. A small, deliberate `ansible.cfg` - defaults for inventory path, host key checking policy, and forks; sensible stdout callback; a named collections path - means `git clone` plus `cd` is the entire onboarding. The settings reference in [Appendix A](#appA) lists the keys that matter; the shape to internalize is that behavior which varies per person belongs in `~/.ansible.cfg`, behavior which defines the project belongs in the repo, and almost nothing belongs in `/etc`.

```ini
# ansible.cfg - project-local, versioned
[defaults]
inventory = inventories/dev
host_key_checking = False
forks = 20
callbacks_enabled = ansible.posix.profile_tasks
collections_path = ./collections

[ssh_connection]
pipelining = True
```

The directory skeleton that the rest of this book assumes is deliberately boring and grows with you: `inventories/` for host data ([Chapter 3](#ch3)), `playbooks/` for entry points, `roles/` for reusable units ([Chapter 8](#ch8)), `collections/` for installed collections via `requirements.yml` ([Chapter 8](#ch8) and [Appendix B](#appB)), and `group_vars/`/`host_vars/` beside the inventory. The `ansible-creator` tool scaffolds modern layouts (including collection layouts) when you would rather not type the tree by hand - the skeleton in [Appendix B](#appB) matches what it generates closely enough that either path works.

## 2.4 Targets You Can Actually Run: Containers as Managed Hosts

Every exercise in this book needs real managed hosts, and borrowing production for it is not a plan. The trick this series uses is to make Docker containers pretend to be Linux hosts: an image with an SSH daemon (or Python plus `community.docker.docker` connection) is a perfect, disposable target for package, file, service, and user modules, and it costs nothing to destroy and recreate mid-chapter. For the labs we use images that ship an SSH server, connect over the container network, and treat each container exactly like a cloud VM - the inventory entry is identical, which is the pedagogical point: Ansible does not care what is behind the address.

```yaml
# Lab targets, preview of Chapter 3 - two "hosts" that are containers
all:
  hosts:
    web1:
      ansible_host: 127.0.0.1
      ansible_port: 2201
      ansible_user: root
    web2:
      ansible_host: 127.0.0.1
      ansible_port: 2202
      ansible_user: root
```

::: {.warn}
**Watch out - localhost is not a rehearsal**

`ansible localhost -m ...` proves the control node works, and `connection: local` is a legitimate production pattern for controlling APIs. But rehearsing playbooks against localhost teaches the wrong reflexes: no SSH layer, no privilege escalation across the network, no concurrency. Use container or VM targets for everything you will later point at real machines - the failure modes you need to practice live behind the connection, not in front of it.
:::

## 2.5 Execution Environments, Briefly

The old joke about Ansible's control node - it works on my laptop - got a structural answer: the execution environment (EE), a container image that bundles `ansible-core`, the collections, their Python dependencies, and sometimes the plugins, so that the same image runs your automation everywhere. In Part II, [Chapter 10](#ch10) builds EEs properly with `ansible-builder` and runs them through `ansible-navigator`; the reason to meet the idea now is orientation - when you install the community package in a venv tonight, you are using the *developer* workflow, and when your CI or controller runs the same automation inside a pinned EE, you are using the *production* workflow, and the playbooks are identical across both. Ansible itself ships community EE base and minimal images, versioned to match the community package, so the upgrade path is public and boring on purpose.

## 2.6 Lab 1: A Two-Node Fleet in Containers and Your First Playbook

::: {.lab}
### Lab 1 - First contact: container fleet, ad-hoc commands, and a first playbook {#lab1}

1. Start two disposable targets with SSH: run `docker run -d --name web1 -p 2201:22 --hostname web1 chrismeyersfsu12/ansible-ssh` or any SSH-enabled test image twice, mapping 2201 and 2202, and confirm `ssh -p 2201 root@127.0.0.1` reaches each one. (Any SSH-capable image works; the point is two reachable "hosts".)
2. Create the project skeleton from Section 2.3 - `ansible.cfg`, `inventories/dev/hosts.yml` with the two hosts on ports 2201/2202 - and run `ansible all -m ansible.builtin.ping -i inventories/dev` until both hosts answer `pong`.
3. Go ad-hoc: `ansible all -m ansible.builtin.command -a "uptime" -i inventories/dev`, then `ansible web1 -m ansible.builtin.package -a "name=htop state=present" -b -i inventories/dev`, running the second command twice and reading the `changed`/`ok` distinction out loud.
4. Write `playbooks/bootstrap.yml` that ensures `htop` and `vim` are present, creates user `ops` with your SSH key in `authorized_keys`, and sets the timezone - run it with `--check --diff` first, then for real, then a third time and confirm everything reports `ok`.
5. Break something on purpose: remove `htop` inside one container by hand (`apt-get remove -y htop`), rerun the playbook, and watch Ansible reconcile exactly one host exactly one task. That reconciliation loop is the whole product; everything else in this book is detail on it.
:::

**See also:** [Chapter 3](#ch3) to make the fleet legible, [Chapter 4](#ch4) for the ad-hoc surface, and [Appendix B](#appB) for a ready-made project skeleton.
