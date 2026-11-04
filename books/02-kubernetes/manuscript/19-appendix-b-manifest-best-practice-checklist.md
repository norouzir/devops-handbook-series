# Appendix B - Manifest Best-Practice Checklist {#appB}

Review manifests against this list; each item is one actionable sentence with its rationale. The items marked with an asterisk are the ones reviewers most often waive and later regret.

- Set CPU and memory requests on every container; the scheduler can only protect workloads that told it the truth.\*
- Set memory limits everywhere, and decide CPU limits deliberately rather than by default.\*
- Give every `Deployment` a `readinessProbe`; without one, a `Pod` is traffic-ready the moment the process starts.
- Use a `startupProbe` for slow-booting applications instead of inflating liveness thresholds.
- Point `livenessProbe` at an internal, dependency-free endpoint so a database blip cannot restart the fleet.
- Pin images to digests for release builds; tags are mutable and registries eventually prove it.\*
- Run as non-root: `runAsNonRoot: true`, a fixed `runAsUser`, and no container that needs UID 0.
- Drop `capabilities` to `ALL` and add back only what is genuinely required; set `allowPrivilegeEscalation: false`.
- Set `readOnlyRootFilesystem: true` and mount an `emptyDir` for the few writable paths.
- Label consistently (`app`, `component`, `partOf`) because selectors, policies, and dashboards all key off labels.
- Reference ConfigMaps and Secrets that exist in the same manifest set, and apply configuration objects first.
- Mark configuration immutable once consumers are settled; future you is the beneficiary.
- Set `automountServiceAccountToken: false` on Pods whose workload calls no API.
- Add a `PodDisruptionBudget` to every service that must survive node maintenance, and size it against replica count.\*
- Use `topologySpreadConstraints` for user-facing services so one zone cannot hold every replica.
- Choose `RollingUpdate` strategy numbers consciously: `maxUnavailable: 0` for services that must hold capacity.
- Set `ttlSecondsAfterFinished` on Jobs and a `concurrencyPolicy` on every `CronJob`.
- Use `volumeClaimTemplates` with an explicit `storageClassName` and `Retain`-backed classes for stateful sets.
- Keep namespaces labeled for Pod Security Admission levels from day one: `warn` and `audit` before `enforce`.\*
- Add `NetworkPolicy` default-deny to each application namespace, then allow what the service actually needs.
- Prefer the Gateway API for new HTTP routing; keep annotation-driven `Ingress` for legacy only.
- Never place plaintext credentials in manifests, images, or pipeline logs; use a vault-backed `Secret` mechanism.\*
