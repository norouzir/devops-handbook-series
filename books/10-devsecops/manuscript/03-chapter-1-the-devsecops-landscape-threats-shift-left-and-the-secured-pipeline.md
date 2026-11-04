# Chapter 1 - The DevSecOps Landscape: Threats, Shift-Left, and the Secured Pipeline {#ch1}

## 1.1 What an Adversary Actually Wants

Before a single tool is installed, it pays to be honest about what is being defended and from whom. An adversary attacking a software delivery organization wants four things, roughly in order of preference: **credentials** (a long-lived token, a cloud key, a signing key - anything that makes the attacker indistinguishable from a legitimate workload), **a place to execute code** (a CI runner, a container registry, a Kubernetes cluster), **a path into the artifact** (a dependency, a base image, a build script - anything the pipeline will faithfully ship because it trusted something upstream), and **silence** (no log, no alert, no trace while persistence is established). Every chapter of this book is an answer to one of those four wants, and it is worth reading the table of contents that way.

The public record supplies the case studies, and four of them shape everything in this book. **SolarWinds (2020)** demonstrated supply-chain compromise at its worst: attackers planted a backdoor in the build process itself, and roughly 18,000 customers faithfully downloaded the trojanized update because the artifact was signed and delivered through the trusted channel - the pipeline itself became the weapon. **Codecov (2021)** demonstrated the credentials-first attack: a tampered bash uploader script exfiltrated CI environment variables, and the leaked tokens then opened the victims' own cloud environments. **Log4Shell (CVE-2021-44228, December 2021)** demonstrated that a dependency you did not know you had can be the vulnerability: millions of applications contained a critical remote code execution flaw in a transitive library, and the teams that recovered fastest were the ones who could answer "where do we use log4j?" from a generated list rather than from memory. Finally, the **XZ Utils backdoor (CVE-2024-3094, 2024)** demonstrated that even mature open-source communities can be socially engineered over years - which is why this book treats provenance and attestation, not vibes of trust, as the unit of supply-chain assurance.

::: {.note}
**Best practice - inventory first, tooling second**

Every incident above was worsened by an organization not knowing what it had: which repos held secrets, which images contained log4j, which pipeline had access to production. The first discipline of this book is that every asset is machine-listed - dependencies in a lockfile, images in a registry, secrets in Vault, access in an IAM policy - because you cannot defend, scan, or prove an inventory that exists only in people's heads. [Appendix A](#appA) maps every tool category to the asset it inventories.
:::

## 1.2 Shift-Left and the Cost Curve

