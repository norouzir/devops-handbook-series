# Chapter 10 - Execution Environments and the Modern Toolchain {#ch10}

## 10.1 The Works-On-My-Control-Node Problem

A control node accumulates state: the Python interpreter and its packages, the collections and their versions, the system libraries a module needs, the connection utilities, the locale. Automation that ran perfectly on the author's laptop fails in CI because a collection resolved to a newer major; it fails on the new colleague's machine because `boto3` is missing; it fails six months later on the *same* laptop because a dependency moved. Every failure is real, none is Ansible's fault, and all of them are the same failure: the runtime is not pinned. The execution environment (EE) is the structural answer - a container image that bundles `ansible-core`, collections, Python dependencies, and system libraries - so the question "which Ansible ran this?" has one versioned, digest-pinned answer everywhere it is asked.

An EE is not a nice-to-have abstraction; since the automation-platform world standardized on it, it is the unit in which production automation ships. CI runners pull the same image your controller runs; the controller builds job templates on named EEs; developers run the same image through `ansible-navigator` locally. The playbook becomes portable precisely because it stopped carrying its own environment - the environment travels beside it, immutably, and [Chapter 12](#ch12) tests the image like any other artifact.

## 10.2 ansible-builder: Defining and Building the Image

`ansible-builder` turns a declarative file into an EE image. The modern format is `execution-environment.yml`: a base image, the collections (usually via `requirements.yml` from [Chapter 8](#ch8)), extra Python requirements, and optional system packages and Ansible flags - and `ansible-builder build` produces the image through a staged Containerfile (a builder stage that resolves dependencies and a final stage that assembles the runnable environment).

```yaml
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
  system:
    - iproute
additional_build_steps:
  append_final:
    - LABEL maintainer="platform-team@example.com"
```

The base-image choice is the main design decision: the community ships versioned `base` and `minimal` EE images (matching the community package line, refreshed with each release), `ansible-dev-tools`-based images suit development, and Red Hat-supported images serve platform subscribers. Start from the community base, add *only* what the dependency resolution proves you need, and treat the resulting image as a contract - its tag is semantic (core version, date), its digest is what production references, and upgrades are a pull-request-plus-test event, not a background `pip install`. Build it in CI on every change to `requirements.yml` or the EE definition, push to your registry, and the fleet's automation runtime becomes as reviewable as the automation itself.

## 10.3 ansible-navigator: Running EEs Locally

`ansible-navigator` is the runner built around EEs: it executes playbooks and ad-hoc commands inside the container image through a TUI (or a plain `--mode stdout` stream), mounts the project directory read-only by default, and renders module output through an interactive viewer. The mental shift from `ansible-playbook` is small and total: you keep every habit from Part I - inventory, check mode, vault ids - and add the discipline that the *image* is part of the invocation, exactly as it will be in CI and on the controller. The `ansible-navigator.yml` settings file pins the EE, pull policy, and mode per project, which keeps "run it like CI runs it" a one-word command.

```console
$ ansible-navigator run site.yml -i inventories/dev --mode stdout --eei atlas-ee:1.4.0
$ ansible-navigator run site.yml --check --diff --mode stdout
$ ansible-navigator doc ansible.builtin.template --mode stdout
```

Local iteration on the container fleet from Part I works unchanged under navigator - the Docker connection plugin talks to the daemon from inside the EE given a mounted socket - and the payoff arrives the first time a colleague runs the playbook with zero setup beyond pulling the image. The failure mode to expect is path/mount friction (vault password files and inventory directories must be inside the mounted workspace or passed by volume); the cure is the same as always in this book - rehearse the exact invocation in the lab before production borrows it.

## 10.4 The Toolchain Around the Engine

The modern Ansible developer toolchain is a constellation of small, sharp tools, versioned to travel together in `ansible-dev-tools`. `ansible-creator` scaffolds projects and collections with modern layout and best-practice defaults; `ansible-lint` enforces the rulebook that [Chapter 12](#ch12) turns into a quality gate; `molecule` tests roles and collections against throwaway instances; `tox-ansible`/`pytest-ansible` cover plugin-level testing; `ansible-builder` and `ansible-navigator` close the EE loop. The versioning habit that keeps the constellation coherent: install the *meta-tool* (`pip install ansible-dev-tools`) in development images, and pin the pieces individually in CI so upgrades are deliberate; the tools move independently, and a `requirements-dev.txt` with real versions is cheaper than a surprise.

Two further pieces complete the map. Private automation hub (upstream: Galaxy NG) is a self-hostable registry for collections and EE images - the place your internal collections, vendored third-party collections, and built EEs live behind access control, with `requirements.yml` pointing at it through a server block. And the `ansible` community package's cadence (minor releases about every four weeks, majors each spring and fall paired with core) sets the project's upgrade rhythm: EE images rebuilt on the new base, `requirements.yml` ranges reviewed against the porting guide, and the full test suite of [Chapter 12](#ch12) as the gate - the boring, deliberate upgrade that this entire chapter exists to make possible.

::: {.note}
**Best practice - one image per estate, versioned like a product**

Resist per-project EE sprawl. A small set of estate-wide images - standard, plus special cases with a documented reason - keeps base-image CVE patching a single build pipeline, makes the "which image runs where" question answerable from a table, and lets the platform team own the runtime while product teams own the playbooks. The image tag is the API between those two teams; treat it with the same seriousness.
:::

**See also:** [Chapter 8](#ch8) for the `requirements.yml` this chapter bakes into images, [Chapter 12](#ch12) for testing the image and its contents, and [Chapter 13](#ch13) for the platform layer that runs EEs at fleet scale.
