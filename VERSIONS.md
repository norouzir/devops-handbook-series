# Verified versions

Every volume states in its preface which releases it was checked against. This file collects
them in one place so a future revision knows exactly what to re-verify, and so a reader can tell
at a glance whether their environment matches the book.

**Content date for all ten volumes: October 2026.**

| # | Volume | Pinned to | Re-check first |
|---|--------|-----------|----------------|
| 1 | Docker | Docker Engine v29, Docker Desktop 4.97, Compose v2 plugin, BuildKit/buildx | Docker Engine minor releases (twice a year) |
| 2 | Kubernetes | Kubernetes v1.37 (v1.35 and v1.36 inside their support windows), kind, kubeadm, Helm 4, Kustomize | Kubernetes minors (three per year), Helm majors |
| 3 | GitHub Actions | Node 24 action runtime (default since 2026-06-16, Node 20 removed 2026-09-23), workflow dependency lockfiles (GA 2026-10-28), Actions Runner Controller 0.15.0 | Runner image rotation, action major versions |
| 4 | Ansible | ansible-core 2.21.5, Ansible community package 14, execution environments, AWX | ansible-core minors (roughly every six months) |
| 5 | Terraform | Terraform 1.17.0 (2026-10-21), Terraform Policy GA, HCP Terraform, OpenTofu 1.13 | Terraform minors, provider majors |
| 6 | Prometheus & Grafana | Prometheus 3.15, Alertmanager 0.34, Grafana 13.3, node_exporter 1.12, Grafana Mimir 3.2 | Grafana and Prometheus minors |
| 7 | Elastic Stack | Elasticsearch 9.5, Kibana 9.5, Logstash 9.5 (8.19 branch still maintained for upgrades) | Elastic minor releases |
| 8 | AWS | AWS CLI v2, Amazon Linux 2023, Graviton (arm64) defaults, IMDSv2, `aws-actions/configure-aws-credentials` v6, GitHub OIDC `sub` claim change | Service quotas and Free Tier numbers (continuous) |
| 9 | Azure & GCP | `az` CLI 2.x with bundled Bicep, `azure/login` v3, `google-github-actions/auth` v3, `actions/checkout` v7, AKS N-2 policy, GKE Autopilot, Cloud Run, Artifact Registry | CLI majors, GitHub OIDC `sub` claim change |
| 10 | DevSecOps | gitleaks v8, Semgrep 1.x, Trivy 0.6x, Cosign v2, Syft 1.x, Kyverno 1.1x, OPA Gatekeeper v3, OWASP ZAP 2.1x, Falco, kube-bench 0.1x, `actions/checkout` v7 | Scanner 0.x minors (fast movers) |

## Re-verification policy

1. Pick one volume per revision; do not re-verify the series in one pass.
2. Check the **Re-check first** column, then read the volume's preface paragraph beginning
   "The content reflects…" — it is the authoritative list of what that book pins.
3. Update the preface, this table, and `build/metadata.yaml` (`date:`) together. A version bump
   that touches only one of the three is how the series goes out of sync.
4. Anything describing a preview or alpha feature must say so; the chapters already distinguish
   stability levels, and that distinction is the first thing to decay.

The build toolchain is versioned separately: Pandoc ≥ 2.19 (the defaults files use
`embed-resources`) and WeasyPrint for the PDF. Neither is pinned to a minor release.
