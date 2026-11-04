# Appendix C - Troubleshooting Guide {#appC}

Symptoms first, causes second, fixes third - organized the way incidents arrive. The general order of operations applies here too: reproduce on the container fleet, read the run summary, escalate verbosity (`-vvv` for connections, `-vvvv` for SSH internals), and only then change code.

## C.1 Connection and Authentication Failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `UNREACHABLE ... Failed to connect` | Wrong `ansible_host`/port, SSH service down, security group | `ssh -p <port> user@host` by hand; check the inventory entry that differs |
| `Permission denied (publickey)` | Key not loaded/owned, wrong user | `ssh-add`, verify `ansible_user` and `ansible_ssh_private_key_file`; check key `chmod 600` |
| `host key verification failed` | Unknown host key | Deliberate: `host_key_checking` policy per [Chapter 2](#ch2); never blanket-disable in prod inventories |
| Works as user, fails with `become` | sudoers requires TTY or password | `pipelining` needs passwordless sudo; check `requiretty` relics |
| Intermittent `UNREACHABLE` at scale | SSH rate limiting, MaxStartups | Raise ControlPersist, lower `forks` waves, check `sshd` logs |
| Windows: `connection refused` on 5985/5986 | WinRM listener/HTTPS misconfig | `winrm` listener check via PowerShell; verify `ansible_connection: winrm` + `ansible_port` |

## C.2 Module and Interpreter Failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `No python interpreters found` | No/odd Python on target | Pin `ansible_python_interpreter` in inventory ([Chapter 3](#ch3)) |
| `ModuleNotFoundError` on target only | Missing Python lib in chosen interpreter | Install via `package`/`pip`, or pick the distro Python |
| `paramiko: SSHException` | Control-node crypto mismatch | Prefer OpenSSH transport (default); refresh control-node crypto libs |
| Module hangs on one host | Stale ControlMaster socket, deadlock | Kill control path (`ssh -O exit`), re-run that host |
| `command` module fails quoting | Arguments passed through a shell habit | Use `argv:` form ([Chapter 4](#ch4)); reserve `shell` for real shell needs |

## C.3 Variable and Templating Errors (Post-2.19 Engine)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `variable is undefined` at task N | Precedence assumption wrong | `ansible -m debug -a "var=..."` per host; consult the [Appendix A](#appA) spine |
| `template error while templating string` | Type confusion in Jinja2 | Print the value with `debug`; apply `|string`/proper tests deliberately ([Chapter 6](#ch6)) |
| Condition silently false on some hosts | Fact missing (gather_facts off, subset too small) | Guard with `is defined` + `assert` preconditions ([Chapter 7](#ch7)) |
| Value "lags" one task behind | Lazy evaluation + same-list mutation | Capture with distinct `set_fact` names; register-then-use immediately |
| YAML: `mapping values are not allowed` | Unquoted `{{ }}` starting a value | Quote: `key: "{{ value }}"` |
| `loop` does not see updated list | List mutated inside same task list | Build derived list before the loop |

## C.4 Vault and Secret Errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Decryption failed` | Wrong/missing vault password or id | Check `--vault-id` order/labels; script-based source prints its own errors ([Chapter 9](#ch9)) |
| Secret appears in logs | Task not `no_log` | Add `no_log: true`; redact the leaked log as an incident |
| `--diff` shows a password | Template renders secret into file | `mode: "0600"`, avoid diffs on secret files, redact summaries |
| Rekey leaves old password working | Some file encrypted with another id | `grep -rl ANSIBLE_VAULT` the repo; rekey per identity |
| CI: works locally, fails there | Password source differs | Executable vault-id script + CI secret injection ([Appendix B](#appB)) |

## C.5 Handler, Order, and Rollout Mysteries

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Handler never ran | No notifying task reported `changed` | Expected; verify with `--diff` what actually changed |
| Handler ran too late | Queue drains at play end | `meta: ansible.builtin.flush_handlers` at the right point ([Chapter 5](#ch5)) |
| Tag run skips a dependency | Tags on dynamic includes behave differently | Move the decision to static imports or restructure ([Chapter 14](#ch14)) |
| Rolling update proceeds on bad wave | `max_fail_percentage` too lax / no post assert | `max_fail_percentage: 0` + real health assertions ([Chapter 14](#ch14)) |
| `run_once` result missing on other hosts | Registered context confusion | Read via `hostvars[first_host]['result']`; document the pattern |
| Delegated task uses wrong facts | `delegate_facts` default | Decide explicitly and comment the choice |

## C.6 When to Escalate to the Ecosystem

Some failures are not yours to fix, and knowing where each class belongs saves evenings. Bugs in modules or plugins belong on the owning collection's issue tracker (reproduce first on the container fleet, include `ansible --version` and the FQCN). Core templating and executor behavior - especially anything that changed with data tagging - belongs on the ansible-core tracker with a minimal reproduction, checked against the current porting guide. Platform-layer failures (controller, EDA, navigator) go to their respective projects, with the EE image digest attached. And the standing habit that prevents most escalations entirely: pin versions, read the porting guide before upgrades, and keep the [Chapter 12](#ch12) suite green so that the fleet's automation is always one replay away from proven-good.
