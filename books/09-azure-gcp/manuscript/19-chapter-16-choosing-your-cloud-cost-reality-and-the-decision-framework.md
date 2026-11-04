# Chapter 16 - Choosing Your Cloud: Cost Reality and the Decision Framework {#ch16}

## 16.1 Gravity: The Decision You Usually Already Made

Most cloud choices are not choices; they are recognitions. An organization that lives in Microsoft 365, Entra ID, and System Center has chosen Azure the way water chooses downhill - the identity plane, the licensing agreements, and the desktop fleet already point there. A company whose center of mass is data engineering, BigQuery-shaped analytics, or a Kubernetes-first platform team leans Google Cloud because the platform's best products point the same way. And the team that needs the broadest catalog, the deepest third-party integrations, and the largest hiring pool usually lands on AWS, which is where this series started for exactly that reason. The decision framework in this chapter exists for the minority of cases where gravity is genuinely ambiguous - and, just as importantly, to give the majority a defensible record of *why the obvious answer was obvious*.

## 16.2 Skills and the Convergence Story

The delta this book opened with is smaller than it was five years ago, and the convergence has a name list: Kubernetes on all three ([Chapter 5](#ch5), [Chapter 12](#ch12)), OCI images everywhere, OpenTelemetry feeding every monitoring stack, and OIDC federation as the only CI credential model worth teaching ([Chapter 7](#ch7), [Chapter 14](#ch14)). What still differs is *operational habit* - the IAM dialects of [Chapter 15](#ch15), the network models, the CLI muscle memory - and habits cost real hours during incidents, which is the strongest argument for *depth on one cloud* over equality on three. The practical hiring note: engineers strong on any one hyperscaler reach competence on a second in weeks with a book like this one, because the concepts transferred; what they need is the mapping and the deliberate practice, not a bootcamp.

## 16.3 Price: Method Over Numbers

Any price table in a book is wrong within a year, so this section teaches the method instead. **Model the workload, not the instance list**: pick the three-month steady state (vCPU-hours, storage GB-months, egress GB, request counts) and price *that* in each cloud's calculator - the catalogs differ too much for a per-unit comparison to mean anything. **Include the fixed fees**: EKS's per-cluster control-plane charge, AKS's free-tier ceiling and Standard SLA fee, GKE's Autopilot management fee, support plans, and the load balancers and NAT that the happy-path tutorial forgets. **Discount instruments differ**: AWS Savings Plans and RIs, Azure Reservations and savings plans, GCP Committed Use Discounts - all roughly comparable on compute, none comparable on serverless, where the discount story mostly does not exist. **Egress is the tiebreaker that breaks ties** ([Chapter 15](#ch15)): price the inter-cloud links if any architecture sketch has them. And **run the capstone**: one evening of real deployments ([Lab 6](#ch15)) produces a steady-state cost number per cloud that no calculator disputes, because it is measured, not modeled.

::: {.note}
**Best practice - a one-week benchmark beats a spreadsheet, and a spreadsheet still comes first**

The sequence that works: spreadsheet the steady state (an hour), then run the *actual* application on each candidate for a week at representative traffic with billing exports on, then compare the real bills to the spreadsheet and interrogate every gap. The gaps are the curriculum: they show you which services the application leaned on that the model missed - usually a managed queue, a DNS zone, or log ingestion nobody priced.
:::

## 16.4 Service-Specific Captures

Beyond gravity and price, three honest captures tip specific workloads. **GKE Autopilot and Cloud Run** are the best managed-container pair on any cloud ([Chapter 12](#ch12), [Chapter 13](#ch13)) - if the platform strategy is "Kubernetes without a platform team" or "containers without a cluster," GCP's implementations lead. **Entra integration** is Azure's capture: workloads whose identity, compliance, and desktop estate are Microsoft-shaped inherit SSO, conditional access, and governance that no other cloud matches at that depth ([Chapter 2](#ch2)). And **AWS breadth** remains real: the long tail of managed services, the marketplace, and the community answer-base mean the strange requirement is more likely to have a managed product on AWS than anywhere else - the reason the series began there. Sovereign and compliance requirements (EU data boundary postures, government regions, sector-specific attestations) are the fourth capture, and they outrank every consideration above when they apply.

## 16.5 Multi-Cloud: The Honest Conversation

The capstone's evening ([Chapter 15](#ch15)) is also the anti-hype evidence. Multi-cloud is *right* in four situations: after an acquisition that brings a second estate; when a sovereign or regulatory requirement demands a specific provider for a specific workload; when one cloud's unique service genuinely captures the business (and the data gravity rule of [Section 15.4](#ch15) is respected); and as an exit-risk posture *implemented at the portable layers* - containers, Kubernetes, Terraform, OpenTelemetry - rather than as duplicated everything. It is *wrong* when the motivation is negotiation leverage (the discount you win is smaller than the second platform team you hire), resilience theater (regional HA inside one cloud delivers more availability per dollar than two clouds - the outage domains do not care about your vendor list), or résumé-driven engineering. The portable-layer posture is the one this series equips: the same containers, the same manifests with three annotations, the same pipeline shape with three deploy steps - which is exactly the delta a two-cloud future needs, and exactly what the duplicated-platform posture never achieves.

## 16.6 The Decision Framework

Bring it together as a scored record - weight the criteria for *your* organization, score each cloud honestly, and let the output be a document rather than a debate:

| Criterion | Weight (example) | AWS | Azure | GCP |
| --- | --- | --- | --- | --- |
| Existing estate gravity (identity, licensing, data) | 30 | 4 | 5 | 3 |
| Service fit for the workload's hard requirements | 25 | 5 | 4 | 4 |
| Team skills and hiring pool | 15 | 5 | 4 | 3 |
| Modeled + measured cost at steady state | 20 | 4 | 4 | 4 |
| Sovereignty / compliance posture | 10 | 4 | 5 | 4 |
| **Weighted total** | | **4.4** | **4.4** | **3.6** |

The example numbers are the point: a Microsoft-shaped organization scores Azure ahead on gravity and sovereignty, the compute score ties because converged platforms tie, and the honest conclusion - *one primary cloud, deep; the portable layers maintained; a second cloud only when a capture is real* - survives any reasonable weighting. Write the scores down with the capstone's measured numbers attached, and the next "should we move to X?" conversation starts from a record instead of a rumor.

::: {.warn}
**Watch out - a decision framework is a decision, not a hedge**

A scored evaluation that ends in "all three, a little" has failed its purpose: three shallow platforms cost more than one deep one in every currency this book has counted - incidents, hiring, bills, and the pager. Run the framework, commit to the primary, keep the capstone's portable layers as insurance, and revisit on a schedule (or when a capture appears), not after every keynote.
:::

**See also:** [Appendix A](#appA) is the service map the whole decision leans on, [Chapter 15](#ch15) is the measurement chapter, and the *Terraform for DevOps Engineers* volume owns the cross-cloud IaC layer this chapter's insurance policy is written on.
