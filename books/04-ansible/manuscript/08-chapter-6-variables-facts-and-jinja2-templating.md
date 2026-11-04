# Chapter 6 - Variables, Facts, and Jinja2 Templating {#ch6}

## 6.1 Where Variables Live and Who Wins

Ansible variables arrive from more places than any other tool you will use - inventory files and their `group_vars`/`host_vars` directories, `vars:` blocks, `vars_files`, role defaults, `set_fact`, registered results, extra vars on the command line - and the engine resolves them at use time with a precedence order the documentation numbers at twenty-plus levels. The full list is reference material in [Appendix A](#appA); working competence needs only the shape of it: *extra vars (`-e`) beat everything; then `include_params`/task-level `vars`; then `set_fact` and registered results; then role variables; then block/play/`vars_files`; then host facts; then `host_vars`; then `group_vars` (with later-listed inventory groups beating earlier ones - child groups over parents); then role defaults lose to everything.* The one-sentence summary professionals use: *the more specific and the more explicitly passed-in, the stronger.*

Two consequences follow that are worth adopting as reflexes. First, never debug precedence by reordering files - debug it by asking where a value *should* live: defaults a role ships (`role/defaults/main.yml`), configuration a deployment chooses (`group_vars`), identity per host (`host_vars`), or a knob an operator may override tonight (`-e` or `vars:` at the call site). Second, scope is lexical and per-host: a variable set in a play is visible to every task in that play *for each host in it*, and values are always evaluated in the context of the host currently executing - the reason `hostvars` ([Section 6.4](#s-magic)) exists as the window between hosts.

## 6.2 Facts: The Machine's Own Variables

*Facts* are variables Ansible discovers about a target by running the `setup` module - addresses, OS family, distributions, kernels, disk layout, Python version, thousands of keys under `ansible_*` (`ansible_facts['os_family']`, `ansible_default_ipv4.address`, `ansible_processor_vcpus`). Collected by default at the top of every play (`gather_facts: true`), they are the standard machinery for portable playbooks: choose package names by `ansible_os_family`, size workers by memory, render templates with the real interface addresses. `ansible <host> -m setup -a "filter=ansible_os*"` is the fastest way to see what a given machine actually reports, and fact values are ordinary variables - usable in templates, conditions, and lookups like anything you defined yourself.

Fact gathering costs seconds per host, and mature projects tune it three ways. `gather_facts: false` on plays that only orchestrate (API calls, load-balancer members, cloud resources) removes the largest fixed cost in the run; *fact caching* (`ansible.cfg`: `fact_caching = ansible.builtin.jsonfile` with a TTL) persists facts between runs so playbooks can use `ansible_memtotal_mb` without a fresh round-trip - [Chapter 11](#ch11) tunes this properly; and `module_defaults` (play-level) pins defaults for repeatedly used modules, facts included when you use explicit `setup` calls. The `ansible.builtin.gather_facts` module keyword and `setup`'s `filter`/`gather_subset` arguments trim which subsets are collected when only network or only hardware facts are needed.

::: {.note}
**Best practice - filter facts when you only need a few**

On large fleets with fact caching disabled, `gather_subset: "!all,network"`-style filters (via `setup` arguments or `module_defaults`) cut per-host collection time dramatically. It is the cheapest performance win in the tool - and the one most often discovered three years into a project instead of three days.
:::

## 6.3 Templating with Jinja2: The Grammar

Every string in a task - module arguments, file contents through `template`, conditionals - is a Jinja2 template rendered before execution. The grammar has two forms: `{{ }}` prints an expression, `{% %}` is a statement (loops, conditionals, macros) usable inside templates and, in controlled doses, in task arguments; comments are `{# #}`. Filters transform values on the way through: `default` (with its crucial second argument `true` to also catch empty strings and booleans-false), `lower`/`upper`, `join`, `split`, `regex_replace`, `to_json`/`from_json`, `b64encode`, `password_hash` (note: since ansible-core 2.21 the hashing backend is libcrypt/libxcrypt rather than passlib - hashes remain valid but byte-for-byte output may differ from older runs), and the structural trio `combine`, `groupby`, and `dict2items` that turn YAML-shaped data into loopable shapes. *Tests* are used with `is`/`is not`: `defined`, `match`/`search`, `version` (the correct way to compare software versions), `subset`, `boolean`.

```yaml
- name: Configure monitoring endpoint
  ansible.builtin.template:
    src: exporter.yml.j2
    dest: /etc/exporters/exporter.yml
  vars:
    listen_port: "{{ exporter_port | default(9100) }}"
    region: "{{ ansible_facts['machine_id'][:2] | lower }}"
```

Jinja2 *lookups* pull data from outside the host at control-node execution time - `lookup('ansible.builtin.file', path)`, `lookup('ansible.builtin.env', 'USER')`, `lookup('ansible.builtin.pipe', cmd)`, `ansible.builtin.url`, and the credential connectors used in [Chapter 9](#ch9) - and the `query` form returns the full list where `lookup` flattens to a string. Lookups run *on the control node*, never on the target - a distinction that explains both their speed and their security posture, and the reason a lookup can read your workstation's SSH keys while the target sees only the rendered result.

## 6.4 Magic Variables and Cross-Host Sight {#s-magic}

A handful of variable names are reserved and immensely useful: `inventory_hostname` (the host's name in inventory - use it instead of `ansible_hostname` when you want the inventory identity, which does not depend on facts or OS), `play_hosts`/`ansible_play_hosts_all` (hosts in the current play), `groups` and `group_names` (the whole group structure and this host's memberships), and above all `hostvars` - a dictionary of every host's variables and facts, readable from any host's context. `hostvars` is how one host learns another's address: a load balancer rendered on `lb1` needs `groups['webservers'] | map('extract', hostvars, 'ansible_host')`; a leader election needs `hostvars[groups['dbservers'][0]]`. Set once, per run, in the host's own context - `set_fact` and `register` - these become visible cross-host through the same window, which is the sanctioned way playbooks coordinate without a database.

## 6.5 Data Tagging and the 2.19+ Templating Overhaul

ansible-core 2.19 replaced the templating engine's internals and introduced *data tagging*: values now carry machine-readable tags about their type, origin, trust, and whether they are templatable, and the engine's lazy evaluation renders strings only when needed. For playbook authors the visible changes are mostly good news and one habit change. Good news: type confusion fails loudly instead of silently - a string that happens to contain `{{ }}` is no longer mysteriously re-templated, booleans stop being "yes"/"no"/"True"/"1" soup in conditions, and errors point closer to the real problem. The habit change: constructs that leaned on string-coercion quirks (double-templating values through variables, `when` conditions written as strings that morph types, `|bool` guards against values that are now properly typed) need revisiting, and the official 2.19 porting guide is the checklist for retrofitting older repositories.

The practical guidance for new code is to treat types as real: compare with `version`, test with `is boolean`/`is number`, pass structured data (lists, dicts) through variables instead of joining strings and re-splitting them, and use `|string` deliberately when a genuinely textual value is needed. With data tagging, Ansible can also *report* which values were marked untrusted (for example values originating from an untrusted source such as task results), which underpins the security posture discussed in [Chapter 12](#ch12) - the same rewrite that made templating stricter made the trust story legible.

::: {.warn}
**Watch out - lazy evaluation changes observed side effects**

Because templating is lazy on the 2.19+ engine, a value referenced in a `when` or passed to a module may render *later* than intuition suggests - after later `set_fact`s in the same play, in some plugin paths. Sequences that mutate a variable and compare it in the same task list should capture intermediate values explicitly (`set_fact` with distinct names or `vars` at block scope). The old advice "register then use immediately" is now the mandatory advice, not the polite one.
:::

## 6.6 Declaring, Loading, and Protecting Variables

The remaining mechanics round out daily practice. `vars:` blocks inline small, context-local values; `vars_files:` loads a YAML file per play (values known at authorship, secret values belong to [Chapter 9](#ch9)); `include_vars` loads files dynamically per host or per condition - the correct tool for `vars/{{ ansible_os_family }}.yml` dialect switching. `set_fact` computes and pins a host-scoped value mid-run (from registered results, cross-host `hostvars` reads, or arithmetic); `ansible.builtin.assert` turns expectations into failures with human-readable messages, and is the polite cousin of the task-graph errors you get otherwise. Two small syntax habits prevent the most common bugs: quote every YAML value that starts with a brace (`listen_port: "{{ x }}"` or YAML will parse it as a mapping), and prefer `:` block scalars or `>-` folded scalars in templates so that colons in rendered content do not fight the parser.

**See also:** [Chapter 5](#ch5) for the playbook these variables feed, [Chapter 7](#ch7) for conditionals over registered values, [Chapter 9](#ch9) for the secret half of variable hygiene, and [Appendix A](#appA) for the full precedence table.
