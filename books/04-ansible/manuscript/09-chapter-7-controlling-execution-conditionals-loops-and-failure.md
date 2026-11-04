# Chapter 7 - Controlling Execution: Conditionals, Loops, and Failure {#ch7}

## 7.1 Conditionals: when, Honestly Applied

The `when` clause gates a task per host: its expression is a Jinja2 boolean evaluated in that host's context, and the task is *skipped* - reported as such in the run summary - rather than executed when it is false. Idioms worth burning in: `when: ansible_facts['os_family'] == "RedHat"` for dialect switching; `when: result.stdout is search('active')` after a `register`; combined forms `when: expr1 or expr2`, list form (implicit `and`), and multi-line conditions with parentheses for readability. Conditions operate on variables, facts, and registered results - never on "what the previous task printed" guessed from memory; if a decision depends on machine state, the state is registered first, as [Chapter 5](#ch5) established.

```yaml
- name: Harden SSH (Debian family)
  ansible.builtin.lineinfile:
    path: /etc/ssh/sshd_config
    line: "PasswordAuthentication no"
    state: present
  when: ansible_facts['os_family'] in ["Debian"]

- name: Harden SSH (RHEL family, firewalld present)
  ansible.builtin.template:
    src: sshd.conf.j2
    dest: /etc/ssh/sshd_config.d/50-hardening.conf
  when:
    - ansible_facts['os_family'] == "RedHat"
    - ssh_hardening is defined
```

