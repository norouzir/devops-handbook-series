# Chapter 5 - Configuration: ConfigMaps, Secrets, and Pod Settings {#ch5}

The Docker book's rule, one image per environment with configuration injected at runtime, becomes formal in Kubernetes: configuration is API objects, injected into Pods in typed and auditable ways. This chapter covers the two configuration objects and their injection modes, the security context settings that control identity and privileges inside the Pod, and the apply workflow that keeps all of it reviewable. The goal is a service whose image never changes between environments and whose configuration always says where it came from.

## 5.1 ConfigMaps: Injecting Configuration

A `ConfigMap` is a small key-value store for non-sensitive configuration: keys become either environment variables or files mounted into a container. Environment injection suits simple knobs like `LOG_LEVEL` and feature flags; file mounts suit anything structured, an `nginx.conf`, a `log4j2.xml`, an entire `/etc` app directory. The two modes differ in one behavior that matters operationally: env values are fixed at container start, while mounted files are updated by the `kubelet` within the sync period, so a mounted reload-capable application can pick up changes without a rollout, and a common pattern is pairing the file mount with an annotation checksum that triggers a rolling restart only when a restart is truly needed.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config
  labels: { app: api }
data:
  LOG_LEVEL: "info"
  nginx.conf: |
    server {
      listen 8080;
      location / { proxy_pass http://127.0.0.1:9000; }
    }
---
# excerpt of the Pod template consuming it
    spec:
      containers:
        - name: api
          image: myorg/api:1.4.0
          envFrom:
            - configMapRef: { name: api-config }
          volumeMounts:
            - { name: nginx-conf, mountPath: /etc/nginx/conf.d }
      volumes:
        - name: nginx-conf
          configMap: { name: api-config, items: [ { key: nginx.conf, path: default.conf } ] }
```

Size and structure rules keep ConfigMaps sane: keep them under the 1 MiB object limit and out of them anything secret, anything huge, and anything binary, which belongs in object storage referenced by name. Mark configuration that is consumed at startup only as immutable: immutable ConfigMaps reject changes, which protects a whole class of accidents and lets the API server skip watch traffic for them. Every `ConfigMap` should carry the same `app` label as its consumer so a namespace review shows which objects feed which workloads.

## 5.2 Secrets: Sensitive Configuration

A `Secret` is a `ConfigMap` with sensitive intent and better handling: values are stored base64-encoded, exposure is gated by RBAC that can be narrowed to specific `Secret` names, and the `kubelet` can mount them as `tmpfs` files rather than write them to the node's disk. The base64 detail deserves emphasis because it is the most repeated misconception in Kubernetes onboarding: encoding is not encryption, anyone with get rights on the `Secret` reads it with `kubectl get secret -o yaml` plus one decode step. The protection layers that matter are RBAC, encryption at rest for `etcd`, which managed providers enable and `kubeadm` clusters should, and audit logging on `Secret` reads.

Day-to-day `Secret` hygiene is procedural. Create with `kubectl create secret generic` from literals or files, never by committing decoded values; prefer `stringData` when authoring YAML so values stay readable, and let the API encode them. Mark secrets immutable once consumers are settled. For git-stored secret management, which Part II's GitOps flow needs, the standard tools are External Secrets Operator, which syncs from a real vault, SealedSecrets, which stores only encrypted data in git, and SOPS for file-level encryption; Chapter 13 compares them in the pipeline context. What never changes is the destination: a `Secret` belongs in a vault or an encrypted artifact, not in a Docker layer or a plain manifest in a public repo, the exact mistake the Docker book's Watch out box warned about.

## 5.3 Security Contexts and Pod Settings

The `securityContext` fields are where a `Pod`'s Linux identity is set, and they compose with Chapter 9's policies. `runAsNonRoot` with a `runAsUser` rejects container images that insist on UID 0, enforcing at admission what the Docker book recommended by habit. `readOnlyRootFilesystem` with a writable `emptyDir` for the few writable paths turns most file-based exploits into dead ends. Capabilities should be dropped to `ALL` and added back only where a container genuinely needs one, and `allowPrivilegeEscalation: false` closes the setuid loophole. These settings are your half of the contract: Chapter 9's Pod Security Admission will enforce the same line namespace-wide, but workloads that already comply never need exceptions.

## 5.4 Applying Configuration Safely

`kubectl apply` is the daily driver, and two habits make it safe. First, `kubectl diff -f` shows exactly what an apply will change, using server-side dry-run, which catches selector drift and deleted fields before they land. Second, server-side apply, the default write path since the field-manager model matured and now the mechanism Helm 4 uses, records which manager owns which field, so tools stop stepping on each other's edits and `kubectl apply --server-side --force-conflicts` is an understood, deliberate operation rather than a mystery. The `last-applied` annotation of the old client-side flow still exists, but new tooling has moved on, and your pipelines should too.

| Mechanism | Use for | Key behavior |
| ------------ | -------------------- | ------------------ |
| `ConfigMap` env | Simple flags, endpoints, log levels | Fixed at container start; changes need a rollout |
| `ConfigMap` file mount | Config files, templates, full app config | `Kubelet` refreshes files; app may reload live |
| `Secret` env / mount | Credentials, tokens, keys | RBAC-gated; `tmpfs` mounts; base64 is not encryption |
| Immutable `ConfigMap`/`Secret` | Startup-only config, trust anchors | Rejects updates; protects from drift accidents |
| External Secrets Operator | GitOps-managed credentials from a vault | Syncs from Vault/ASM/Secrets Manager into Secrets |

: Table 5.1 - Configuration mechanisms and when to use each

::: {.warn}
**Watch out**

The most common configuration incident is the silent env-var mismatch: a `Deployment` references a `ConfigMap` key that does not exist or a `ConfigMap` that is not created yet, the container starts with an empty value, and the failure surfaces later as an application error far from the cause. Guard the seam: keep `ConfigMap` and `Deployment` in one manifest set, apply ConfigMaps first, and add a startup check that fails fast when a required variable is missing.
:::

**See also:** [Chapter 4](#ch4) for the workloads that mount these objects, [Chapter 9](#ch9) for secrets at cluster scale.
