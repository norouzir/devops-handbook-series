# Chapter 1 - CI/CD and GitHub Actions: The Landscape {#ch1}

## 1.1 Why Continuous Integration and Continuous Delivery

Continuous integration is the discipline of merging every developer's work into a shared mainline frequently, and proving that the mainline is healthy on every merge. Continuous delivery extends that proof forward: the code that passed CI is automatically packaged, versioned, and staged for release, so that deployment becomes a routine decision rather than a quarterly event. The value is not the tooling; it is the shrinkage of feedback loops. A defect introduced at 10:00 and reported at 10:07 is a five-minute fix. The same defect discovered in production three weeks later is an incident, a postmortem, and a trust deficit with your users.

A CI/CD system does four jobs well: it builds the software reproducibly, it runs the test suites that gate merging, it produces versioned artifacts that can be promoted rather than rebuilt, and it deploys those artifacts to environments under explicit policy. Everything else - dashboards, badges, notifications - is secondary. When you evaluate any automation platform, including GitHub Actions, evaluate it against those four jobs first. The platform that wins is rarely the one with the longest feature list; it is the one your team can debug at 2 a.m. when the release is blocked.

GitHub Actions entered general availability in November 2019 and is now the automation layer built into every GitHub repository and most GitHub Enterprise installations. Its strategic advantage is collocation: the code, the pull requests, the checks, the packages, and the pipeline configuration live in one place with one permission model. For teams that already collaborate on GitHub, Actions removes the integration tax that a separate CI server imposes - there are no webhooks to wire, no credentials to mirror, and no second user directory to maintain.

## 1.2 The Execution Model

The GitHub Actions model is a hierarchy of four nouns. An **event** is something that happens in or to a repository: a push, a pull request, a manual click, a timer, or an HTTP webhook. A **workflow** is a YAML file in `.github/workflows/` that declares which events trigger it and what to do. A workflow contains one or more **jobs**, which are the units of scheduling and failure isolation. Each job contains a linear list of **steps**, and each step is either a shell command or a reference to an **action** - a packaged, reusable unit of automation. Understanding which level owns which concern is half of your daily debugging: failures and timeouts belong to jobs, parallelism and dependencies belong to jobs and `needs`, and data flow belongs to steps and their outputs.

```yaml
name: CI
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: npm ci
      - run: npm test
```

The snippet above is a complete, valid workflow. When a commit lands on `main`, GitHub queues a run, allocates a fresh **runner** (a virtual machine or, in the self-hosted case, a registered agent), checks out the code, and executes the steps in order. If any step exits non-zero, the job fails and later steps are skipped unless marked `if: always()`. Runs are immutable records: each one pins the commit it ran against, the workflow file as it existed at that commit, and the logs it produced, which makes them both an audit trail and a debugging surface.

Jobs in a workflow run in parallel by default and communicate through explicitly declared outputs and `needs` dependencies, which you will meet properly in Chapter 5. This is deliberately different from the single linear pipeline of older systems: an Actions workflow is closer to a small directed acyclic graph that you express in YAML. That shape maps naturally onto real work - lint and unit tests can run simultaneously, integration tests wait for a build, and deployment waits for all of them.

## 1.3 What the Platform Provides Out of the Box

Actions ships with a substantial managed substrate. **GitHub-hosted runners** give you ephemeral virtual machines maintained by GitHub - Ubuntu 24.04, Windows Server 2022 and 2025, and macOS images including Apple-silicon runners - with a broad toolchain preinstalled and refreshed on a published schedule. **GitHub Packages** hosts your container images and language packages next to your code, with permissions inherited from the repository. The **Marketplace** distributes tens of thousands of community actions, and first-party actions such as `actions/checkout`, `actions/cache`, and `actions/upload-artifact` cover the most common needs. On the security side, the platform provides the `GITHUB_TOKEN` with per-workflow permission scoping, OpenID Connect federation to cloud providers, and artifact attestations backed by Sigstore, all of which Part II treats in depth.

Two platform services deserve early attention because they shape workflow design. The **checks API** surfaces job results on pull requests, so CI outcomes become first-class conversational objects with re-run buttons and required-check semantics. And **environments** - named deployment targets with protection rules - turn deploy jobs into auditable, approval-gated events rather than bare shell scripts. You can ship a great deal of software using only these primitives plus plain shell.

## 1.4 How Actions Compares