**Shift-left** means moving security work earlier in the delivery timeline, and the justification is economics, not fashion. The industry-standard cost curve (quoted by NIST and IBM's annual breach reports in various forms) is that a defect found in design costs a rounding error, the same defect found in production costs one to two orders of magnitude more - in engineering hours, in incident response, and in the breach-notification machinery that follows. A hardcoded AWS key caught by a pre-commit hook costs the developer thirty seconds of embarrassment. The same key caught by an auditor costs a rotated key, a log review, a compliance finding, and possibly a public disclosure. The same key caught by an attacker costs the breach.

Shift-left has a second, less advertised benefit that matters more in practice: **feedback latency**. Security findings that arrive as a report weeks after the code was written are resented and deferred; findings that arrive as a red X on the pull request the developer just opened are fixed while the context is still loaded. This book's bias is therefore unapologetic: prefer checks that run on every commit and every pull request over checks that run quarterly, and prefer checks that fail a build over checks that file a ticket nobody owns. Where a check cannot fail the build (a scanner with noisy false positives, for example), [Chapter 7](#ch7) shows the intermediate discipline - gate on severity, report on the rest.

One caveat keeps the concept honest: shift-left does not mean "all security happens before release." Runtime detection ([Chapter 12](#ch12)) and incident response ([Chapter 13](#ch13)) exist precisely because some defects will ship anyway; defense in depth is the acceptance that every layer eventually fails. The mature formulation is *shift-left where you can, defend deep where you must*.

## 1.3 The Secured Pipeline Map

The running example is the same **shopnow** platform the series has carried since the Docker book: a containerized web service backed by a database, built by GitHub Actions, shipped to a registry, and run on Kubernetes. This book hardens that pipeline stage by stage, and each stage pairs a threat with a control:

| Stage | What can go wrong | Control (chapter) |
|---|---|---|
| Developer workstation | Secret committed to git history | Gitleaks + pre-commit ([Chapter 2](#ch2)) |
| CI platform | Over-privileged workflow, poisoned runner | Least-privilege GitHub Actions ([Chapter 3](#ch3)) |
| Source & dependencies | Vulnerable code, malicious package | Semgrep, Dependabot, SCA ([Chapter 4](#ch4)) |
| Image build | Bloated, CVE-laden base image | Minimal bases + Trivy ([Chapter 5](#ch5)) |
| Artifact publication | Tampered or unidentifiable artifact | Cosign signing, Syft SBOM, SLSA ([Chapter 6](#ch6)) |
| The build as a whole | One weak link silently bypassed | The assembled secured pipeline ([Chapter 7](#ch7)) |
| Admission | Non-compliant workload scheduled | Kyverno / Gatekeeper ([Chapter 8](#ch8)) |
| Runtime | Lateral movement, unexpected process | NetworkPolicy, Pod Security, Falco ([Chapter 9](#ch9)) |
| Infrastructure | Over-privileged IaC, open security groups | Trivy IaC, Checkov, least privilege ([Chapter 10](#ch10)) |
| The application | Injection, broken auth, XSS | OWASP Top 10, ZAP DAST ([Chapter 11](#ch11)) |
| Operations | Breach detected too late or never | Security telemetry ([Chapter 12](#ch12)) |
| When it fails | Chaos, slow recovery, repeat incident | Incident response, postmortems ([Chapter 13](#ch13)) |
| The auditors | Evidence collected by hand, once a year | Compliance as code ([Chapter 14](#ch14)) |

: Table 1.1 - The secured pipeline at a glance: threat, control, and where to find it

Two design principles govern the whole map. First, **every control is automated or it does not exist** - a checklist that depends on someone remembering is a wish, not a control, so everything in this book runs from a hook, a workflow, an admission policy, or a scheduled job. Second, **every control has a bypass story** - the book is explicit about what each layer assumes and what happens when that assumption fails, because that is the difference between security theater and engineering.

## 1.4 Threat Modeling in Ten Minutes

Before building controls, spend ten minutes per system doing what professional red teams do first: **threat modeling**. The lightweight version needs a whiteboard and four questions. *What are we building?* - a data-flow sketch with trust boundaries (browser, ingress, pods, database, third-party APIs). *What can go wrong?* - for each boundary, walk the **STRIDE** categories: Spoofing (can something pretend to be a legitimate caller?), Tampering (can data or artifacts be modified in transit or at rest?), Repudiation (can an action be denied for lack of logs?), Information disclosure (what reads that data?), Denial of service (what, if flooded, stops the business?), Elevation of privilege (can a low-identity become a high one?). *What will we do about it?* - either a control, an accepted risk, or a ticket with an owner. *Did we do a good enough job?* - the only honest test, which is why the Part II capstone ([Chapter 15](#ch15)) attacks the pipeline this book built.

::: {.warn}
**Watch out - the "we're too small to be a target" fallacy**

Automated attackers do not choose targets by revenue; they scan the whole internet for exposed secrets, open dashboards, and vulnerable versions, and they compromise the unlisted company as readily as the listed one. Most breaches in the public record were opportunistic, not targeted. Size changes your attacker's *effort*, never their *existence* - so the habits in this book scale from a two-person startup to an enterprise team by changing depth, not direction.
:::

**See also:** [Chapter 2](#ch2) starts the hands-on work with the controls that stop the most common breach vector - leaked credentials; [Chapter 7](#ch7) assembles Part I into one pipeline; [Chapter 15](#ch15) is where the map from Table 1.1 gets attacked end to end.
