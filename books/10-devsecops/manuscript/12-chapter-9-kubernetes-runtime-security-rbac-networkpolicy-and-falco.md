# Chapter 9 - Kubernetes Runtime Security: RBAC, NetworkPolicy, and Falco {#ch9}

## 9.1 Identity Inside the Cluster: ServiceAccounts and RBAC

Admission control ([Chapter 8](#ch8)) decides *what may enter* the cluster; this chapter decides *what each thing inside may do*. The unit of workload identity is the **ServiceAccount**. Its two defaults are both permissive and both worth fixing in any production namespace: every pod without an explicit `serviceAccountName` runs as `default`, and every ServiceAccount mounts its API token into the pod automatically. The hardened baseline for `shopnow`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: shopnow
  namespace: shopnow-prod
automountServiceAccountToken: false   # the app never talks to the API
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: shopnow, namespace: shopnow-prod }
spec:
  template:
    spec:
      serviceAccountName: shopnow
      automountServiceAccountToken: false
```

A workload that never calls the Kubernetes API (the common case - `shopnow` serves HTTP and talks to PostgreSQL) needs no token at all, and not mounting one removes an entire credential class from the pod's file system. Workloads that *do* talk to the API get a dedicated ServiceAccount bound by **RBAC** to a narrowly written Role - the `shopnow-operator` that reads its own ConfigMap gets `get`/`list` on ConfigMaps in `shopnow-prod` and nothing else, which is the same least-privilege grammar the Terraform book applied to cloud IAM. The audit question worth asking quarterly: `kubectl get rolebindings,clusterrolebindings -A` and for every binding, *who is bound, to what, and would a compromise of that identity matter?* ClusterRoleBindings with `cluster-admin` are like root SSH keys from the 2000s - they exist, but each one should have a named owner and a reason, and the count should approach zero.

## 9.2 NetworkPolicy: The Lateral-Movement Killer

By default, every pod in a Kubernetes cluster can reach every other pod on every port. That flat network is the attacker's highway: one compromised pod in a staging namespace can reach a production database directly, because nothing between them speaks policy. **NetworkPolicy** changes the default - and the key semantic is that the *first* policy selecting a pod makes that pod isolated: everything not explicitly allowed becomes denied. The production pattern for `shopnow-prod` is therefore default-deny, then three explicit allowances:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny-all, namespace: shopnow-prod }
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: shopnow-allow, namespace: shopnow-prod }
spec:
  podSelector: { matchLabels: { app: shopnow } }
  policyTypes: [Ingress, Egress]
  ingress:
    - from:                          # only the ingress controller's pods
        - namespaceSelector: { matchLabels: { name: ingress-nginx } }
          podSelector: { matchLabels: { app.kubernetes.io/name: ingress-nginx } }
      ports: [{ port: 8080, protocol: TCP }]
  egress:
    - to: [{ podSelector: { matchLabels: { app: postgres } } }]   # the database
      ports: [{ port: 5432, protocol: TCP }]
    - to:                            # DNS, or nothing else resolves
        - namespaceSelector: {}
      ports: [{ port: 53, protocol: UDP }]
```

The result reads like a firewall from a textbook: `shopnow` accepts traffic only from the ingress controller on 8080, sends only to PostgreSQL on 5432 and to DNS, and cannot reach - or be reached from - anything else, including other namespaces. A compromised `shopnow` pod's blast radius shrinks from "the cluster network" to "the database connection it was always going to use."

::: {.warn}
**Watch out - NetworkPolicy needs a CNI that enforces it**

The API object is not the enforcement: vanilla `kind`, plain kubeadm with many defaults, and several managed control planes accept NetworkPolicy objects and silently do nothing without a policy-capable CNI (Calico, Cilium, Weave). The classic failure is writing a policy set, seeing no behavior change, and concluding it works - it does not. Verify enforcement with a positive and a negative test from a scratch pod: `kubectl run tmp --rm -it --image=busybox -- nc -zv shopnow 8080` must fail from an unselected pod and the app must still work through the ingress. The Kubernetes book's networking chapter covers CNI selection; here, only the test proves the control.
:::

## 9.3 Pod Hardening: The SecurityContext Stack

[Chapter 8](#ch8)'s policies *require* a hardened pod spec; this section is what that spec actually contains, layer by layer:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    seccompProfile: { type: RuntimeDefault }   # kernel syscall filter
  containers:
    - name: shopnow
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true            # payload can't be planted on disk
        capabilities: { drop: ["ALL"] }         # no CAP_NET_RAW, no CAP_SYS_ADMIN...
      volumeMounts:
        - { name: tmp, mountPath: /tmp }        # writable tmp as emptyDir
  volumes:
    - { name: tmp, emptyDir: {} }
```

Each line removes a concrete capability an attacker values: `runAsNonRoot` and the dropped capabilities shrink the process's kernel reach; `seccompProfile: RuntimeDefault` filters the syscall surface to a sane subset; `readOnlyRootFilesystem` means a downloaded payload has nowhere durable to live (pair with an `emptyDir` for the paths the app legitimately writes). Individually each is a speed bump; together they are why the distroless image of [Chapter 5](#ch5) and the nonroot default matter - the controls only compose when the image has no shell, the process has no capabilities, and the filesystem accepts no writes.

## 9.4 Falco: Detecting What Should Not Be Happening

Everything above is *prevention* - rules that make bad behavior impossible. **Falco** is *detection*: a syscall-level sensor that watches what processes actually do and fires rules on the anomalous - a shell spawned in a container, `shopnow` opening `/etc/shadow`, an outbound connection to a fresh IP, a write to a sensitive mount. Prevention assumes the rule set anticipated the attack; detection covers the attacks that get through anyway, which [Chapter 1](#ch1) promised would happen eventually. Falco ships thousands of community rules and expresses its own in readable conditions:

```yaml
- rule: Terminal Shell in Container
  desc: A shell was spawned inside a container - rare and worth a page.
  condition: >
    spawned_process and container and
    proc.name in (bash, sh, ash, zsh) and
    not k8s.pod.label.role in (debug, toolbox)
  output: >
    Shell in container (user=%user.name pod=%k8s.pod.name
    container=%container.name parent=%proc.pname cmd=%proc.cmdline)
  priority: WARNING
```

A distroless `shopnow` cannot spawn a shell at all - so the rule above firing in `shopnow-prod` is not a tuning question; it is an incident, and it goes to [Chapter 12](#ch12)'s telemetry pipeline and pager. Falco's deployment story (the `falcoctl` driver on nodes, or the `falco-sidekick` route into Prometheus Alertmanager and Elasticsearch) is deferred to the telemetry chapter; what belongs here is the design principle: **prevent what you can predict, detect everything else** - and every Falco alert that proves a prevention gap becomes a candidate admission policy or pod spec change in the next sprint.

**See also:** [Chapter 10](#ch10) applies the same least-privilege lens to the infrastructure under the cluster; [Chapter 12](#ch12) wires Falco and the audit log into the observability stack; the Kubernetes book's Chapter 9 remains the full reference for RBAC verbs and Pod Security standards.
