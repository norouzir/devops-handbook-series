# Chapter 9 - Security: RBAC, Pod Security, and Hardening {#ch9}

Kubernetes security is not one wall but a sequence of gates, and this chapter walks them in the order a request meets them: who are you, what may you do to the API, what may a `Pod` become on its node, and which Pods may talk to which. The mechanisms are RBAC for the API, Pod Security Admission for `Pod` privileges, and `NetworkPolicy` for east-west traffic, and each has a clean mental model that turns security from folklore into configuration. The lab at the end builds all three on your `kind` cluster.

## 9.1 Authentication and ServiceAccounts

Every request to the API server carries an identity. Humans authenticate through certificates, OIDC tokens from your identity provider, or cloud-specific integrations, and machine identity is the `ServiceAccount`: a namespaced object whose projected token is mounted into Pods at a known path. The modern token is time-limited and audience-bound, requested through the `TokenRequest` API and refreshed by the `kubelet`, a quiet but important improvement over the eternal tokens of older clusters. The operational rule that prevents most accidents is deny-by-default thinking: a `Pod` gets a `ServiceAccount` with exactly the permissions its workload needs, and if it needs none, `automountServiceAccountToken: false` removes the token from the `Pod` entirely.

## 9.2 RBAC in Practice

Authorization is a pure lookup: does any `RoleBinding` grant this subject the verb on this resource in this namespace, or via a `ClusterRoleBinding` cluster-wide. `Roles` and bindings are small YAML, and the effective-question tool is built in: `kubectl auth can-i create deployments -n prod` answers instantly, and `--as=system:serviceaccount:prod:api` lets you audit on behalf of any service account. Verbs are coarse but sufficient: `get`, `list`, `watch` for readers; `create`, `update`, `patch`, `delete` for writers; and for controllers, the full watch on their resource. Two structures scale well in practice: one `ClusterRole` per job shape bound into each namespace that needs it, and aggregated `ClusterRoles` whose `rules` assemble by label for cluster-scoped operators.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata: { name: api, namespace: prod }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: api-reader, namespace: prod }
rules:
  - apiGroups: [ "" ]
    resources: [ "configmaps" ]
    verbs: [ "get", "list", "watch" ]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: api-reader-binding, namespace: prod }
subjects:
  - { kind: ServiceAccount, name: api, namespace: prod }
roleRef:
  kind: Role
  name: api-reader
  apiGroup: rbac.authorization.k8s.io
```

The classic RBAC mistakes are all scope mistakes. Binding `cluster-admin` to a workload because the pod needed one forgotten permission hands the entire cluster to that `Pod`, and the credential theft playbook in every container-escape story starts there. Wildcard `rules` copied from tutorials quietly grant `resources` nobody inventoried. And editing the built-in roles instead of creating your own survives only until the next upgrade. Audit with `kubectl auth can-i --list --as=...` per service account; the output is short, reviewable, and regularly embarrassing.

## 9.3 Pod Security Admission

Pod Security Policies were removed in v1.25, and their replacement, Pod Security Admission, is both simpler and harder to misconfigure: namespaces carry one label per level, and the API server enforces the level on `Pod` creation. `Privileged` is unrestricted and reserved for `kube-system` and the few controllers that earn it. `Baseline` blocks the known-escalation primitives, host namespaces, `hostPath`, `privileged` containers, host networking, while leaving normal applications untouched. `Restricted` is the modern baseline from the Docker book made mandatory: non-root UID, dropped `capabilities`, no privilege escalation, seccomp profile `RuntimeDefault`. `Enforce`, `audit`, and `warn` are independent per namespace, which gives you the migration sequence for free: `warn` and `audit` first, read the warnings for a sprint, then flip `enforce`.

## 9.4 NetworkPolicies

The pod network from Chapter 6 is all-allow by design: any `Pod` may talk to any `Pod` unless you say otherwise, and in most clusters that is dozens of microservices and a database all sharing one flat network. `NetworkPolicy` is the firewall layer, selected by the same label matching as everything else: a policy applying to pods with `app: api` specifies which ingress sources and egress destinations are allowed, and the first policy touching a `Pod` flips it from allow-all to deny-anything-not-listed. Two structural rules prevent surprises: policies are namespace-scoped, so cross-namespace rules name namespaces explicitly in their selectors, and enforcement depends on the CNI, since a `NetworkPolicy` in a cluster whose plugin ignores policies is security theater, which is why Calico and Cilium dominate real estates.

```yaml
# default-deny for all pods in the namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny, namespace: prod }
spec:
  podSelector: {}
  policyTypes: [ Ingress, Egress ]
---
# allow api to receive from the gateway, and to reach DNS + its database
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: api-allow, namespace: prod }
spec:
  podSelector: { matchLabels: { app: api } }
  policyTypes: [ Ingress, Egress ]
  ingress:
    - from: [ { podSelector: { matchLabels: { app: gateway } } } ]
      ports: [ { protocol: TCP, port: 8080 } ]
  egress:
    - to: [ { namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: kube-system } } } ]
      ports: [ { protocol: UDP, port: 53 } ]
    - to: [ { podSelector: { matchLabels: { app: postgres } } } ]
      ports: [ { protocol: TCP, port: 5432 } ]
```

## 9.5 Hardening Beyond the API

The remaining hardening is mostly the Docker book's discipline continued: images scanned and digest-pinned, secrets from vaults rather than `ENV`, and runtime identity from the node's cloud role instead of long-lived credentials. Workload identity, IRSA on EKS, Workload Identity on GKE, and the Azure equivalent, lets a `ServiceAccount` assume a cloud role, so a `Pod` reading from object storage needs no static keys at all. Add the supply-chain layer on top: admission policies checking image provenance, and the SBOM and attestation habits from the Docker book's BuildKit chapter carry over unchanged, because the cluster consumes exactly the artifacts you hardened there.

::: {.lab}
### Lab 3 - Build the security gates {#lab3}

1. Create namespace `locked`, label it with Pod Security levels `warn=restricted` and `audit=restricted`, then deploy an unprivileged `nginx` `Pod` and a `privileged` one. Read both warning lines and explain which fields the `restricted` level rejects.
2. Create the `api` `ServiceAccount` and `Role`/`RoleBinding` from Section 9.2, then verify with `kubectl auth can-i --list --as=system:serviceaccount:default:api -n default` that it can read `configmaps` and nothing else.
3. Run a `Pod` with that `ServiceAccount` and confirm its token exists only as a projected, expiring volume: `kubectl exec -it ... -- cat /var/run/secrets/tokens/...`. Then set `automountServiceAccountToken: false` on another `Pod` and confirm no token mounts.
4. Apply the `default-deny` and `api-allow` `NetworkPolicies` from Section 9.4 to a test namespace running two labeled `Deployments`. Verify the blocked path times out and the allowed path connects, and note which CNI is enforcing in your `kind` cluster.
5. Finish with an audit pass: for every `ServiceAccount` in `kube-system`, run `kubectl auth can-i --list --as=...` and identify the two most powerful. There is no fix required; the exercise is to make privilege visible.
:::

**See also:** [Chapter 5](#ch5) for the secrets this chapter hardens, [Chapter 10](#ch10) for resource limits as a denial-of-service control.
