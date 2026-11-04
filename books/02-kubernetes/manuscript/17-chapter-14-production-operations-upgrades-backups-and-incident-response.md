# Chapter 14 - Production Operations: Upgrades, Backups, and Incident Response {#ch14}

Everything before this chapter built the cluster; this chapter keeps it alive. Operations is where Kubernetes pays its learning debt in installments: every four months a new minor arrives, nodes fail on their own schedule, and the incident you did not rehearse is the one you will debug at 3 a.m. The material is deliberately practical, the upgrade sequence, the drain-and-PDB dance, the `etcd` snapshot, and the incident playbook, and it closes the book the way operations closes its weeks: with a drill, not a plan.

## 14.1 Upgrade Discipline

Kubernetes supports three minors at a time, and v1.34 exits support on October 27, 2026, which makes the policy concrete: a cluster that skips a window becomes unsupported in a season. Version skew rules shape every upgrade: `kubelet`s may lag the API server by up to three minors, and components upgrade in order, control plane first, then nodes, then add-ons, because an add-on expecting a newer API than the control plane serves is the classic self-inflicted outage. The `kubeadm` sequence is therefore a ritual worth scripting: `drain` the control plane, upgrade `kubeadm` and the control plane binaries, validate, then walk worker nodes one at a time, and finally reconcile every add-on, CNI, ingress controller, cert-manager, against their compatibility matrices.

```bash
# kubeadm minor upgrade walkthrough (control plane on 1.36 -> 1.37)
sudo apt-get update
sudo apt-get install -y kubeadm=1.37.* --allow-change-held-packages
kubeadm upgrade plan
sudo kubeadm upgrade apply v1.37.1

# node-by-node (from an admin machine, one worker at a time)
kubectl drain node-2 --ignore-daemonsets --delete-emptydir-data
sudo apt-get install -y kubeadm=1.37.* kubelet=1.37.* kubectl=1.37.* \
  --allow-change-held-packages
sudo kubeadm upgrade node
sudo systemctl restart kubelet
kubectl uncordon node-2
kubectl get nodes   # confirm versions and Ready
```

On managed clusters the same discipline applies with less soldering: the provider patches the control plane on your schedule request, but your nodes, your add-ons, and your API deprecations are yours, and EKS, GKE, and AKS all publish end-of-standard-support dates that do not negotiate. Whichever model you run, the upgrade budget is cultural: four months per minor is not a deadline imposed by this book but the maintenance contract the ecosystem actually offers, and estates that treat it as such report boring upgrades, which is the goal.

## 14.2 Node Lifecycle: Drains and Disruptions

Taking a node out of rotation is a two-verb operation with one negotiation in the middle. `cordon` marks the node unschedulable so new Pods go elsewhere; `drain` evicts what is already there, and the eviction requests go through the API, which means they negotiate with PodDisruptionBudgets: a PDB allowing `minAvailable: 2` on a three-replica service caps voluntary disruption at one replica at a time, and `drain` waits, politely and indefinitely, until the budget allows the next eviction. The flags matter: `--ignore-daemonsets` because `DaemonSet` Pods belong to their node, `--delete-emptydir-data` because scratch volumes are disposable by definition. The anti-patterns are equally clear: forcing a drain past a PDB to save ten minutes converts planned maintenance into an unplanned outage, and running without PDBs at all means every drain is a gamble with every service on the node.

## 14.3 Backups and Disaster Recovery

Kubernetes has exactly one backup that only you can take: `etcd`. All desired state, every `Deployment`, `Secret`, and RBAC rule, lives there, and a snapshot is a single command against the `etcd` endpoint, schedulable with the `CronJob` machinery from Chapter 11 and restorable by restoring the snapshot directory and restarting the static control plane Pods. Two caveats keep the drill honest: `etcd` restores are cluster-state restores, best rehearsed on a scratch control plane, and they do nothing for the data your workloads store in PersistentVolumes, which is a separate, workload-level responsibility. Velero is the standard tool for that second half: it backs up Kubernetes objects and volume snapshots together, can target a second region or cluster, and its restore drills are the closest thing this ecosystem has to a fire evacuation.

