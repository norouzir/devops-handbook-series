# Chapter 14 - Compliance as Code: CIS Benchmarks and Automated Evidence {#ch14}

## 14.1 What Auditors Actually Want

Compliance has a reputation as a paperwork tax because the traditional way to satisfy it is an annual scramble: screenshots collected by hand, spreadsheets of "who has access," policies printed for signatures - a snapshot that begins aging the moment it is taken. The DevSecOps answer is **continuous compliance**: the controls this book built are already machine-checkable, so the evidence of compliance is a *query* rather than a project. An auditor's real questions are short and reasonable - *show me that secrets are managed, that changes are reviewed, that access is least-privilege, that you detect and respond* - and every one of them maps to an artifact this series already produces: Vault policies and audit logs ([Chapter 2](#ch2)), branch protection and required reviews ([Chapter 3](#ch3)), IAM grown from denied attempts ([Chapter 10](#ch10)), the incident runbook and postmortem archive ([Chapter 13](#ch13)). The work of this chapter is wiring those artifacts into a standing, automated evidence base - the same shift from manual to pipeline that everything else in the series went through.

## 14.2 CIS Benchmarks and kube-bench

The **CIS Benchmarks** are the industry's consensus hardening checklists, published per technology: Kubernetes, Docker, each cloud's foundational security benchmark, PostgreSQL, nginx. Each benchmark is a numbered set of controls with an audit procedure and a remediation ("2.2.5 - Ensure that the API server `--audit-log-path` argument is set", "5.3.2 - Ensure that only trusted registry images are used"). They are the natural answer to "harden the cluster" because they are specific, prioritized, and machine-checkable - and **kube-bench** is the open-source tool that runs the Kubernetes benchmark's checks against a real cluster and prints pass/fail per control:

```bash
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml
kubectl logs -n kube-bench job.batch/kube-bench | tail -40
# [PASS] 1.2.15 Ensure that the --audit-log-path argument is set
# [FAIL] 4.2.2 Ensure that the --rotate-certificates argument is not set to false
```

The honest interpretation of a first run: dozens of PASS lines (the managed control plane handles most node-security controls automatically - one of the quiet arguments for AKS/GKE/EKS), a handful of actionable FAILs, and a few findings that a managed service makes structurally unfixable by the customer. The workflow mirrors [Chapter 8](#ch8)'s policy rollout: run it, triage the failures into *fix*, *compensate*, or *accept-with-reason*, fix the fixable ones as IaC changes ([Chapter 10](#ch10) - the cluster is Terraform, so the remediation is a diff), and schedule kube-bench so drift reappears as a fresh FAIL rather than a finding next audit season. Trivy's kubernetes subcommand overlaps happily with kube-bench for the CIS checks and adds its own scanning, so the same tool family from [Chapter 5](#ch5) covers this ground too.

## 14.3 Mapping Controls to Frameworks

SOC 2, ISO 27001, PCI-DSS, and friends read like different vocabularies for one small set of underlying questions, and the mapping effort is a one-time exercise that pays off for every framework after the first. The working table for `shopnow` - one control, the implementing mechanism, the *automated* evidence:

| Framework question | Implementing control | Automated evidence |
|---|---|---|
| Are secrets managed and rotated? | Vault policies, dynamic DB creds ([Chapter 2](#ch2)) | Vault policy objects, lease/audit log queries |
| Are changes reviewed before deploy? | Branch protection, environments ([Chapter 3](#ch3)) | GitHub ruleset config, merged-PR audit export |
| Is code/artifact integrity verified? | Scanning + signing + admission ([Chapter 6](#ch6), [Chapter 8](#ch8)) | Policy reports, cosign verify logs, scan history |
| Is access least-privilege? | IAM process, RBAC, SSO ([Chapter 10](#ch10), [Chapter 9](#ch9)) | Access-analyzer findings, RBAC dump with owners |
| Are incidents detected and handled? | Telemetry + runbooks ([Chapter 12](#ch12), [Chapter 13](#ch13)) | Alert-to-triage metrics, postmortem archive |
| Is the platform hardened to a baseline? | CIS via kube-bench + IaC (this chapter) | Scheduled kube-bench results in the log store |

: Table 14.1 - Control-to-framework mapping for `shopnow`: the auditor's questions, the mechanisms, and where the evidence lives

The mapping table *is* the compliance artifact - auditors accept a system that demonstrably checks itself, and the table tells them exactly where to look. New framework requirements arrive as new rows, not new projects.

## 14.4 Automating the Evidence Base

The last mile is making the evidence collection itself a scheduled pipeline, which is just the series' cron-workflow pattern applied to compliance:

```yaml
# .github/workflows/compliance-evidence.yml (scheduled)
on:
  schedule:
    - cron: "0 6 * * 1"      # Mondays, 06:00 UTC
jobs:
  collect:
    runs-on: ubuntu-latest
    permissions: { id-token: write, contents: read }
    steps:
      - name: kube-bench snapshot
        run: ./scripts/kube-bench-collect.sh >> evidence/$(date +%F)-kube-bench.txt
      - name: Kyverno policy reports
        run: kubectl get policyreports -A -o json > evidence/$(date +%F)-admission.json
      - name: Access review (RBAC + cloud IAM)
        run: ./scripts/access-review.sh > evidence/$(date +%F)-access.csv
      - name: Publish to the evidence store
        run: ./scripts/evidence-upload.sh   # versioned, access-logged, WORM-ish
```

Every Monday the pipeline re-proves the platform to itself: benchmarks pass, admission policies are still Enforce, the access review runs with owners attached, and the artifacts land in append-only storage. The human cadence that remains is small and high-value: the quarterly access review (each binding confirmed by its owner, or removed), and the annual refresh of the control-mapping table. Everything else the auditor asks for is a link to a query result - which is the quiet endgame of this whole book: a platform where *compliant* is not a season, it is a property of the pipelines.

**See also:** [Chapter 15](#ch15) attacks the platform this chapter just certified; [Chapter 16](#ch16) turns the controls into an organizational roadmap; the CIS Benchmarks' own documentation owns the per-technology control details.
