# Chapter 9 - CI/CD to AWS with GitHub Actions {#ch9}

## 9.1 The Problem with Long-Lived Keys

The first generation of cloud CI worked like this: create an IAM user for the pipeline, mint an access key, paste the key into a GitHub secret, and hope nobody leaks it. The failure modes are documented in every breach postmortem since - credentials in build logs, in forks' PR runs, in a departed engineer's local clone - and they all stem from one design flaw: *a credential that never expires is a liability forever*. The modern pattern removes the stored credential entirely. GitHub's runners issue short-lived **OIDC tokens** (signed JWTs naming the repository, workflow, and branch); AWS trusts GitHub's token endpoint as an **OIDC identity provider**; and a role's trust policy admits only tokens whose claims match. The pipeline authenticates with proof of *where it is running*, receives credentials that expire within the hour, and the long-lived key disappears from the story. This chapter builds that pipeline end to end for the running example - build the image, push to ECR, deploy to EKS ([Chapter 7](#ch7)) - and adds the S3/CloudFront variant for the static tier ([Chapter 5](#ch5)). The workflow mechanics themselves are the *GitHub Actions for DevOps Engineers* volume's territory; here only the AWS side is new.

## 9.2 The Trust Setup: Identity Provider and Role

Two objects on the AWS side make federation work. First, GitHub's OIDC endpoint is registered once per account as an identity provider:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

Second, a role whose **trust policy** admits that provider *with conditions* - this is where the security lives, because without conditions any GitHub repository on the planet could assume the role:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:acme/shopnow:*"
      }
    }
  }]
}
```

The `sub` claim is the scoping surface: `repo:acme/shopnow:*` admits any workflow in that repository, and it deserves narrowing in practice - `repo:acme/shopnow:ref:refs/heads/main` admits only main-branch workflows, and GitHub *environments* add an `environment:production` stanza that pairs with protected-environment approvals below. One 2026 wrinkle matters when trust policies silently stop matching: repositories created after mid-July 2026 embed organization and repository identifiers in the `sub` claim (`repo:<org>/<repo>@<org-id>/<repo-id>:ref:...`), so a condition written for the old format needs the newer `StringLike` pattern - and the action's documentation owns the current canonical form. Scope the role's *permissions* policy as tightly as the job: ECR push on one repository, EKS describe and update on one cluster - never the admin umbrella.

## 9.3 The Workflow: Build, Push, Deploy

The pipeline that deploys the running example:

```yaml
name: deploy
on:
  push:
    branches: [main]
permissions:
  id-token: write      # the OIDC token - the only permission that matters here
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v6
        with:
          role-to-assume: arn:aws:iam::111122223333:role/shopnow-deploy
          aws-region: eu-central-1

      - name: Login to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push (arm64, for Graviton nodes)
        env:
          REGISTRY: ${{ steps.ecr.outputs.registry }}
        run: |
          docker buildx build \
            --platform linux/arm64 \
            -t "$REGISTRY/shopnow:${{ github.sha }}" \
            -t "$REGISTRY/shopnow:latest" \
            --push .

      - name: Deploy to EKS
        env:
          REGISTRY: ${{ steps.ecr.outputs.registry }}
        run: |
          aws eks update-kubeconfig --name shopnow --region eu-central-1
          kubectl set image deployment/shopnow-web \
            web="$REGISTRY/shopnow:${{ github.sha }}"
          kubectl rollout status deployment/shopnow-web --timeout=180s
```

Five details carry the chapter. `id-token: write` is the permission that mints the OIDC token - without it the action falls back to asking for stored keys, which is the design working as intended. `configure-aws-credentials@v6` exchanges the token for role credentials and exports them for every later step; nothing else in the workflow holds a secret. The image is tagged with the commit SHA - *immutable deploys*, since `latest` explains nothing at 2 a.m. - and built for `linux/arm64` because the [Chapter 7](#ch7) nodes are Graviton. `kubectl set image` + `rollout status` is a minimal imperative deploy: honest and sufficient here, with the GitOps alternative (Argo CD, Flux) as the standard next step when the team wants *reconciliation* rather than *pushing*. And `rollout status --timeout` makes a bad deploy *fail the pipeline* instead of failing silently.

## 9.4 The Static Tier: S3 Sync and CloudFront Invalidation

The static assets from [Chapter 5](#ch5) deploy with a lighter pipeline step in the same workflow:

```yaml
      - name: Deploy static assets
        run: |
          aws s3 sync ./site s3://shopnow-assets-eu-central-1-prod/site --delete
          aws cloudfront create-invalidation \
            --distribution-id E1234ABC \
            --paths "/site/*"
