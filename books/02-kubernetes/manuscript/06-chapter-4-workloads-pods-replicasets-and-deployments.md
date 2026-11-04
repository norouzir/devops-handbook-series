# Chapter 4 - Workloads: Pods, ReplicaSets, and Deployments {#ch4}

Workload objects are where your intentions meet the scheduler. This chapter covers the ladder from the `Pod` up through `ReplicaSet` to `Deployment`, the probe and resource settings that make Pods survivable, and the rollout machinery that makes releases boring, which is the highest compliment an operations book can pay. These are the objects you will write most; fluency here is the entry ticket to everything in Part II.

## 4.1 Pods and Their Containers

A `Pod` is a host in miniature: one IP address shared by all its containers, one lifecycle, one scheduler decision. Containers inside a `Pod` talk over `localhost` and share configured volumes, which is why sidecar patterns work, but a `Pod` is also the unit of failure: any container crashing marks the whole `Pod`'s health, and scaling means new whole Pods, never half of one. The default is therefore one container per `Pod`, and multi-container Pods are a deliberate design choice for genuinely coupled processes.

Native sidecars, stable since v1.29, are declared as init containers with `restartPolicy: Always`, and the ordering guarantees are worth knowing precisely: sidecars start before the main container and are guaranteed running first, which fixes the classic race where a log shipper or service mesh proxy missed early traffic; on shutdown they are stopped after the main container exits. Ordinary init containers remain the right tool for one-shot setup that must complete, such as waiting for a database or generating config, because the main container does not start until they exit successfully.

## 4.2 Labels, Selectors, and Annotations

Labels are how Kubernetes groups objects, and grouping is how everything works: a `Service` finds its backends by selector, a `Deployment` finds its Pods the same way, and your own commands filter with `-l`. Because selectors are contracts, rename labels carefully; changing a `Deployment`'s pod template labels breaks its `Service` silently if the selector no longer matches. The convention worth adopting early is a small fixed set: `app` for identity, `component` or `tier` for role, `version` or `track` for release metadata. Annotations carry the rest: per-tool configuration, checksums for config-driven restarts, and human notes that must not affect selection.

## 4.3 ReplicaSets and Deployments

A `ReplicaSet`'s entire job is the count: it maintains N ready Pods matching its selector, creating or deleting as reality drifts. You rarely write one directly, because a `Deployment` wraps it with the part that matters for releases: whenever the `Pod` template changes, the `Deployment` creates a new `ReplicaSet` and migrates to it gradually, keeping the old one scaled down with its revision intact. That history is what makes rollback a real operation rather than a re-deploy prayer: every revision is still in the API with its exact template.

The rollout defaults are a good production baseline: `max Surge` of 25 percent and `max Unavailable` of 25 percent mean a four-replica `Deployment` always keeps at least three `Ready` during an update. Tune them per service: stateless frontends can surge aggressively, while a service that hates duplicate traffic may prefer `maxUnavailable` over surge. Progress is tracked in status conditions, and a stuck rollout, `ProgressDeadlineExceeded` after the timeout, is a first-class signal your readiness gates are failing, not a silent hang.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  labels: { app: api }
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  selector:
    matchLabels: { app: api }
  template:
    metadata:
      labels: { app: api }
    spec:
      containers:
        - name: api
          image: myorg/api:1.4.0
          ports: [ { containerPort: 8080 } ]
          readinessProbe:
            httpGet: { path: /healthz, port: 8080 }
            initialDelaySeconds: 3
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /healthz, port: 8080 }
            initialDelaySeconds: 20
            periodSeconds: 15
          startupProbe:
            httpGet: { path: /healthz, port: 8080 }
            failureThreshold: 30
            periodSeconds: 5
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits:   { cpu: 500m, memory: 256Mi }
```

## 4.4 Health Probes

Three probes give the cluster eyes on your process. The startup probe gates the other two, retrying until the application first becomes healthy, which is how you give a slow-booting JVM five minutes without lying to the liveness check. The readiness probe answers: should traffic be sent to this `Pod` right now, and failing it removes the `Pod` from Services without restarting anything, which is the correct response to a lost database connection. The liveness probe answers: is this process wedged beyond recovery, and failing it restarts the container, the correct response to a deadlock, and only that.

Probe discipline prevents self-inflicted outages. Point liveness at something cheap and internal, never at a dependency: a liveness check that queries the database turns a database blip into every `Pod` restarting at once. Since v1.32 a sleep action lets a liveness probe pause deliberately before failing, useful for graceful shutdown windows. Give every `Deployment` a readiness probe; the cluster routes by it, and without one, a `Pod` is traffic-ready the instant the process starts, which is rarely when the application is.

## 4.5 Resource Requests, Limits, and QoS

Requests are what the scheduler books on a node; limits are the ceiling the `kubelet` enforces at runtime. A `Pod` that requests `100m` CPU and `128Mi` memory reserves exactly that against node capacity, while a memory limit of `256Mi` means exceeding it ends the container with an OOMKill, exit code 137, rather than endangering neighbors. CPU limits throttle instead of killing, which is why many operators set CPU requests without limits and let workloads burst, reserving hard memory limits as the real safety line. The three QoS classes fall out of the settings: `Guaranteed` where requests equal limits, `Burstable` when requests are lower, `BestEffort` when neither is set, and the class decides eviction order under node pressure in Chapter 10.

Vertical scaling of running Pods no longer requires a restart: in-place pod resize, GA since v1.33, lets you edit resources on a running `Pod` and have the `kubelet` apply the new values when the container runtime and node allow it. It pairs naturally with the `VerticalPodAutoscaler` in Chapter 10, but the direct form is worth knowing: `kubectl edit pod` with a `resources` change, watching the resize status in the `Pod`'s conditions. Not every combination is resizable in every environment, so treat it as a right-sizing tool, not a license to skip capacity planning.

::: {.lab}
### Lab 2 - The full workload lifecycle {#lab2}

1. Apply the api `Deployment` from Section 4.3 against your `kind` cluster. Watch `kubectl rollout status deployment/api` until complete, then confirm the three probes appear in `kubectl describe pod` events.
2. Ship a bad release on purpose: apply the same manifest with image `myorg/api:9.9.9`. Run `kubectl get pods` and explain the `ImagePullBackOff` you see, then watch `kubectl rollout undo deployment/api` restore the previous revision from history.
3. Test readiness honestly: delete the `readinessProbe` block, re-apply, and use `kubectl get endpoints` or `kubectl get pods --show-labels` during the rollout to see how traffic-readiness differs. Restore the probe afterwards.
4. Trigger self-healing twice: `kubectl delete pod -l app=api` for the `ReplicaSet` controller, then `kubectl exec` into one `Pod` and kill PID 1 for the liveness probe. Note which actor fixed each failure and how the restart counts change.
5. Right-size with evidence: run `kubectl top pods` (after installing `metrics-server` per Chapter 12 if needed), compare against the requests you set, and adjust one value using in-place resize via `kubectl edit pod`, observing the resize condition on the `Pod`.
:::

::: {.note}
**Best practice**

Treat the `Deployment` manifest as the whole truth of a service: `image`, probes, `resources`, and `strategy` live in git, and `kubectl` rollout operations are the only hand edits you allow in production. Rollback is then a reviewable action with a manifest commit attached, and the revision history in the cluster matches the history in your repository instead of diverging from it.
:::

**See also:** [Chapter 5](#ch5) for the configuration these pods consume, [Chapter 10](#ch10) for how the scheduler places them, and [Chapter 14](#ch14) for rollouts you can undo.
