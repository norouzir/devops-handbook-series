# Chapter 4 - Actions: Reusable Building Blocks {#ch4}

## 4.1 The Action Concept and the Marketplace

An action is a packaged unit of automation that a step consumes with `uses:`. Where `run:` steps are your code, actions are dependencies - curated, versioned, and reusable. The GitHub Marketplace indexes public actions with categories, verification badges, and install snippets, and the first-party `actions/` org (`checkout`, `setup-node`, `cache`, `upload-artifact`, `create-pull-request`, `attest-build-provenance`) covers the canonical tasks. A step's `uses:` value names the repository, the path within it (for multi-action repos), and the version: `uses: actions/checkout@v6`, `uses: docker/build-push-action@v6`, or `uses: ./.github/actions/internal-lint` for local composite actions.

Versioning is where hygiene matters. Tags move; `@v6` is a mutable reference that a maintainer - or an attacker who compromises the repo - can repoint. Professional practice is to pin third-party actions to a full commit SHA in workflows that touch credentials or production, and to keep the friendly major tag in a comment. Workflow lockfiles, which went GA on October 28, 2026, automate exactly this: they record reviewed commits for every action and its transitive dependencies in `.github/workflows/actions.lock` while keeping readable tags in the YAML. Dependabot opens version-update pull requests for actions (including lockfile regeneration for onboarded workflows), so pinning no longer means staying stale.

## 4.2 action.yml: Metadata, Inputs, and Outputs

Every action is defined by an `action.yml` (or `action.yaml`) at its root (or at the subpath referenced by `uses:`). The metadata declares the action's name, description, inputs with defaults and `required` flags, outputs, and the `runs:` stanza that selects the implementation type. Inputs are passed as step `with:` values and arrive to the implementation as `INPUT_<NAME>` environment variables (upper-cased, spaces to hyphens) for composite actions, or as an input object for JavaScript actions. Declaring outputs requires the implementation to append to `GITHUB_OUTPUT`; consumers read them as `steps.<id>.outputs.<name>`.

```yaml
name: 'Deploy manifest'
description: 'Renders and applies a k8s manifest for one service'
inputs:
  service:
    description: 'Service name'
    required: true
  image:
    description: 'Full image reference to deploy'
    required: true
  dry_run:
    description: 'Render without applying'
    required: false
    default: 'true'
outputs:
  manifest_path:
    description: 'Path of the rendered manifest'
    value: ${{ steps.render.outputs.path }}
runs:
  using: 'composite'
  steps:
    - id: render
      shell: bash
      run: ./render.sh '${{ inputs.service }}' '${{ inputs.image }}' > manifest.yaml
      # simplified for illustration
    - id: apply
      if: ${{ inputs.dry_run == 'false' }}
      shell: bash
      run: kubectl apply -f manifest.yaml
```

## 4.3 Composite Actions

Composite actions are YAML files that bundle a sequence of steps - including `run:` steps and nested `uses:` steps - into one reusable unit. They run on the caller's runner, need no build toolchain, support `shell:` on every `run:` step, and are the default choice for in-house reuse: the team's standard 'checkout plus tool setup plus cache restore' incantation, the vetted linting preamble, the org-specific Docker login dance. Composite actions can set outputs for later steps, forward environment variables, and even reference other actions, which lets you compose small, auditable layers instead of one monolith. Keep one composite action per concern, store them either in `.github/actions/` of the same repository for simple cases or in a dedicated internal repository with its own review process for organization-wide reuse.

::: {.note}
**Best practice - prefer composite for internals**

When choosing between the three action types for internal automation, default to composite. JavaScript actions buy you unit-testable logic but add a Node toolchain and a build step; container actions buy you a pinned environment but cost image pull time on every run. Most internal needs are 'run these five vetted steps in this order', which is exactly what composite does.
:::

## 4.4 JavaScript Actions and the Node 24 Runtime

JavaScript actions execute on the runner's built-in Node runtime and talk to the platform through the `@actions/core` and `@actions/github` toolkits - clean APIs for inputs, outputs, artifacts, and an authenticated Octokit client. They are the right choice for logic that is awkward in shell: structured API calls, complex parsing, conditional fan-out. The packaging contract matters: the `main:` entry in `action.yml` points at a bundled file (conventionally `dist/index.js`), built with a bundler such as esbuild so the action has no install step at runtime.

The runtime migration is the event of 2026 and you must know it cold. Runner v2.328.0 shipped with both Node 20 and Node 24, defaulting to Node 20; on June 16, 2026 runners began defaulting to **Node 24**; and on September 23, 2026 Node 20 was removed entirely, along with the `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION` escape hatch. Action metadata now declares `runs: using: node24`. Consequences: any first-party action you maintain needs a rebuilt `dist` under `node24`; any pinned old major of a vendor action needs a Dependabot-style bump; self-hosted fleets need current runner versions, and Node 24 does not support macOS 13.4-or-earlier hosts or ARM32 at all. The debugging signature of an un-migrated action is a startup failure on the runner, not a test failure - which is why the post-job `post:` phase of popular actions was also rebuilt and why you should test cache-save and cleanup paths, not just happy-path steps.

```yaml
# action.yml of a JavaScript action after the Node 24 migration
name: 'Wait for rollout'
description: 'Polls a deployment endpoint until healthy or timeout'
inputs:
  url:
    description: 'Health endpoint'
    required: true
  timeout-seconds:
    description: 'Give up after N seconds'
    default: '300'
runs:
  using: 'node24'
  main: 'dist/index.js'
```

## 4.5 Docker Container Actions

The third implementation type builds and runs the action inside a `Dockerfile` you point at from `runs: using: 'docker'`. The action's environment is fully pinned - libc, tooling, everything - and `ENTRYPOINT` receives the inputs as arguments or `INPUT_*` variables. Container actions shine where the logic depends on a heavyweight toolchain you do not want to install per run: a linter with native dependencies, an infrastructure CLI with an exotic runtime. The trade-offs are cold-start cost (the image builds or pulls on every run unless cached), Linux-only execution, and the container restrictions described in Chapter 3. As a rule of thumb: composite for orchestration, JavaScript for platform API logic, Docker only when the environment itself is the deliverable.

## 4.6 Publishing, Sharing, and Governing Actions

Publishing to the Marketplace requires a public repository, a `Dockerfile` or compiled `dist`, and a release tagged `v<major>` with proper semver metadata; the draft-release flow in the repository UI walks you through it. Internal distribution is simpler and more important in practice: organization-owned repositories of reusable actions, consumed by SHA-pinned references and gated by `CODEOWNERS` review. On the consumption side, organizations control what workflows may use through the **allowed actions** policy (permitted Marketplace actions and verified creators), and now through the **Require lockfile** policy for lockfile-onboarded workflows. Both controls live in organization settings, and Chapter 14 folds them into the full governance picture.

::: {.warn}
**Watch out - transitive dependencies move too**

A composite action you pin by SHA may itself `uses:` a mutable tag downstream, and a `run:` step may `curl` a script from a moving URL. Supply-chain review must consider the whole closure. Workflow lockfiles record transitive action dependencies automatically; for non-action dependencies (downloaded binaries, install scripts), checksum them in the workflow itself.
:::

**See also:** [Chapter 5](#ch5) for the expressions an action receives, [Chapter 10](#ch10) for composing actions into reusable workflows, and [Chapter 12](#ch12) for pinning them safely.
