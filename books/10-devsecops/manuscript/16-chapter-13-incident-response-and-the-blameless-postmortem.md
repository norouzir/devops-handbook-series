# Chapter 13 - Incident Response and the Blameless Postmortem {#ch13}

## 13.1 The Lifecycle: Declare, Contain, Eradicate, Recover, Learn

An incident is any event where the answer to "is this bad?" is "we are not sure" or "yes" - and the first discipline is that **declaration is cheap**. Response lives and dies on time-to-declaration: a suspected incident declared at minute five that turns out to be a deploy quirk costs an apology in standup; the same suspicion deferred for a day while someone "double-checks quietly" is a day of attacker dwell time. The lifecycle this chapter uses is the standard incident-response loop, adapted to the stack this book built:

1. **Declare** - page the on-call, open the incident channel and document, assign an **incident commander** (IC) whose job is coordination, not typing commands.
2. **Contain** - stop the bleeding while preserving evidence: revoke the credential, quarantine the pod, block the source, snapshot before wiping.
3. **Eradicate** - remove the access and the artifact: rotate everything the intruder could have touched, rebuild from trusted images ([Chapter 5](#ch5) makes this a pipeline run, not a project).
4. **Recover** - restore service from verified-clean state, watch the telemetry from [Chapter 12](#ch12) for the return trip, then stand down formally.
5. **Learn** - the blameless postmortem, written while memory is fresh, with action items that are tickets with owners and dates.

The stage order is deliberate and worth defending: containment comes before eradication because cutting access *first* preserves the option to investigate; eradication before recovery because restoring onto a compromised surface is a restart button for the incident; and evidence preservation throughout, because the postmortem and any legal or insurance follow-up are only as good as what was captured before the rebuild.

## 13.2 The Runbook: Pre-Deciding Under Pressure

The incident commander's real advantage is never intelligence under pressure - it is that the decisions were made calmly, months earlier, and written down. A **security runbook** is that record, one page per alert from [Chapter 12](#ch12), each answering the same four questions in the same order: *What is this alert actually saying?* (the triage questions that separate true from false in ninety seconds), *What is the containment move?* (the exact commands, copy-pasteable at 2 a.m.), *Who else gets pulled in?* (the escalation list, with a backup per name), and *What evidence do we capture before touching anything?* The `shopnow` set looks like this in practice:

| Alert | First containment move | Evidence before acting |
|---|---|---|
| Shell in container ([Chapter 9](#ch9)) | Quarantine: apply a deny-all NetworkPolicy to the pod | `kubectl get pod -o yaml`, Falco event, process list snapshot |
| Leaked secret (gitleaks hit) | Revoke/rotate in Vault; audit reads of that path | Vault audit log for the secret path, git history |
| Unsigned image rejected ([Chapter 8](#ch8)) | Verify who/what pushed; registry event log | Registry push events, cosign verify output |
| Audit log disabled | Restore via GitOps revert; freeze IAM changes | Audit stream up to the gap, IAM change history |

: Table 13.1 - Excerpts from the `shopnow` security runbook: the pre-decided first moves

The runbook is versioned in the same repository as the alerts it answers, reviewed after every incident and every game day, and rehearsed - which is the part that separates a runbook from a wiki page.

## 13.3 Containment Mechanics in This Stack

The stack from Parts I and II makes containment unusually mechanical, and it is worth seeing how the earlier chapters pay off. A compromised credential is a Vault revocation plus a lease audit - seconds, because credentials were short-lived by design ([Chapter 2](#ch2)). A compromised pod is a NetworkPolicy quarantine and a kill - and the *rebuild* is the pipeline, because the cluster runs digest-pinned, signed images verified at admission ([Chapter 8](#ch8)), so "redeploy clean" and "prove it is clean" are the same operation. A compromised identity is an OIDC/IAM rotation with the audit stream to bound the blast radius in time. The general containment principle: **act on identity and network first** (revoke, isolate - fast and reversible), **act on state second** (snapshot, then wipe and rebuild from the signed artifact). The one rule that must never bend: snapshot the interesting state - the pod's filesystem, the relevant logs, the process table - *before* the destructive fix, because eradication is one `kubectl delete` away from destroying the evidence the postmortem needs.

## 13.4 The Blameless Postmortem

The postmortem is where an incident pays its way, and **blameless** is an engineering property, not a courtesy: people who fear blame hide the details that explain failures, and the details are the product. The template is stable across the industry: a one-line summary with severity and duration; the **timeline** (every action and detection with timestamps, written from the logs, not memory); the impact statement (users, data, money); the **analysis** - not "five whys" the ritual, but the honest causal chain: what did the controls assume, which assumption failed, and *why was that assumption reasonable at the time it was made?* The final section is the payoff: **action items as tickets with owners and dates**, split by type - a prevention gap feeds an admission policy or pipeline gate ([Chapter 8](#ch8), [Chapter 7](#ch7)), a detection gap feeds a Falco rule or alert ([Chapter 12](#ch12)), a process gap feeds the runbook (this chapter). A postmortem without dated action items is a memoir.

::: {.note}
**Best practice - review postmortems like code**

The postmortem document itself goes through review: a peer (ideally from another team) reads it asking one question - "would our current controls catch this again tomorrow?" If the honest answer is no, the action items are not done; if the action items are done, the document closes with a **game day** that replays the failure and demonstrates the new control working. The review-and-replay loop is what converts incident pain into organizational immunity, and it is also the strongest artifact a compliance audit ([Chapter 14](#ch14)) can be shown.
:::

## 13.5 Practice Before the Real Thing

Response under pressure is a rehearsed skill, and rehearsal is schedulable. The **tabletop exercise** runs an hour: read the incident scenario (a leaked `AKIA` key in a fork, an unsigned image in the registry, an alert nobody has ever paged on), walk the runbook aloud, and write down every place the document said something nobody could execute. The **game day** goes further and injects the event into staging for real - kill the admission webhook, drop a shell into a pod, push an unsigned image - with the on-call responding as if it were production. Two drills a year per team is enough to keep the runbook honest and the pager reflexes alive, and the capstone chapter next door ([Chapter 15](#ch15)) is, in effect, this book's own game day.

**See also:** [Chapter 12](#ch12) supplies the alerts this chapter responds to; [Chapter 14](#ch14) turns the runbooks and postmortems into audit evidence; the Prometheus & Grafana book's alerting chapter remains the reference for the Alertmanager routing that pages the IC.
