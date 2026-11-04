# Chapter 10 - Infrastructure as Code Security: Trivy, Checkov, and Least Privilege {#ch10}

## 10.1 IaC Is the Credential-Bearing Configuration

By the time the Terraform book was done, `shopnow`'s entire infrastructure - VPC, cluster, database, IAM - existed as code that applies in minutes. This chapter states the uncomfortable corollary: **the code is now the security posture**. A security group rule of `0.0.0.0/0` on port 5432, an S3 bucket without encryption, an IAM role with `"Action": "*"` - these are no longer console mistakes someone made at 2 a.m.; they are lines in `main.tf`, reviewed in pull requests, applied by CI, and *guaranteed to exist exactly as written*. The upside is the same as it was for application code: posture becomes reviewable, scannable, testable, and revertible. The discipline of this chapter is to put infrastructure through the same gates [Chapter 7](#ch7) put the image through - scan on every pull request, fail on critical findings, and let the pipeline be the only writer.

## 10.2 Scanning IaC: Trivy config and Checkov

The same Trivy binary from [Chapter 5](#ch5) scans infrastructure definitions via its `config` subcommand - Terraform, CloudFormation, Kubernetes manifests, Dockerfiles - against hundreds of built-in checks. **Checkov** (Prisma/PerimeterX's open-source scanner) is the other standard engine, with the widest policy coverage for Terraform specifically and graph-based checks that follow values across modules:

```bash
trivy config --severity HIGH,CRITICAL --exit-code 1 infra/
checkov -d infra/ --framework terraform --hard-fail-on CRITICAL
checkov -d infra/ --skip-check CKV_AWS_20   # explicit, commented suppression
```

Run against the cloud books' `shopnow` stacks, the scanners light up the canonical findings, and every one of them is a real breach pattern: security groups open to the world on database ports; RDS or Cloud SQL instances with public IPs; S3 buckets and disk volumes without encryption or with versioning off; IAM roles with wildcard actions; EKS/GKE node pools without private endpoints. The output is the useful kind - check ID, resource address, the offending line, and the compliant fix - which makes the scanner a teaching tool as much as a gate. Suppressions are explicit (`--skip-check` with the ID in the CI config, or an inline comment holding a reason and review date), so an accepted risk is a reviewed artifact, exactly as with `.trivyignore` in [Chapter 5](#ch5).

::: {.note}
**Best practice - gate on plan, not just source**

Scanning `.tf` source catches the static cases; the sharper gate scans the **plan** (`terraform plan -out=tfplan && checkov -f tfplan --framework terraform_plan`), because the plan is the resolved truth - variables substituted, modules expanded, the actual change about to be applied. A policy that reads "no resource may be created with a public IP" is ambiguous in source when the value comes from a variable and unambiguous in a plan. The Terraform book's CI chapter built the plan-prerequisite pipeline; this chapter adds the scanner as a second, parallel job on the same artifact.
:::

## 10.3 Least Privilege for Workloads: The IAM Endgame

Wildcard-action roles pass scanners more often than they should (the check flags `"*"` but `"s3:*"` on `"*"` resources in a module deep in the tree is the same disaster with better manners), so least privilege deserves its own workflow rather than a single check. The working method for `shopnow`: start from **zero** and grant on evidence - the workload fails with `AccessDenied`, the access-denied log line (CloudTrail or cloud audit logs) names the exact action and resource, and the policy grows by one precise statement. Both AWS IAM Access Analyzer and the equivalent Azure/GCP policy analyzers generate findings that convert directly into scoping work: unused permissions, public exposure, cross-account trust worth re-examining. The cloud books built each platform's IAM model; this chapter's contribution is the *process* - roles are grown from denied attempts and pruned by analyzer findings on a schedule, never cloned from the last role and widened to stop the friction.

Two IAM rules carry most of the weight in practice. **No long-lived credentials for workloads**: the cloud books' OIDC federation pattern (GitHub Actions to cloud, Vault dynamic credentials from [Chapter 2](#ch2)) means CI and workloads hold no static keys to rotate or leak - where a static key survives, it belongs in Vault with a rotation schedule, not in a variable file. **Boundaries on the writers**: the role that runs `terraform apply` is itself the most privileged identity in the organization, so it gets a permissions boundary (it may create resources, but it may not create `*` admin roles), its use is logged to the audit stream of [Chapter 12](#ch12), and human access rides the same break-glass and review patterns as the production database.

## 10.4 State: The File That Is Also a Secret Store

One IaC artifact deserves a security chapter of its own: **state**. Terraform state files contain resource attributes verbatim - database passwords, generated secrets, connection strings - which makes every `.tfstate` a credentials file regardless of what the code says. The controls are quick to state because the Terraform book built them: remote backends only (local state on a laptop is an incident), the backend's storage encrypted at rest and access-logged, state locking enabled, and the plan/apply artifacts in CI treated as sensitive outputs rather than pipeline logs to be browsed. The `sensitive = true` marking keeps secrets out of *logs*; only the encrypted backend keeps them out of *files*. One more habit closes the loop: state snapshots retained per apply (versioned bucket or equivalent) mean a bad apply - or a bad actor with the apply role - is a revert, not a rebuild.

## 10.5 The IaC Gate in CI

The assembled gate slots into the pipeline from [Chapter 7](#ch7) as one job, parallel to the image build:

```yaml
  infra-gates:
    runs-on: ubuntu-latest
    permissions: { contents: read, id-token: write }
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v7.0.0
      - run: terraform -chdir=infra init -backend=false
      - run: terraform -chdir=infra plan -out=tfplan
      - name: Static + plan scans
        run: |
          trivy config --severity HIGH,CRITICAL --exit-code 1 infra/
          checkov -f tfplan --framework terraform_plan --hard-fail-on CRITICAL
      - name: Apply (OIDC role, audited)
        if: github.ref == 'refs/heads/main'
        run: terraform -chdir=infra apply -auto-approve tfplan
```

Static scan, plan scan, then apply from the reviewed plan under an OIDC-assumed role - the infrastructure equivalent of test, scan, sign, deploy. Combined with the cloud books' drift detection (`terraform plan` on a schedule reporting drift without applying), the posture stays *as reviewed*: not just hardened once, but continuously reconciled against its definition.

**See also:** [Chapter 11](#ch11) moves from infrastructure to the application itself; the Terraform book's chapters 10 and 11 remain the full reference for state management and policy-as-code frameworks; [Appendix B](#appB) holds the scanner commands.
