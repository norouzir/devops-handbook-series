# Chapter 7 - Storage: Volumes, PVCs, and StorageClasses {#ch7}

The Docker book's storage chapter ended with a principle: containers are disposable, data is not, and the boundary between them is a volume. Kubernetes formalizes that boundary into a small API with strong opinions: Pods declare what they need through `PersistentVolumeClaims`, the cluster supplies actual storage through `PersistentVolumes`, and `StorageClasses` define how new volumes get created. This chapter covers the machinery and, more importantly, the judgment: which storage class fits which workload, and why the honest answer for many databases is still the one from Chapter 11.

## 7.1 Volume Types and Pod Lifetime

Inside a `Pod`, volumes solve two distinct problems. Lifetime volumes tie data to the `Pod`'s existence: `emptyDir` is scratch space created when the `Pod` is scheduled and destroyed with it, ideal for spool files, caches, and sidecar communication; it lives in the node's disk or, with the `medium: Memory` setting, in `tmpfs` for speed at the cost of memory pressure. `HostPath` mounts a node directory into the `Pod` and is the volume type to treat with suspicion: it couples the `Pod` to a specific node's filesystem, breaks the scheduler's freedom, and is a known container-escape vector, which is why Pod Security Admission in Chapter 9 restricts it by default. Legitimate `hostPath` uses, such as `DaemonSets` reading node logs, exist and are easy to recognize; everything else should raise an eyebrow.

`Projected` volumes compose several sources into one mount: `Secrets`, `ConfigMaps`, and `downwardAPI` information can land in a single directory, refreshed by the `kubelet`. The service account token you will meet in Chapter 9 arrives this way, with audience and expiry set, and the pattern of mounting a token with a bounded lifetime instead of the eternal legacy token is one of the quiet security wins of modern Kubernetes. For the rest of this chapter, the interesting volumes are the ones that outlive Pods entirely.

## 7.2 PersistentVolumes and Claims

The `PV/PVC` split separates roles deliberately. A `PersistentVolume` describes a piece of real storage: `capacity`, how it can be attached, and what happens when its claim is released. A `PersistentVolumeClaim` is a user's request: how much, which access modes, which class. Kubernetes binds matching claims to volumes, and the `Pod` mounts the claim, so application authors never name a disk, a path, or a cloud volume ID; they ask for `20Gi` of read-write-once storage and mount what arrives. Access modes describe topology, not concurrency permissions: `RWO` means one node at a time, `ROX` read-only from many, `RWX` read-write from many, the mode that network file systems provide and most block storage does not.

| Setting | Values | Meaning in practice |
| ------------ | -------------- | ------------------------ |
| `accessModes` | `RWO`, `ROX`, `RWX` | `RWO` fits databases and most apps; `RWX` requires a file store (NFS, EFS, Azure Files) and enables shared workloads |
| `reclaimPolicy` | `Retain`, `Delete` | `Retain` keeps the volume and its data after the claim is deleted; `Delete` provisions a cleanup, the default for dynamically provisioned volumes |
| `volumeBindingMode` | `Immediate`, `WaitForFirstConsumer` | `WaitForFirstConsumer` delays binding until a `Pod` exists, so topology-aware storage lands in the right zone |

: Table 7.1 - Access modes and reclaim policies

The reclaim policy is where data-loss stories begin. Dynamic provisioning defaults to `Delete`: when someone deletes a `StatefulSet` and its claims, the underlying volumes are destroyed on a schedule, not always immediately but reliably. Production databases deserve `Retain`, plus a backup story from Chapter 14, because reclaim policies are recovery instructions written in advance. Deleting a claim is a data operation even when the YAML makes it look like tidying.

## 7.3 StorageClasses and Dynamic Provisioning

A `StorageClass` is a named recipe for creating volumes: which CSI driver to call, what performance tier to request, whether volumes bind immediately or wait for a consumer, and what reclaim policy to default to. When a claim names a class, the cluster's CSI driver provisions a real volume on demand, and the cloud's `gp3`, `premium-rwo`, or `managed-csi` classes are just recipes someone wrote. The class marked default serves claims that name none, which makes class hygiene a fleet-level decision: name classes after intent, like `fast-replicated` or `cheap-bulk`, keep the default conservative, and let `StatefulSets` select explicitly via their `volumeClaimTemplates` so a workload's storage intent travels with its manifest.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-replicated
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
---
# a claim that uses it
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: api-data }
spec:
  storageClassName: fast-replicated
  accessModes: [ "ReadWriteOnce" ]
  resources: { requests: { storage: 20Gi } }
```

Two lifecycle operations round out daily work. `allowVolumeExpansion: true` on the class enables growing a claim by editing its `spec`, and modern block storage grows in place; shrinking is still not supported, so size generous and verify with a growth drill before you need one. Volume snapshots, a CSI capability, capture point-in-time copies as API objects and are the material Chapter 14's backup strategy is built from; a snapshot schedule attached to each stateful workload is the difference between a restore story and a resignation letter.

## 7.4 Choosing Storage for Workloads

The decision sequence for any stateful workload is short and worth internalizing. First ask whether the data must live in the cluster at all: managed databases, object storage, and external caches remove the entire operational class of backup, failover, and version upgrades, which is why Chapter 11 treats managed data services as the default answer for most teams. If it must live in-cluster, match access mode to reality: single-writer workloads are `RWO` block storage, shared-file workloads are `RWX` network file systems, and pretending `RWO` is enough for two busy writers fails the moment the scheduler co-locates them. Finally, match performance to measurement, not marketing: provision from the class whose IOPS and throughput match a load test, because storage classes differ in real, billable ways.

::: {.warn}
**Watch out**

A `Pending` `PVC` is a scheduling problem in disguise, and the events tell the story: a claim bound to a zone the `Pod` cannot reach, a `WaitForFirstConsumer` volume waiting for a `Pod` that itself waits for the volume, or a class whose driver is not installed on the node. Before touching the workload, read `kubectl describe pvc`; nine times out of ten the fix is a storage class or topology setting, and the tenth time it is a misconfigured `Pod` that can never schedule where its data lives.
:::

**See also:** [Chapter 4](#ch4) for the pods that claim these volumes, [Chapter 11](#ch11) for state that needs more than a PVC, and [Appendix C](#appC) for the pending-claim debug loop.
