# Chapter 15 - The Capstone: A Red-Team Drill Against the Secured Pipeline {#ch15}

## 15.1 The Drill: Attack Your Own Pipeline

Parts I and II built a defense in layers: hooks and scanners at the source, gates in the pipeline, admission policies in the cluster, detection on the nodes, and a runbook for when a page arrives. A defense that has never been attacked is a hypothesis. This capstone turns it into a measurement: a structured **red-team drill** in which you inject five real attack patterns into your own `shopnow` environment - staging or a dedicated clone, never production - and score how many controls caught each attack, at which layer, and how fast. The method borrows from professional purple-teaming: every attack is paired with the detection it *should* trigger, so the output is not "we survived" but a scorecard with named gaps, each becoming a ticket for a new policy, gate, or rule.

The five attacks are chosen to cover the whole [Table 1.1](#ch1) map - source, dependency, artifact, workload, runtime - and each is small enough to stage in minutes:

| # | Attack (red) | Expected detection (blue) | Layer |
|---|---|---|---|
| A1 | Commit a realistic AWS key | Pre-commit hook; gitleaks CI gate | Source |
| A2 | Open a PR adding a vulnerable dependency | Dependency review; Dependabot alert; Semgrep | Source |
| A3 | Push an unsigned, tampered image to the tracked tag | cosign verify in deploy; Kyverno `verifyImages` rejection | Artifact / Admission |
| A4 | Deploy a root, `:latest`, unlimited pod | Kyverno baseline policy rejection; policy report | Admission |
| A5 | Spawn a shell inside a running `shopnow` pod | Falco "shell in container" page; runbook execution | Runtime |

: Table 15.1 - The capstone drill: five attacks, the controls that should fire, the layers they live in

## 15.2 Running the Five Attacks

**A1 - the planted secret.** Create a scratch branch, commit `scripts/deploy.sh` containing an `AKIA`-shaped key, and open the PR. Three controls should engage in sequence: the local pre-commit hook (if you did not skip it - note that you could), the gitleaks CI gate failing the check run, and - the step that proves process, not just tooling - the *response*: rotate-and-remove per the [Chapter 2](#ch2) runbook. The drill question for A1 is "how long from commit to a finding a human saw?", and the honest follow-up is whether anyone *notified* the developer or just left a red X.

**A2 - the vulnerable dependency.** Add `requests==2.27.1` (the [Lab 2](#ch4) plant) to a fresh PR. Dependency review must comment with the advisory, the CI dependency gate must fail, and Dependabot's alert for the *existing* tree (if the version is already on `main`) must exist. This attack probes the review path: a human approving the PR despite a red check is the failure mode to name, which is why branch protection requiring those checks is part of the defense and part of the score.

**A3 - the tampered artifact.** Build a one-character-different `shopnow` image, push it to the same repository and tag as the CI-built one (bypassing the pipeline entirely - that is the point), and attempt two paths: the pipeline's `deploy` job (cosign verify must fail it) and a direct `kubectl set image` (Kyverno's `verifyImages` must reject it). If *either* path admits the image, the signature enforcement from [Chapter 6](#ch6) and [Chapter 8](#ch8) is decorative, and the gap goes straight to the backlog with the highest severity the drill assigns.

**A4 - the non-compliant workload.** Apply a pod manifest with `runAsRoot`, `:latest`, and no resource limits to `shopnow-prod`. Admission must reject with the policy message from [Chapter 8](#ch8) - and the drill checks the *message quality*: an engineer who has never read the policy should be able to comply from the error text alone. If the pod lands, check whether the namespace's policies are actually `Enforce` and whether the workload matched the policy's selector; a policy that does not match the workload it was written for is the most common silent gap in the whole stack.

**A5 - the compromise simulation.** This one needs a sacrificial target, so deploy a *deliberately* shell-equipped debug image (not the distroless `shopnow`) into a sandbox namespace, `kubectl exec` a shell, and touch a sensitive path. Falco should fire the shell-in-container rule, the event should reach Elasticsearch ([Chapter 12](#ch12)), and the `security-critical` severity should page Alertmanager's route. Then run the [Chapter 13](#ch13) runbook for real: quarantine with a deny-all NetworkPolicy, snapshot, delete, rebuild. Time the whole loop from `exec` to declared-standdown - that number is your current incident-response speed, and the only direction it should move is down.

::: {.lab}
### Lab 6 - The Full Drill, Scored {#lab6}

1. Stage the board: a staging cluster with the [Chapter 8](#ch8) policies in `Enforce`, the secured pipeline from [Chapter 7](#ch7), Falco and the telemetry routes from [Chapter 12](#ch12) live, and the runbook from [Chapter 13](#ch13) open in a tab. Confirm detection is green *before* attacking (a drill against dead sensors proves nothing).
2. Run attacks A1 through A5 in order, in separate sessions, recording for each: time-to-first-signal, which layer fired first, whether the alert reached a human, and whether the runbook step was executable from the document alone.
3. Score each attack 0-3: 0 = no signal, 1 = signal existed but nobody saw it, 2 = signal seen and handled manually, 3 = control rejected or paged automatically and the runbook executed cleanly.
4. For every score below 3, write the gap as a ticket with a named layer: a missed A1 is a branch-protection or notification gap; a missed A3 is an admission or verify gap; a slow A5 is a telemetry route or runbook gap.
5. Fix the cheapest gap immediately (it is usually a `validationFailureAction` still on `Audit`, or an Alertmanager route missing a matcher), rerun only that attack, and record the delta. The scorecard and the fixed gap are the capstone's deliverables.
6. Repeat the full drill next quarter. The number that matters across quarters is not the score - it is the *time* column falling.
:::

## 15.3 What the Drill Proves

A clean scorecard across all five attacks is the single most valuable security artifact an engineering team can possess: it is not a policy statement but a *demonstrated, timestamped* record that the platform rejects planted secrets, vulnerable dependencies, tampered artifacts, non-compliant workloads, and live compromises - which is also, not coincidentally, the strongest evidence the compliance chapter's auditor will ever be shown. The drill's second product is the gap list, and its relationship to the rest of the book is the point: every gap is one chapter's control that was configured but not enforced, or enforced but not detected, or detected but not rehearsed. Defense in depth is not a diagram; it is this loop - attack, measure, tighten, repeat - running on a schedule, with the numbers getting quietly better every quarter.

**See also:** [Chapter 16](#ch16) turns the drill cadence and the gap backlog into the team's standing security roadmap; [Chapter 13](#ch13) owns the runbook the drill exercises; [Table 1.1](#ch1) is the map the five attacks were drawn from.
