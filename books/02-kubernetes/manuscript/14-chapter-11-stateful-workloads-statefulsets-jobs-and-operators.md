# Chapter 11 - Stateful Workloads: StatefulSets, Jobs, and Operators {#ch11}

Everything so far assumed `Pods` are interchangeable, and for request-handling services they should be. Databases, queues, and batch pipelines break that assumption in specific ways: they need identities that survive rescheduling, storage bound to a particular member, and start-stop order that respects replication. Kubernetes answers with three workload kinds, `Jobs` for work that must happen, `StatefulSets` for members that must persist, and the operator pattern for products that bring their own expertise. This chapter covers all three, then closes with the judgment call every team eventually faces: what belongs in the cluster, and what is better left to a managed service.

## 11.1 Jobs and CronJobs

A `Job` runs `Pods` until a task completes successfully the specified number of times: `completions` sets how many successes you want, `parallelism` how many may run at once, `backoffLimit` how many failed `Pods` you tolerate before the `Job` is marked failed, and `activeDeadlineSeconds` the hard wall-clock ceiling. The `Pod`'s own `restartPolicy` must be `Never` or `OnFailure` for a `Job`, because the semantics belong to the `Job` controller, not the `kubelet`. Set `completionMode: Indexed` when workers need to know which shard they own, and `ttlSecondsAfterFinished` to clean up completed `Jobs` and their `Pods` automatically, which keeps your namespace from becoming a `Job` museum.

A `CronJob` adds a schedule in standard cron syntax plus the `concurrencyPolicy` decision that every scheduled job eventually needs: `Allow` lets overlapping runs pile up, `Forbid` skips a tick if the previous run is still going, and `Replace` kills the old run and starts fresh. Set `startingDeadlineSeconds` so a suspended controller does not fire a month of missed runs at once, and remember the timezone lesson from every production system: the schedule runs in the controller's time, so pin the timezone your business actually means rather than the one the cluster happens to use.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: nightly-report, namespace: batch }
spec:
  schedule: "30 2 * * *"
  timeZone: "Europe/Berlin"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 300
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600
      ttlSecondsAfterFinished: 86400
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: report
              image: myorg/report:2.1.0
```

## 11.2 StatefulSets: Identity and Order

A `StatefulSet` gives each `Pod` a stable identity that survives rescheduling: `data-0` is always `data-0`, with the same DNS name through a headless `Service` and, via `volumeClaimTemplates`, the same `PersistentVolume` reattached wherever the `Pod` lands. Compare that to a `Deployment`, where a replaced `Pod` gets a new random name and a new claim; replication protocols that depend on member identity, which is most of them, simply do not work that way. The ordering controls are equally deliberate: `podManagementPolicy: OrderedReady` starts members one at a time and waits for each to be `Ready`, the safe default for databases that elect leaders, while `Parallel` trades ordering for startup speed where the application coordinates itself.

Operating `StatefulSets` well means knowing which knobs affect which members. Updates roll from the highest ordinal down by default, and `partition: N` during `rollingUpdate` pins the change to members N and above, the mechanism for canarying a new version on one replica of a three-member database before committing. Scaling down deletes the highestordinal `Pod` and leaves its `PersistentVolume` behind, which is why reclaim policy from Chapter 7 matters doubly here: scale-down is not data deletion unless your policies say so, and scale-up reattaches the retained volume, sometimes with months of stale data that the application must handle. Deletion semantics are the sharp edge: deleting the `StatefulSet` does not delete the `Pods`' volumes, and deleting a claim does, so write the runbook while calm.

| Property | Deployment | StatefulSet |
| -------------- | ------------------ | ------------------ |
| `Pod` identity | Random suffix, replaceable | Stable ordinal, e.g. `data-2` |
| DNS names | Via `Service`, load-balanced | Per-member via headless `Service` |
| Storage | Shared or ephemeral | Per-member PVC from template, reattached on move |
| Start order | Parallel, no meaning | `Ordered` (or `Parallel`) with readiness gates |
| Typical uses | APIs, frontends, workers | Databases, queues, coordinators, brokers |

: Table 11.1 - `Deployment` versus `StatefulSet`

## 11.3 Databases on Kubernetes: The Judgment Call

The honest answer to should we run our database on Kubernetes is usually: not the first one. A managed database service inherits backup, failover, patching, and point-in-time recovery from the provider, and Chapter 7's storage machinery does not reproduce that for free. The self-hosted case is legitimate when you need a version or configuration the managed service does not offer, when data locality or compliance keeps the bytes in-house, or when the workload is already multi-cloud by design. If you self-host, run an operator, not raw `StatefulSets`, because the delta between running Postgres and operating Postgres is exactly the knowledge an operator encodes.

## 11.4 The Operator Pattern

An operator is Chapter 1's control loop applied to a product: a Custom Resource Definition introduces a kind, say `PostgresCluster`, and a controller watches those objects and reconciles the real cluster, `StatefulSet`, `Services`, credentials, backups, failover, toward the spec. The value is that operational knowledge becomes code: version upgrades, replica promotion, and backup schedules are fields on the CR, executed the same way every time, and reviewed as configuration rather than performed as rituals. The mainstream ecosystem is operator-first, from Postgres and MySQL operators to Strimzi for Kafka and `cert-manager` for certificates, and evaluating an operator is evaluating its upgrade story and backup integration above its install one-liner.

Writing your own operator is a genuine option once a workflow repeats: the `controller-runtime` framework and the `kubebuilder` scaffolding make the watch-and-reconcile loop approachable, and your team's deployment choreography, migrate, scale, verify, is exactly the kind of logic that benefits from being encoded once. Keep the boundary in sight, though: an operator that only wraps a `Deployment` adds indirection without knowledge, and a controller is a long-running service with its own upgrade and RBAC story, which is why most teams should consume operators before they author one.

::: {.note}
**Best practice**

For any stateful operator you adopt, rehearse the three emergencies in a non-production cluster before the first production install: a single-replica loss, a full-node loss with volume reattachment, and a version upgrade with rollback. The operator's behavior in those three moments, not its feature list, is what you are buying, and the rehearsal is cheap insurance against learning the answer during an outage.
:::

**See also:** [Chapter 7](#ch7) for the storage primitives underneath, [Chapter 14](#ch14) for backups of state you cannot recreate, and [Chapter 12](#ch12) for observing these workloads once they spread out.
