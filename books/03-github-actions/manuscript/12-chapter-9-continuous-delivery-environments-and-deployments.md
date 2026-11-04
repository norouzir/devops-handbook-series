# Chapter 9 - Continuous Delivery: Environments and Deployments {#ch9}

## 9.1 Environments: Named Deployment Targets

An environment is a named deployment target - `staging`, `production`, `eu-cluster` - that a job references with `environment:`. Jobs targeting an environment acquire its protection rules before any step executes, its secrets and variables take precedence over repository-level ones, and the run's deployment history is recorded on the repository's Environments page. Environments turn deployment from 'a job that happens to kubectl apply' into a first-class platform object with its own access control, its own credentials, and its own audit trail - the difference matters most in organizations where the people who write CI are not the people authorized to touch production.

Three protection rules ship with the platform. **Required reviewers** pause the job until named users or teams approve it - the approval appears as a button on the run, and the reviewer sees the environment, ref, and commit before approving. **Wait timer** inserts a fixed delay (up to 43,200 minutes), useful as a soak period after staging deploy. **Deployment branch and tag policies** restrict which refs may deploy to the environment at all - `main` only for production, release tags only for the hotfix channel. Custom protection rules (a webhook-driven gate you host) complete the set for organizations that must consult external systems - change-management tickets, SLA checks - before release.

```
deploy-production:
  needs: deploy-staging
  runs-on: ubuntu-latest
  environment:
    name: production
    url: https://app.example.com
  concurrency:
    group: cd-production
    cancel-in-progress: false
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/deploy
      with:
        environment: production
        image_digest: ${{ needs.deploy-staging.outputs.image_digest }}
```

## 9.2 Environment Secrets and Configuration

Environment-scoped secrets are the correct home for credentials that only production or staging should hold, because a workflow that never targets the environment can never read them - the protection rules gate the secret read as well as the deployment. This yields a clean privilege geometry: repository secrets for build-time credentials shared by all workflows, environment secrets for deploy-time credentials per target, and organization secrets (with selected-repository access) for platform-wide values. The same precedence applies to configuration variables, which keeps per-environment endpoints and flags out of workflow YAML entirely.

::: {.note}
**Best practice - no production secrets at repository scope**

Audit your repository settings for secrets that exist only to serve production deploys. If a secret is only needed by jobs that target the production environment, delete it from repository scope and recreate it in the environment. The blast radius of a leaked workflow token then stops at staging.
:::

## 9.3 The Deployments API and Rollbacks

Behind the UI, every environment job emits records through the Deployments API: a `deployment` is created for the ref, `deployment_status` events mark `pending`, `in_progress`, `success`, and `failure`, and the `deployment_status` webhook lets external systems react. Setting the environment's `url:` makes the deployment record link to the deployed instance, which is what status badges and dashboards consume. This history is the substrate for pragmatic rollback policy: because promotion is by immutable digest (Chapter 8), a rollback is a new deployment of the previous digest through the same approved pipeline - not an unreviewed `kubectl rollout undo` typed by whoever is awake. Teams that need automatic rollback wrap the deploy step with a health-check-and-revert script and let the API record both attempts.

## 9.4 A Staged Delivery Pipeline

The shape that covers most services: CI builds and tests on every pull request; a merge to `main` builds once more, pushes an immutable image, and deploys to `staging` automatically; integration or smoke suites run against staging; and `production` requires the same image plus a human approval plus (optionally) a wait timer. The production job consumes the staging job's output digest, so approval gates a promotion, not a rebuild. This is the pattern the lab below implements end to end, and Chapter 12 replaces its long-lived cloud credentials with OIDC federation.

::: {.lab}
### Lab 3 - Staged Deployment with Approval Gates {#lab3}

1. In your sample repository, create two environments: `staging` (branch policy: `main` only) and `production` (branch policy: `main` only, required reviewer: yourself).
2. Add a `deploy-staging` job targeting the `staging` environment that deploys an image built earlier in the workflow; set the environment `url` and confirm it appears on the run.
3. Add a smoke-test job that runs after staging and uploads its report as an artifact; make `deploy-production` depend on it.
4. Target `production` with `environment: production`, `concurrency: cd-production`, and prove the run pauses at the approval gate; approve from a different account if possible and record the deployment status history.
5. Attempt to deploy a non-`main` branch to production and confirm the branch policy rejects it before any step runs.
6. Simulate rollback: redeploy the previous image digest through the same workflow and verify the Environments page shows both deployment statuses in order.
:::

**See also:** [Chapter 10](#ch10) for the workflow structure repeated deployments deserve, [Chapter 11](#ch11) for network paths only self-hosted runners can reach.