Three refinements cover the remaining 90 percent of real conditions. `block`/`rescue`/`always` (this chapter's [Section 7.4](#s-blocks)) groups conditions and error handling structurally. Imported versus included files apply conditionals differently - an `import_tasks` with `when` stamps the condition on every imported task, while an `include_tasks` with `when` decides once whether to enter the file; pick deliberately, because tags ride along with the static case and not the dynamic one. And role-level conditions (`roles:` entries with `when`) or task-level conditions inside the role should not both exist for the same decision - one owner per condition, or the review of "why did this not run?" becomes archaeology.

## 7.2 Loops: Iterating Data Without Generating YAML

The modern loop is the `loop` keyword: it takes a list (or a Jinja2 expression producing one) and exposes each element as `item`, with `loop_control.label` making large loops readable in the log and `index_var` for position. Loops nest via `loop: "{{ outer | subelements('ports') }}"`-style constructions or the `with_nested` family of compatibility loops; dictionaries enter the loop world through `dict2items`, and grouped iteration comes from `groupby`. The discipline that keeps loops honest: the data is *declared* (a variable, a `vars_files` entry), the task is *one*, and the diff between environments is data - never a copy-pasted task wall.

```yaml
- name: Ensure service accounts exist
  ansible.builtin.user:
    name: "{{ item.name }}"
    uid: "{{ item.uid | default(omit) }}"
    groups: "{{ item.groups | default([]) }}"
    state: present
  loop: "{{ service_accounts }}"
  loop_control:
    label: "{{ item.name }}"

- name: Open documented ports
  ansible.posix.firewalld:
    port: "{{ item.1 }}/tcp"
    permanent: true
    state: enabled
  loop: "{{ app_servers | subelements('ports') }}"
```

Two sharp edges deserve permanent respect. First, **registering inside a loop** yields a result whose `results` list you index by iteration - `result.results[0].changed` - and whose shape defeats naive conditionals; `when: not item.changed`-style checks inside the loop body are usually what was meant. Second, `loop` is templated *once per host at task start* on modern cores - mutating the source list mid-loop with `set_fact` inside the same task does not extend the iteration; build derived lists with `set_fact` *before* the loop, which also makes the transformation reviewable.

## 7.3 Failure, Changed, and the Honesty Flags

Modules decide success and change themselves; tasks can overrule them with four flags that make automation honest instead of lucky. `ignore_errors: true` continues the play when a task fails (the run reports `failed` but proceeds - and the *host* is marked failed in the summary, which matters for `--limit` decisions later); `failed_when: expr` redefines failure from registered evidence - `failed_when: result.rc not in [0, 1]`; `changed_when: expr` tells Ansible whether an idempotency-blind task (`command`, `shell`, `uri`) actually changed anything - `changed_when: result.stdout | length > 0`; and `failed_when: false`-plus-explicit-assertion patterns turn probes into soft checks that feed later conditions. These flags are the idempotency toolkit promised in [Chapter 1](#ch1): they are how arbitrary commands become first-class citizens of the change contract rather than permanent `changed` noise.

::: {.warn}
**Watch out - failed_when lies are worse than failures**

A `changed_when`/`failed_when` expression written to make a red run green is technical debt with a pager. Every override should be provable from the registered output (`stdout`, `rc`, `status`) and have a one-line comment naming the evidence. When you cannot name the evidence, the task is hiding a real failure - let it fail, and fix the cause.
:::

## 7.4 Blocks, rescue, always: Structured Error Handling {#s-blocks}

`block` groups tasks so they can share policy - `become`, tags, and above all error handling. `rescue` runs when any task in the block fails (per host), `always` runs regardless; together they express rollback and cleanup the way `try`/`catch`/`finally` do in code. The rescued context receives the failure in `ansible_failed_task`/`ansible_failed_result`, which lets `rescue` branches log, notify, roll back (`command: systemctl revert ...`), or fail *differently* (a rescue that itself fails marks the host failed - the honest outcome for unrecoverable errors).

```yaml
- name: Apply config with automatic rollback
  block:
    - name: Stage new configuration
      ansible.builtin.template:
        src: app.conf.j2
        dest: /etc/app/app.conf.next
    - name: Activate and validate
      ansible.builtin.shell: |
        mv /etc/app/app.conf.next /etc/app/app.conf
        appctl validate
      changed_when: true
  rescue:
    - name: Restore previous configuration
      ansible.builtin.copy:
        src: /etc/app/app.conf.bak
        dest: /etc/app/app.conf
        remote_src: true
    - name: Report the failure onward
      ansible.builtin.fail:
        msg: "Config apply failed: {{ ansible_failed_result.stderr | default('unknown') }}"
  always:
    - name: Remove staging artifacts
      ansible.builtin.file:
        path: /etc/app/app.conf.next
        state: absent
```

The pattern above - stage, validate, rescue-rollback, always-cleanup - is the template for every risky in-place change in Part II, and [Chapter 14](#ch14) composes it with `serial` so that a bad configuration is discovered on two hosts instead of forty. Blocks also carry `when` at their own level, which applies to every contained task - the clean way to condition whole *groups* of tasks without repeating the clause.

## 7.5 The failure model: hosts, waves, and giving up

When a task fails on a host, that host stops executing the play (its remaining tasks are skipped), the other hosts finish the current task, and - by default - the play aborts once the current wave completes; subsequent plays are skipped for the failed host. The tuning knobs reshape that default deliberately: `any_errors_fatal: true` stops at the *first* failure (cluster-wide consistency operations), `max_fail_percentage: 20` tolerates a bounded fraction (fleet-wide best-effort), and the run's summary - `failed=`, `ignored=`, `changed=` - is the evidence reviewers read. Failures also interact with strategies: under `strategy: free`, a failed host stops alone while others continue, which is exactly the parallelism/blast-radius trade in miniature and the reason [Chapter 11](#ch11) treats strategy selection as a production decision rather than a convenience.

::: {.note}
**Best practice - assert early, fail loudly, skip honestly**

Open risky plays with `ansible.builtin.assert` on the preconditions that would otherwise fail mysteriously three tasks in (facts present, variables defined, versions in range). A run that dies in second one with a clear message costs minutes; a run that dies in task twelve with a traceback from deep inside a template costs an evening - and the `skipped=` count in a summary is information, not waste, when the skips encode real topology.
:::

## 7.6 Lab: Turning a fragile script into honest automation

::: {.lab}
### Lab 4 - Conditionals, loops, and the honesty flags on the container fleet {#lab4}

1. Take the Lab 3 nginx playbook and add an `assert` pre-task requiring `listen_port` to be defined and between 1-65535 - then run it against a group that lacks the variable and read the failure calmly for once.
2. Convert the package installation to a loop over a declared list (`web_packages: [nginx, curl, unzip]`), using `loop_control.label`, and prove idempotency by three consecutive runs with `changed=0` expected after the first.
3. Add an OS-dialect conditional: one group variable `package_list` per `group_vars` file, a `when` on `ansible_facts['os_family']`, and confirm exactly the right branch executes on each container group.
4. Add a health probe built from `ansible.builtin.uri` with `register`, `failed_when: false`, and a follow-up `assert` that distinguishes "service down" from "wrong status code" in the failure message.
5. Wrap the config application in a `block`/`rescue`/`always` set that restores the previous config from a backup copy and always removes the staged file; break the template on purpose and watch the rollback execute - then read the run summary aloud: failed, rescued, changed, skipped, in operator language.
:::

**See also:** [Chapter 5](#ch5) for handlers and run structure, [Chapter 6](#ch6) for the variable machinery conditions ride on, and [Chapter 14](#ch14) where these failure controls meet fleet-scale rollouts.
