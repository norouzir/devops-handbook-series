# Chapter 11 - Self-Hosted Runners and Runner Infrastructure {#ch11}

## 11.1 When Self-Hosted Makes Sense

Self-hosted runners are machines you operate - registered with GitHub, executing jobs, streaming logs back. The honest reasons to run them: specialized hardware (GPUs, Apple silicon at scale, exotic architectures), private network access to systems GitHub cannot reach (databases on a VPN, hardware-in-the-loop rigs, on-prem mainframes), very high sustained volume where dedicated capacity beats per-minute pricing, and data-locality requirements that hosted runners cannot meet. The dishonest reason is 'hosted runners are slow' - almost always a caching and parallelism problem wearing a capacity costume. And since March 1, 2026, self-hosted compute on GitHub-hosted services is metered at 0.002 dollars per minute (with monthly free allowances by plan and GHES exempt), so the cost case must now beat both hosted pricing and the new self-hosted line item.

::: {.warn}
**Watch out - never on public repositories**

A self-hosted runner on a public repository executes arbitrary pull-request code on your machine by default. Unless you have fork-pr-based hardening with isolated ephemeral runners and explicit approval flows, keep self-hosted runners attached to private repositories only. This is the single most common catastrophic misconfiguration in the ecosystem.
:::

## 11.2 Registration, Groups, and Labels

Runners register at repository, organization, or enterprise scope using a short-lived registration token and the `config.sh` (or `config.cmd`) flow from the runner release archive; the service runs under systemd (Linux), launchd (macOS), or Windows services, and current runner versions enforce an auto-update cadence that GitHub began tightening in 2026 - outdated runners are flagged and eventually blocked from the service, so fleet upgrade discipline is mandatory, not optional. **Runner groups** are administrative buckets (with network and permission isolation at org/enterprise scope), and **labels** are the dispatch vocabulary: workflows say `runs-on: [self-hosted, linux, gpu]` and the queue matches a runner carrying those labels. Labels are free-form strings - adopt a naming convention (OS, arch, capability) before the fleet grows, because relabeling a hundred machines is nobody's favorite week.

```bash
# one-time registration (ephemeral mode)
./config.sh --url https://github.com/org/repo \
  --token "$REGISTRATION_TOKEN" \
  --labels self-hosted,linux,x64,gpu \
  --runnergroup infra \
  --ephemeral
./svc.sh install && ./svc.sh start
```

## 11.3 Ephemeral Runners and Isolation

The security and reliability model of self-hosting improved decisively with `--ephemeral` mode: the runner processes exactly one job, then deregisters itself, leaving the host clean for a re-image. Paired with disposable infrastructure - a VM deleted after each job, a container discarded per job - ephemeral runners remove most of the persistent-state risks that made shared self-hosted runners dangerous: leftover caches, stray credentials in home directories, and the subtle poisonings that follow. GitHub's own guidance and every serious deployment now treat **ephemeral + immutable + reaped** as the baseline, and the billing model (per-minute metering) makes the idleness of a long-lived runner visible in a way it never was before.

## 11.4 Autoscaling with the Actions Runner Controller

The **Actions Runner Controller (ARC)** runs self-hosted runners as Kubernetes resources: `RunnerDeployment` and `RunnerSet` custom resources declare a runner image, labels, and scaling rules, and the controller creates and deletes runner pods on demand, listening to GitHub's scale-set webhooks so the fleet tracks the actual queue rather than polling guesses. Runner groups in ARC mode are managed at the enterprise level with `RunnerGroup` resources, and proxy configuration, Docker-in-Docker options, and listener tuning are all declarative. ARC 0.15.0 (October 2026) is the current release line, and kubernetes-mode runners are GA with Helm-based installation as the standard path.

```bash
# values.yaml excerpt for ARC RunnerDeployment
runnerScaleSetName: org-infra
githubConfigUrl: https://github.com/org
githubConfigRunnerGroup: infra
minRunners: 0
maxRunners: 20
template:
  spec:
    containers:
      - name: runner
        image: ghcr.io/actions/actions-runner:2.328.1
        command: [ './entrypoint.sh' ]
        resources:
          requests: { cpu: '2', memory: 4Gi }
          limits:   { cpu: '4', memory: 8Gi }
```

::: {.note}
**Best practice - scale to zero, burst honestly**

The ARC promise is minRunners: 0 with burst capacity, which pairs perfectly with per-minute metering: idle infrastructure no longer costs anything but a node's footprint. Set maxRunners from your concurrency quota (not from hope), and give each scale set its own runner group so a flood of one workflow type cannot starve another.
:::

## 11.5 Larger Hosted Runners as the Middle Path

Before standing up infrastructure, check the managed option: larger hosted runners offer 4, 8, 16, 32, and 64 vCPU Linux and Windows machines (plus Apple-silicon macOS configurations) configured at org or enterprise level, assigned through dedicated labels, billed per-minute at a premium, and unusable with included minutes. They cover the most common self-hosting motive - 'the build is heavy' - without operating a single machine, and they inherit all hosted-runner isolation properties. The 2025 cleanup removed the legacy overlap where larger runners were exposed through the self-hosted runner APIs; they are now squarely a hosted-runner product. Reserve genuine self-hosting for network access and specialized hardware, and let ARC handle volume.

::: {.lab}
### Lab 4 - Ephemeral Runner and ARC Foundations {#lab4}

1. On a disposable Linux VM (or Docker container), register a runner with `--ephemeral` against a private test repository; run one job and confirm the runner deregisters afterward.
2. Give the runner a label set (`self-hosted,linux,x64,lab`) and dispatch a workflow with `runs-on: [self-hosted, lab]`; inspect the job log header for runner name and group.
3. Deliberately skip `--ephemeral` in a second registration, run a job that writes a file to the home directory, then run an ephemeral job and compare statefulness - write the risk into your runbook.
4. Install ARC with Helm into a local Kubernetes cluster (kind from the Docker book's toolchain works); deploy a `RunnerDeployment` with `minRunners: 0, maxRunners: 2` and your lab labels.
5. Fire five parallel `workflow_dispatch` jobs and watch the controller scale pods from zero to two, then back to zero; record queue times in the summary job.
6. Metering check: review the billing usage report for the self-hosted minutes consumed by this lab and compute the monthly cost at 0.002 dollars per minute if this fleet ran 24/7.
:::

**See also:** [Chapter 3](#ch3) for the runner concept itself, [Chapter 12](#ch12) for the trust boundary a self-hosted runner crosses, and [Chapter 13](#ch13) for how their costs behave.