```

`sync --delete` makes the bucket mirror the build; the **CloudFront invalidation** clears the CDN's cached copies so users see the new content immediately (invalidations cost after the free monthly allowance - path-scoped patterns like `/site/*` keep the count sane). With versioned filenames (`app.a1b2c3.js`), the invalidation step disappears because new URLs never hit stale cache - the professional pattern, and a nice example of letting naming discipline delete an operational step.

## 9.5 Environments, Approvals, and Scoping

GitHub **environments** are the bridge between the platform's rules and the pipeline's: an environment named `production` can require reviewer approval, restrict to protected branches, and gate on deployment status - all enforced by GitHub before the job runs, which pairs exactly with the per-environment trust stanzas from Section 9.2 and with separate AWS roles per environment (`shopnow-deploy-dev` cannot touch prod because *its role* cannot, not because a human remembered to check). The same principle scales through the platform: one role per workflow per environment, each with a permissions policy that would embarrass no auditor, and the [Chapter 2](#ch2) Access Analyzer reviewing the set monthly.

::: {.note}
**Best practice - make the rollback command the deploy command's twin**

Every deploy mechanism here has a one-line rollback, and the runbook should print both side by side. `kubectl rollout undo deployment/shopnow-web` walks the ReplicaSet history; for S3 syncs, the previous artifacts directory (or S3 versioning from Section 5.4) is the twin. The test: at 2 a.m., the on-call engineer should never need to *design* a rollback - only to run the one next to the deploy.
:::

## 9.6 Lab 5: A Pipeline with No Stored Credentials

::: {.lab}
### Lab 5 - OIDC Pipeline End to End {#lab5}

1. Set up the trust: create the OIDC provider (Section 9.2), a `shopnow-deploy` role with a `repo:<you>/shopnow:*` condition, and a permissions policy covering ECR push on one repository plus EKS describe/update on your cluster. Keep the policy JSON in the repo - it is documentation.
2. Write the workflow of Section 9.3 into the repository. Run it on a push and watch each step: confirm the credentials step logs `Assuming role with OIDC` and that no AWS secret exists anywhere in the repository settings.
3. Negative test: open the trust policy, change the `sub` condition to `repo:acme/other-repo:*`, re-run, and read the exact failure (`Not authorized to perform sts:AssumeRoleWithWebIdentity`). Restore the condition. That error text is [Appendix C](#appC)'s entry on this exact failure.
4. Add the `production` environment with a required reviewer, and verify the run pauses for approval before deploying. Observe the `environment:production` stanza appear in the token's `sub` (visible in the action's debug output).
5. Break-glass drill: intentionally deploy a broken image tag (point the deployment at a tag that does not exist), watch `rollout status` fail the pipeline, then run `kubectl rollout undo` and confirm the previous image is serving. That drill is the rollback promise of Section 9.5, tested.
6. Cleanup: the role and provider are the kind of infrastructure worth keeping; do delete the workflow's `latest` tag habit if you added one, and confirm no access keys were created at any point (`aws iam list-users` should show none for this pipeline).

Deliverable: a repository whose push-to-main deploys to EKS with zero stored AWS credentials, a reviewer gate, and a rehearsed rollback - the same shape scales from this lab to real platforms with only the role policies changing.
:::

**See also:** [Chapter 10](#ch10) wires the deploy's aftermath into alarms, [Chapter 11](#ch11) puts the trust policy and role itself under Terraform, and the *GitHub Actions for DevOps Engineers* volume owns the workflow-language details this chapter assumed.
