# Chapter 8 - Policy as Code for Kubernetes: Kyverno and OPA Gatekeeper {#ch8}

## 8.1 The Admission Controller: The Cluster's Last Border

Part I's controls run in the pipeline; this chapter installs the same discipline inside the cluster itself. Every object that enters Kubernetes passes through the API server, and the API server consults **admission controllers** - synchronous webhooks that receive the object *before* it is persisted and may validate it, mutate it, or reject it outright. This is the one enforcement point where "no" actually means no: a rejected Deployment never schedules, never starts, and never touches the network. Policy as code here converts the cluster's implicit trust ("anything that made it past kubectl apply is allowed") into explicit, versioned, testable rules - the same shift Terraform brought to infrastructure in the IaC book.

The two dominant open-source engines express the same idea with different grammars. **Kyverno** uses Kubernetes-native YAML policies - no new language, resources matched by kind and name, rules that validate, mutate, or generate. **OPA Gatekeeper** uses policies written in **Rego**, OPA's declarative language, with constraint templates that offer more expressive logic at the cost of a second language. This book leads with Kyverno for day-to-day policy (its readability wins adoption, and adoption is the hard part) and covers Gatekeeper where its expressiveness matters. The policy set below is the cluster-side complement to [Chapter 7](#ch7)'s pipeline: the cluster now independently refuses what the pipeline would never ship.

## 8.2 Kyverno in Practice