Every team eventually asks whether to consolidate on Actions or run a dedicated CI system alongside GitHub. There is no universal answer, but honest comparison helps. Jenkins is unmatched in raw flexibility and plugin breadth, and remains the incumbent in large on-premise estates; the cost is that you operate it - controllers, agents, plugin CVEs, and Groovy pipelines that only one person understands. GitLab CI is an excellent, tightly integrated pipeline system, but it lives in GitLab, so using it means either migrating repositories or maintaining two collaboration surfaces. CircleCI offers fast, opinionated hosted builds with strong caching and an excellent orbs ecosystem, at a separate per-credit price. Azure DevOps Pipelines remains the standard in enterprises that live in Azure DevOps for boards and repos.

| Platform | Strengths | Costs / frictions | Sweet spot |
| -------- | -------------- | -------------- | -------------- |
| GitHub Actions | Native to GitHub; YAML workflows; huge Marketplace; OIDC and attestations built in; per-minute hosted runners | GitHub-bound; per-minute pricing on private repos; YAML sprawl without governance | Teams already on GitHub, OSS and enterprise alike |
| Jenkins | Fully self-hosted; infinite plugins; mature declarative pipelines; no per-minute fees | You own the servers, upgrades, and plugin security; dated UX; tribal Groovy knowledge | On-prem estates, exotic toolchains, strict data locality |
| GitLab CI | Unified with repos, MRs, and registries; strong runners; integrated security scanning | Requires GitLab as the SCM; feature depth varies by tier | Orgs standardized on GitLab |
| CircleCI | Fast, tuned build images; superior cache UX; test splitting built in | Separate vendor and bill; config DSL to learn; context limits | Performance-sensitive teams paying for speed |
| Azure DevOps | Deep Azure + enterprise integration; classic and YAML pipelines; agent pools | Heavier product surface; UX older; less GitHub-native | Microsoft-stack enterprises with existing ADO |

: Table 1.1 - GitHub Actions versus the established alternatives

The migration chapter (Chapter 14) returns to this comparison with concrete migration strategies. The short version: if your source code already lives on GitHub, Actions is usually the lowest-friction default, and its governance tools - organization-wide reusable workflows, allowed-action policies, and now lockfiles - close most of the control gaps that historically pushed enterprises toward self-managed Jenkins.

## 1.5 Costs and Quotas at a Glance

Actions bills hosted runner usage by the minute, with operating-system multipliers: Linux minutes cost 1x, Windows 2x, and macOS 10x. Every paid plan includes a monthly allowance of hosted minutes - 2,000 minutes on the Free plan, 3,000 on Pro and Team, and 50,000 on Enterprise Cloud - and usage beyond the allowance is billed per minute by product tier. Public repositories run free on standard hosted runners. **Larger runners** (4 to 64 vCPU Linux and Windows machines, with Apple-silicon macOS options) are billed separately at a higher per-minute rate and cannot be paid for with included minutes. Storage for artifacts and logs is billed separately with a per-repository default retention of 90 days.

::: {.warn}
**Watch out - self-hosted is no longer free on hosted GitHub**

Since March 1, 2026, self-hosted runner usage is metered at 0.002 dollars per minute, with a monthly free allowance (1,000 minutes for Free accounts, 3,000 for Team plans, 50,000 for Enterprise Cloud; GitHub Enterprise Server installations are exempt). A fleet of always-on self-hosted runners now has a real, growing line item. Chapter 13 covers metering, budgeting, and the optimization playbook in full.
:::

Quotas are the second cost surface. Concurrent jobs are capped by plan (20 on Free, 40 on Team, 180 on Enterprise Cloud for standard runners), a single job may run for at most 6 hours, and a workflow run is terminated after 35 hours. API rate limits for the `GITHUB_TOKEN` (1,000 requests per hour per repository) matter once you start automating through the REST API. These ceilings are generous for a small team and are exactly the numbers you must put in capacity spreadsheets for a large one.

## 1.6 When Actions Is the Wrong Tool

Choosing Actions is easy to justify, but three situations should give you pause. First, strict air-gapped environments: Actions is a hosted service, and while GitHub Enterprise Server supports Actions locally, running that well is a real platform-engineering commitment. Second, extremely long or stateful workloads: 6-hour job limits and ephemeral runners make Actions a poor batch scheduler, and systems designed for long-running computation will fit better. Third, teams whose release process requires deep, custom infrastructure control - dedicated bare-metal targets, mainframe integration, hardware-in-the-loop testing - often end up happier keeping that piece on dedicated tooling and letting Actions orchestrate the rest through APIs. Naming the failure modes up front is cheaper than discovering them in quarter three.

**See also:** [Chapter 2](#ch2) for the workflow file itself, [Chapter 9](#ch9) for where CI stops and delivery begins, and the *Docker for DevOps Engineers* volume for the images these pipelines build.
