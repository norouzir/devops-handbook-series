# Appendix A - The Security Tool Map: Categories and Choices {#appA}

Security tooling is a landscape, not a shopping list, and the fastest way to get lost is evaluating tools before fixing the categories. This appendix maps the categories this book used to the open-source tools that anchor each one, with the series' pick marked and the credible alternatives named. Every category is defined by the question it answers, because the question is what survives tool churn.

| Category (the question) | Series pick | Credible alternatives |
|---|---|---|
| Secrets detection - *did a credential get committed?* | **Gitleaks v8** | TruffleHog, Trivy (secret mode), git-secrets |
| Secrets platform - *where do credentials live and expire?* | **HashiCorp Vault** | Cloud-native secret managers (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager), OpenBao (Vault's open-source fork), Infisical |
| SAST - *is there a vulnerability pattern in our code?* | **Semgrep** + GitHub CodeQL | SonarQube, Brakeman (Rails), bandit (Python) |
| SCA / dependency scanning - *is a dependency known-bad?* | **Dependabot** (GitHub-native) | Renovate, Trivy (fs mode), Snyk, OWASP Dependency-Check |
| Container image scanning - *what CVEs ride in the image?* | **Trivy** | Grype, Docker Scout, Clair |
| Artifact signing - *can we prove who built this?* | **Cosign** (Sigstore) | Notation/Notary v2, in-toto attestations, GPG (legacy) |
| SBOM generation - *what exactly is inside the artifact?* | **Syft** | Trivy (sbom mode), CycloneDX generators |
| Provenance / build attestation - *which build made this?* | **GitHub artifact attestations** (SLSA) | in-toto, SLSAcommunity tools, Tekton Chains |
| Admission policy - *can a non-compliant workload start at all?* | **Kyverno** | OPA Gatekeeper, Kubernetes Pod Security Admission, VPA/labels-native controls |
| IaC scanning - *is the infrastructure code compliant?* | **Trivy (config) + Checkov** | tfsec (merged into Trivy), terrascan, KICS |
| DAST - *does the running app misbehave?* | **OWASP ZAP** | Nuclei, Burp Suite Enterprise (commercial) |
| Runtime detection - *is a running process doing something abnormal?* | **Falco** | Tetragon, Sysdig Secure (commercial), Aqua (commercial) |
| Benchmark / hardening audit - *does the platform meet the baseline?* | **kube-bench** (CIS) | Trivy (kubernetes mode), cloud-native posture tools |
| CI hardening - *is the pipeline itself a smaller target?* | **GitHub hardening settings + StepSecurity harden-runner** | GitLab hardening guides, self-hosted runner isolation patterns |

: Table A.1 - The security tool map: category, question, and the open-source anchors

Three reading notes on the map. First, **Trivy appears in four categories on purpose** - image, filesystem/dependency, IaC, and Kubernetes scanning in one binary - and that consolidation is exactly why the series standardized on it: fewer databases to keep current, one `.trivyignore` convention, one gate pattern. Second, the **cloud-native secret managers** are legitimate competitors to Vault and the right answer for some teams; the series still teaches Vault because its dynamic secrets, lease model, and OIDC auth are portable across the three clouds the series covers, and because a single secrets interface beats three when the pipeline deploys to all of them. Third, **categories, not tools, are the commitment**: swapping Grype for Trivy is an afternoon; leaving the "is the image clean?" question unanswered is the incident. When you evaluate a tool not on this list, fit it into a category first - and if it fits no category, be suspicious of the problem it is solving.

The companion map to keep in mind is *this series' own books*: this volume's chapters deliberately reuse each prior book as infrastructure - scanners ride the GitHub Actions book's workflows, admission rides the Kubernetes book's manifests, telemetry rides the observability books' pipelines, and the cloud books' OIDC federation is the credential spine. When you add a security tool later, add it the same way: as a gate or a sensor inside the pipeline and platform that already exist.

**See also:** [Chapter 1](#ch1) for the threat model that orders these categories; [Appendix B](#appB) for the command-level reference for the series' picks.