```bash
# etcd snapshot (on a control plane node, with the etcdctl image)
ETCDCTL_API=3 etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save /backup/etcd-snap-$(date +%F).db
etcdctl snapshot status /backup/etcd-snap-$(date +%F).db -w table

# object + volume backup with Velero
velero backup create nightly-$(date +%F) --include-namespaces prod
velero restore create --from-backup nightly-2026-10-20 --wait
```

## 14.4 The Incident Playbook

Incidents in Kubernetes follow recognizable shapes, and the playbook is a fixed order of questions. Start with blast radius: `kubectl get pods -A` and `get nodes` tell you whether one service, one namespace, or the cluster is sick, because the fix differs completely. Cluster-wide symptoms route to the control plane and nodes first, `NotReady` nodes, API latency, `etcd` alarms, per Chapter 2's failure table. Namespace-scoped symptoms route to the workload: `kubectl describe pod` and its events answer `Pending` and scheduling mysteries, logs answer CrashLoops, and `kubectl get events --sort-by=.lastTimestamp` is the flight recorder of everything that just happened. The discipline that separates operators from firefighters is writing down the timeline as you go; the post-incident review reconstructs itself from it, and the action items that follow are what actually make next month's incident shorter.

Prepare the human layer with the same seriousness as the technical one. On-call rotations with a handoff note, runbooks linked from the alert itself, and a standing rule that incident channels record decisions, not just symptoms. The kapitan's test for your readiness is brutal and simple: pick an incident from this book, OOMKill storm, `Ingress` 503s, a stuck drain, and time a rehearsal with the dashboards, not with the source of truth in your head. Every minute you shave in rehearsal is a minute a customer never notices.

## 14.5 Capacity and Cost Hygiene

The last operations habit is financial, and Kubernetes makes it measurable: requests are your bill. Idle-but-reserved capacity, Pods requesting generous memory and using a tenth, is the largest line item in most estates, and Chapter 10's VPA recommendations plus a monthly rightsizing review claw it back without heroics. The second lever is deletion hygiene: completed Jobs, orphaned PVCs from scaled-down StatefulSets, forgotten test namespaces, all of which `kubectl` can enumerate and ttl policies can prevent. The third is buying deliberately: spot instances for stateless and batch, reserved capacity for the stateful core, and a dashboard that shows cost per namespace, because a platform that cannot explain its own bill eventually gets its budget, and its existence, questioned.

::: {.lab}
### Lab 5 - The operations drill {#lab5}

1. Take an `etcd` snapshot from your `kind` control plane following Section 14.3, note the file size, and verify it with `snapshot status`. Restore confidence, not the cluster: document the exact restore sequence for your setup as if a new colleague would execute it tonight.
2. Install Velero with the `kind` provider plugin or a local storage backend, create a backup of a namespace holding the `api` app and its `ConfigMap`, delete the namespace, and restore it. Confirm both workload and configuration returned intact.
3. Exercise disruption control: add a PDB with `minAvailable: 2` to the three-replica `api` `Deployment`, then `kubectl drain` one `kind` worker with the proper flags. Watch the evicted Pods reschedule and the drain wait on the budget; note what `--disable-eviction` would have done differently.
4. Run the upgrade ritual in miniature: create a second `kind` cluster pinned one minor behind, then upgrade it node-image by node-image with `kind`'s tooling, and record which steps from the `kubeadm` sequence have `kind` equivalents and which are abstracted away.
5. Close with the incident shape: delete the `api` `Deployment`'s `Service` selector label on purpose (drift), then find the fault using only `kubectl get endpoints`, `kubectl describe`, and your observability stack from Chapter 12. Time yourself; this is the 3 a.m. muscle.
:::

**See also:** [Chapter 3](#ch3) for cluster lifecycle from the other end, [Chapter 11](#ch11) for the state whose backups you are now testing, and [Chapter 13](#ch13) for the delivery path that ships these upgrades.
