# Chapter 4 - Ad-Hoc Commands and the Module Universe {#ch4}

## 4.1 Modules: The Unit of Work

A module is a small, self-contained program that accepts JSON arguments, inspects or changes the state of a system, and returns JSON describing what happened - including the all-important `changed` flag from [Chapter 1](#ch1). You never run modules by hand; Ansible ships them to the target, executes them, deletes them, and renders the result. Modules are namespaced by collection in fully-qualified form (`community.general.timezone`), with the `ansible.builtin.` prefix reserved for the engine's own set - and while the short name (`timezone`) still resolves, the fully-qualified name is what belongs in everything you keep, because two collections may both define `iptables` and only FQCN says which one you meant.

The module universe is where Ansible's breadth lives: `ansible.builtin` covers files, packages, services, users, and orchestration primitives; `ansible.posix` carries the sysadmin classics (`selinux`, `firewalld`, `mount`, `sysctl`); `community.general` is the curated long tail; clouds live in their own collections (`amazon.aws`, `azure.azcollection`, `google.cloud`); and network vendors ship `cisco.ios`, `junipernetworks.junos`, and friends. `ansible-doc -l` enumerates what is installed, `ansible-doc <fqcn>` shows arguments and examples, and the `-s` short form fits on a screen while pair-programming. When a task needs something no module does, [Chapter 5](#ch5) shows the escape hatches - `command`, `shell`, `script` - and why they are hatches rather than doors.

## 4.2 Ad-Hoc Commands: Ansible Without YAML

The `ansible` CLI runs one module against a pattern, and it is the right tool for questions and one-shot corrections: `ansible webservers -m ansible.builtin.service -a "name=nginx state=restarted" -b`. Ad-hoc runs share every input channel a playbook has - inventory, patterns, privilege escalation, vault passwords - which makes them the fastest way to exercise a new module, verify connectivity, or perform a controlled change without committing a file. The discipline is to treat ad-hoc work as ephemeral by default: the moment a command is typed twice, it graduates into a playbook, because the repository is the memory of the estate and a shell history is not.

```console
$ ansible all -m ansible.builtin.ping                       # connectivity
$ ansible webservers -m ansible.builtin.setup -a "filter=ansible_os_family*"
$ ansible dbservers -m ansible.builtin.package -a "name=htop state=present" -b
$ ansible "web*" -m ansible.builtin.command -a "df -h /"     # one-off check
$ ansible all -m ansible.posix.sysctl -a "name=vm.swappiness value=10 state=present" -b
```

The examples above trace the daily arc - reachability, facts, a package change, a read-only probe, a kernel tunable - and each one is idempotent by design: run any of them twice and the second reports `ok` rather than repeating work. That property is what licenses running ad-hoc commands against production at all, and it is worth testing your own commands for it before they touch anything with a pager attached.

## 4.3 The Command/Shell Cliff

Three modules execute arbitrary commands, and the difference between them is the difference between safe and dangerous. `ansible.builtin.command` runs a binary with arguments, *without* a shell - no pipes, no globs, no variable expansion - and it is the default choice because its arguments are unambiguous. `ansible.builtin.shell` runs through `/bin/sh` and is the correct tool exactly when shell semantics are the requirement; its arguments are subject to injection whenever any part comes from a variable, and [Chapter 12](#ch12) revisits it as a standing audit finding. `ansible.builtin.script` ships a local script to the target and runs it - a migration tool more than a design pattern, because its logic is invisible to Ansible's change tracking and to every reader of the repository.

::: {.warn}
**Watch out - command is the last resort, not the first**

`command` and `shell` tasks always report `changed` (Ansible cannot know better), never validate arguments, and rot silently. Every one of them should carry an explicit justification: `creates:`/`removes:` guards, `changed_when:` based on real output, or a `register` plus condition that proves idempotency - the patterns are in [Chapter 7](#ch7). A repository whose diff shows a new bare `command:` task deserves the same scrutiny as a new root SSH key, because that is roughly what it is.
:::

## 4.4 Check Mode, Diff Mode, and Honest Preview

`--check` runs the entire task graph without making changes - modules report what they *would* do, and tasks that cannot predict are skipped - while `--diff` adds before/after renderings for file-like modules. Together they are the rehearsal habit of the book: `ansible-playbook site.yml --check --diff` before every nontrivial run, always. The preview has honest limits, and knowing them is part of competence: tasks guarded by `register`-ed values may fail in check mode because the value never materializes, and `command` tasks simply refuse to run - both fixable with `check_mode: false` on the specific task that must execute for real (a read-only query, a directory listing) so the rest of the run stays synthetic. Check mode is also the cheapest smoke test in CI, which is why [Chapter 12](#ch12) runs it on every pull request before any container spins up.

## 4.5 Privilege Escalation: become Without Folklore

Ansible logs in as an ordinary user and escalates to another identity per task or per play with `become`; the flags `-b`/`--become`, `--become-user`, and the `become:`/`become_user:` play keywords are the same mechanism at different scopes. The default method is `sudo`, the default target is `root`, and both are overridable per host (`ansible_become_method: enable` on some network gear, `runas` on Windows) or per task. Two settings keep fleets sane: passwordless sudo for the Ansible account is the pragmatic norm (prompt-driven escalation does not parallelize), and `become: true` belongs on the *play* or *block* level rather than scattered task by task, so that reading a task never depends on remembering an earlier flag.

::: {.note}
**Best practice - one automation account, no shared roots**

Connect as a dedicated account (for example `ansible-admin`) with pinned sudoers rules, key-based auth, and no interactive login; escalate per play with explicit `become_user` where root is not actually required. The audit trail then answers "which automation, on which host, as whom" from logs alone - and the day you must revoke a human's access, the automation account is untouched.
:::

## 4.6 The Modules Worth Knowing by Heart

A working core covers most daily work, and fluency in it beats encyclopedic recall: `package` (distro-agnostic package state; `apt`/`dnf` when you need their specifics), `service` and its systemd-native sibling, `copy` and `template` ([Chapter 6](#ch6) for the templating depth), `file`, `lineinfile`, `blockinfile` for file surgery, `user` and `group`, `uri` for HTTP checks and API calls, `get_url` for fetches with checksums, `unarchive`, `cron`, `hostname`, `reboot`, and the orchestration pair `delegate_to`/`run_once` met properly in [Chapter 14](#ch14). Around them, `setup` collects *facts* - the variable portrait of a host that [Chapter 6](#ch6) turns into portable playbooks - and `wait_for`/`wait_for_connection` turn timing guesses into correctness.

The habit to build this chapter is reflexive documentation lookup: before writing any task from memory, `ansible-doc <module>` and read the *examples* section, because module argument conventions drift between collections and the embedded docs are always current for the installed version. The habit to avoid is memorizing module behavior by trial against production; containers from [Lab 1](#lab1) exist precisely so that the trial-and-error phase happens somewhere disposable.

**See also:** [Chapter 5](#ch5) to assemble these modules into plays, [Chapter 6](#ch6) for facts and templating, and [Chapter 7](#ch7) for guarding the command/shell escapes.
