# Chapter 10 - Scheduling, Autoscaling, and Resource Management {#ch10}

Chapter 4 taught you to ask for resources; this chapter covers who grants them and what happens when they run out. The scheduler's decisions, the `kubelet`'s evictions, and the three autoscalers form one resource economy: requests are currency, capacity is supply, and every outage in this domain is a mismatch between the two. Understanding the mechanisms turns capacity planning from superstition into configuration, and autoscaling from a checkbox into an architecture decision with real trade-offs.

## 10.1 How the Scheduler Decides

For every unscheduled `Pod` the scheduler runs two phases. Filtering removes nodes that cannot host the `Pod`: insufficient unreserved CPU or memory, `nodeSelector` and `affinity` mismatches, taints without matching `tolerations`, and topology constraints the `Pod` cannot satisfy. Scoring ranks the survivors: spreading replicas across zones and nodes with topology spread constraints, honoring preferred `affinity`, bin-packing or spreading by scoring plugins, and reserving room for future scale. The winner gets the binding, and if no node passes the filter, the `Pod` stays `Pending` with the reason recorded in its events, which is why `Pending` diagnostics start with `kubectl describe pod` and its `FailedScheduling` line rather than with guesswork.

The steering tools deserve precise definitions because their names invite confusion. `nodeSelector` and `nodeAffinity` attract `Pods` to nodes by labels, the standard way to target GPU nodes or dedicated pools. Taints repel: a node marked with a taint admits only `Pods` carrying the matching toleration, which is how control planes stay protected and how dedicated tenants are built. `Pod` affinity and anti-affinity pull or push `Pods` relative to other `Pods`, and `topologySpreadConstraints` express the modern intent cleanly, keep at least one replica per zone, with the `maxSkew` knob deciding how strict. The honest guidance: label pools, taint specials, spread everything user-facing, and never encode hope as hard `affinity`, because constraints that cannot be satisfied silently cap your replicas.

## 10.2 Node Pressure, Eviction, and Priority

When a node runs short of memory or disk, the `kubelet` becomes the enforcer: it ranks its `Pods` by usage relative to requests and by QoS class from Chapter 4, and evicts from the bottom, `BestEffort` first, `Burstable` above request next, `Guaranteed` last. This is why requests are not paperwork: a `Pod` whose requests reflect real usage is protected by its honesty, while a `Pod` that lied low gets evicted first and deserved it. Memory limits interact here too: exceeding a hard limit is an OOMKill inside the node rather than an eviction, and Chapter 4's exit code 137 is the fingerprint. `PriorityClasses` add a deliberate override for the essential few: a high-priority controller can preempt lower-priority `Pods` when capacity is tight, which is why `kube-system` runs PriorityClass-protected and why you should create your own for anything the business calls critical.

## 10.3 Horizontal Pod Autoscaling

The `HorizontalPodAutoscaler` changes replica counts against measured load. Its plumbing matured quietly: the metrics API that feeds it, `metrics.k8s.io`, reached GA in v1.37, so the `kubectl top` and HPA path no longer rests on beta APIs. The standard HPA scales on CPU or memory utilization against requests, which is another reason honest requests matter, and custom or external metrics, queue depth, requests per second, extend it through the metrics adapters. The `behavior` block makes ramp intent explicit: `scaleUp` policies with stabilization windows prevent flapping, and `scaleDown` controls how quickly capacity drains after a spike, which for many services is the more delicate operation.

Two edges of the HPA need awareness rather than heroics. Scaling to zero, attractive for spiky and event-driven workloads, arrives as an alpha feature in v1.37 and belongs in labs, not yet in production paths, with Knative-style platforms as the mature alternative. And the HPA's floor and ceiling, `minReplicas` and `maxReplicas`, are real architecture decisions: set the floor to survive a zone loss, set the ceiling where the database or the budget actually breaks, and revisit both with the load tests from Chapter 12 rather than during the incident.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: api, namespace: prod }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: api }
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 70 }
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies: [ { type: Percent, value: 100, periodSeconds: 60 } ]
    scaleDown:
      stabilizationWindowSeconds: 300
      policies: [ { type: Pods, value: 2, periodSeconds: 60 } ]
```

## 10.4 Vertical Scaling and Cluster Autoscaling

The `VerticalPodAutoscaler` answers a different question: not how many replicas, but how much per `Pod`. In recommendation mode it watches real usage and writes its numbers into status for you to review, which is the safest and most useful form; the automatic modes rewrite `Pod` resources directly, and since in-place resize is GA as of v1.33, a VPA-guided rightsizing loop no longer forces a restart on every adjustment. The productive pairing is recommendation mode plus a periodic review: let the VPA measure, let a human approve, and let the deployment change ship like any other.

When `Pods` cannot schedule because nodes are full, the Cluster Autoscaler adds nodes from a pool, and when nodes idle below utilization for a sustained window it removes them, respecting PDBs from Chapter 14 and `Pod` priorities. Karpenter, now the CNCF-bred alternative, skips pre-provisioned pools: it watches `Pending` `Pods` directly and launches exactly-sized instances, consolidating continuously as load shifts. The trade-offs are real: Cluster Autoscaler is predictable and pool-bound, Karpenter is faster to fit and cheaper on diverse workloads but couples you to its own CRDs and consolidation behavior. Either way, pair node autoscaling with `PodDisruptionBudgets` and requests hygiene, because an autoscaler amplifies whatever truth, or fiction, your requests tell it.

| Autoscaler | Changes | Signals | Watch out for |
| ----------- | ------------- | ------------- | ------------- |
| HPA | Replica count | CPU/memory utilization, custom metrics | Requests honesty; scale-down flapping |
| VPA | Per-Pod resources | Actual usage over time | Use recommendation mode first; resize needs GA in-place or restarts |
| Cluster Autoscaler / Karpenter | Node count | `Pending` `Pods`, idle capacity | PDB interactions; zone balance; cost visibility |

: Table 10.1 - The three autoscalers

::: {.note}
**Best practice**

Give every namespace a `ResourceQuota` and a `LimitRange` as soon as more than one team deploys into it. Quotas cap the total requests and limits, making capacity a team-level conversation instead of a cluster-wide surprise, and `LimitRanges` stop the unbounded default `Pod` that requests nothing and evicts first. The autoscalers from this chapter assume a well-formed economy; quotas are what keep the economy honest.
:::

**See also:** [Chapter 4](#ch4) for the workloads being scheduled, [Chapter 11](#ch11) for the workloads that cannot be rescheduled freely, and [Chapter 12](#ch12) for the metrics autoscaling depends on.