Installation is a Helm chart (the Kubernetes book's chapter on packaging applies unchanged), after which policies are ordinary cluster objects:

```bash
helm repo add kyverno https://kyverno.github.io/kyverno
helm install kyverno kyverno/kyverno -n kyverno --create-namespace
```

The canonical first policy requires signed images - Part I's proof, enforced where it is final:

```yaml
# 01-verify-signatures.yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-shopnow-signature
spec:
  validationFailureAction: Enforce   # Audit = observe only; Enforce = reject
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-signature
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaces: ["shopnow-prod"]
      verifyImages:
        - imageReferences:
            - "ghcr.io/acme/shopnow:*"
        attestors:
          - entries:
              - keyless:
                  subjectRegExp: "^https://github.com/acme/shopnow/"
                  issuerRegExp: "^https://token.actions.githubusercontent.com/"
                  rekor:
                    url: https://rekor.sigstore.dev
```

A pod referencing `ghcr.io/acme/shopnow` in `shopnow-prod` is admitted only if its digest carries a valid keyless signature from the repository's CI - the cosign verify of [Chapter 6](#ch6), executed by the cluster on every create and update. Three more policies complete the starter set, each one rule-shaped and reviewable:

```yaml
# 02-baseline-policies.yaml (excerpt)
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: shopnow-baseline
spec:
  validationFailureAction: Enforce
  background: true          # audit existing resources too
  rules:
    - name: require-nonroot-and-limits
      match:
        any: [{ resources: { kinds: [Pod], namespaces: ["shopnow-*"] } }]
      validate:
        message: "Containers must run non-root and declare CPU/memory limits."
        pattern:
          spec:
            containers:
              - securityContext:
                  runAsNonRoot: true
                resources:
                  limits: { "?*": "?*" }
    - name: require-image-tag-not-latest
      match:
        any: [{ resources: { kinds: [Pod], namespaces: ["shopnow-*"] } }]
      validate:
        message: "Image tags must be digests or semver - never :latest."
        pattern:
          spec:
            containers:
              - image: "*:*@* | !*latest*"
```

`kubectl get policyreports -A` shows the audit view - violations against already-running workloads, which is how a policy is *rolled out*: set `validationFailureAction: Audit` first, read the reports for a week, fix the legitimate hits, then flip to `Enforce`. Mutation rules earn their keep for defaults (injecting `runAsNonRoot`, adding network policies to new namespaces) so the compliant path is the zero-effort path.

::: {.warn}
**Watch out - an admission webhook is on the critical path of every write**

The API server calls admission webhooks synchronously: if the Kyverno pods are down or unreachable and the webhook's `failurePolicy` is `Fail`, *every* `kubectl apply` in the cluster fails - including the ones trying to fix Kyverno. The protections are built in and worth knowing before the first incident: the Kyverno namespace is self-exempt, Helm's upgrade path handles the ordering, and an administrator with the right cluster credentials can remove the ValidatingWebhookConfiguration in a true emergency. Roll policies out to one namespace, not the whole cluster, and never deploy a policy to production that has not run in staging first - [Lab 5](#lab5) exists precisely so the first `Enforce` surprise is not a production deploy.
:::

## 8.3 Gatekeeper: The Same Idea in Rego

Gatekeeper expresses policy as **ConstraintTemplates** (Rego logic) instantiated by **constraints** (parameters). The no-latest rule in Rego:

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredimagetag
spec:
  crd:
    spec:
      names: { kind: K8sRequiredImageTag }
  targets:
    - target: admission.k8s.gatekeeper.sh
      libs:
        - |
          package k8srequiredimagetag
          deny.never = true        # template placeholder; logic lives in src below
      src:
        - |
          package k8srequiredimagetag
          deny contains msg if {
            c := input.review.object.spec.containers[_]
            not endswith(c.image, ":latest")
            not contains(c.image, "@sha256:")
            msg := sprintf("image %v must be digest- or semver-tagged", [c.image])
          }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredImageTag
metadata:
  name: shopnow-no-latest
spec:
  match:
    kinds: [{ apiGroups: [""], kinds: ["Pod"] }]
    namespaces: ["shopnow-prod"]
```

The Rego version states the same invariant in logic rather than pattern, which buys composability (one template, many constraints, parameterized by namespace or registry) and costs a language your team must learn to review. The pragmatic split used throughout the rest of the book: Kyverno for the working policy set, Gatekeeper for policies that genuinely need logic Kyverno's patterns cannot express, and **one** of them owning enforcement in any given cluster - two admission stacks on the same resource means two failure modes on every write, and no way to know which policy said no.

## 8.4 Policy Operations: Test, Roll Out, Live With It

Policies are code and get the full treatment. Kyverno ships `kyverno apply` (and a `kyverno test` harness with fixtures) so a policy runs against manifests in CI - the same pull request that changes the Deployment runs the policy suite that will judge it, and policy regressions fail before the cluster ever sees them. Version policies in the same GitOps repository as everything else (the Kubernetes book's Chapter 13 pattern), so admission behavior is diffed and rolled back like code. And keep the human vocabulary ready: every `Enforce` rejection returns the policy's `message` to the kubectl caller, so write messages for the engineer who hits them at deploy time - "image must be signed by CI; see runbook section 4" - because the admission controller is the one tool in the cluster that talks back.

::: {.lab}
### Lab 5 - Stand Up Kyverno and Reject a Violation {#lab5}

1. Install Kyverno into a kind or staging cluster (Helm, as above) and confirm `kubectl get pods -n kyverno` is healthy.
2. Apply the three starter policies with `validationFailureAction: Audit`. Deploy the *clean* `shopnow` image from [Chapter 7](#ch7) and read `kubectl get policyreports -n shopnow-prod` - note which rules pass and which flag legacy workloads.
3. Deploy a deliberate violation: `shopnow:latest` with no resources block, `runAsRoot` implied. Observe the policy report *accepting the deploy* (Audit), with the violations named.
4. Flip `verify-shopnow-signature` and `shopnow-baseline` to `Enforce`. Re-apply the violating deployment: it must be **rejected** by the API server with the policy message. Deploy the signed, digest-tagged image from [Chapter 7](#ch7): it must be admitted.
5. Break the guarantee: build a one-character-different image, push it to the same tag, and attempt the deploy. Admission rejects the unsigned digest - the tamper-test from [Lab 4](#ch5), now enforced by the cluster instead of the pipeline.
6. Write one policy of your own for a real convention `shopnow` should have (a required label, a namespace annotation, a specific registry allowlist), test it with `kyverno apply` against the repo's manifests, and open it as a PR with an Audit rollout plan.
:::

**See also:** [Chapter 9](#ch9) hardens what admission lets through - identity, network, and runtime; the Kubernetes book's security chapter holds the Pod Security baseline these policies enforce; [Appendix C](#appC) carries the complete policy files from this chapter.
