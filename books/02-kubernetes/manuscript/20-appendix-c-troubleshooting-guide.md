# Appendix C - Troubleshooting Guide {#appC}

This appendix is organized by the symptom you see, not by the component that caused it, because at 3 a.m. you know the former. Each section gives the quick read, the usual causes in order of frequency, and the fix path. The universal first commands are `kubectl get pods -A` and `kubectl get events -A --sort-by=.lastTimestamp`; run them before anything else.

## C.1 ImagePullBackOff and ErrImagePull

The `kubelet` cannot fetch the image, and `describe` names the exact reason. The causes in order: the tag does not exist (typo, or CI never pushed), the registry requires credentials and `imagePullSecrets` is missing or wrong, a private registry needs a CA or is listed in the runtime's `insecure-registries`, and rate limiting, which anonymous Docker Hub pulls hit famously. The fix path: read the event line for the underlying error, verify the image exists with a local pull, then align secrets: create a pull secret from a registry login and attach it via `imagePullSecrets` or a `ServiceAccount`. In `kind` clusters, remember images must be loaded with `kind load docker-image` or pulled from a reachable registry.

## C.2 CrashLoopBackOff

The container starts and exits, repeatedly, with exponential backoff between attempts. First read the current logs with `kubectl logs`, then the previous attempt with `-p`, because the crash before the crash often carries the real error: a missing environment variable, an unreachable dependency at boot, a config file that failed to parse. If logs are empty, the process died before logging, so `exec` a shell into the image variant with a `sleep` command or check exit codes: 1 is application failure, 137 is OOMKill or kill signal, 126/127 are command problems. Misconfigured probes also cause this shape, a liveness probe too aggressive for a slow boot kills healthy-but-slow Pods forever; the fix is a `startupProbe`, not a longer liveness timeout.

## C.3 Pod Stuck Pending

The scheduler has not placed the `Pod`, and its events say which constraint failed. Insufficient cpu/memory means the requests exceed free capacity anywhere: reduce requests, delete hogs, or add a node, and check for a `ResourceQuota` in the namespace, which fails with a different, quota-specific event. `Unschedulable` taints means `affinity` or `tolerations` exclude every node, common after a mis-scoped `nodeSelector`. Volume topology errors route to Chapter 7's PVC diagnosis. Persistent three-replica `Pending` with an autoscaler present is the intended trigger for the Cluster Autoscaler or Karpenter, so confirm their logs show the decision.

## C.4 OOMKilled and Exit Code 137

The container exceeded its memory limit and the kernel killed it. Confirm in `describe`: `Last State` shows `Reason: OOMKilled`. The honest fix is more memory limit or less memory use: check for a leak with the memory-vs-limit query from Chapter 12, remember that JVM and language runtimes need heap plus non-heap headroom, and note that in-place resize (GA since v1.33) can raise a limit without a restart on modern runtimes. A `Pod` that flaps `OOMKilled` under load alone is a capacity finding, not a mystery; record the measured peak from metrics and set the limit above it with headroom.

## C.5 Service Unreachable or DNS Failures

Split the failure by layer. If the `Service` name does not resolve, you are in DNS: cross-namespace lookups need the qualified name, namespace-local short names fail if the `Service` is elsewhere, and `CoreDNS` health is the next check. If it resolves but connects nowhere, endpoints are empty: the `Service` selector does not match the `Pod` labels, or no `Pod` is `Ready`, which loops back to readiness probes. If it connects but drops intermittently, look at `kube-proxy` mode and the CNI: `nftables-mode` and eBPF data planes behave differently under scale, and conntrack exhaustion on busy nodes is the classic silent dropper. Run a network debug `Pod` for on-the-spot tests: `nslookup` for DNS, `curl` to the `Service` and to a specific `Pod` IP, isolating `Service` machinery from backend health.

## C.6 Ingress or Gateway Returns 503/404

A 404 usually means the hostname and path rules never matched: check the `Ingress` or `HTTPRoute` host against what the client sends, and confirm the resource is attached to the right `Gateway` or `IngressClass`. A 503 means routing matched but no healthy backend exists, which is the empty-endpoints problem one layer up, or TLS termination issues if the 503 comes from the controller itself. In ingress-nginx, the controller's own logs and its `/healthz` separate controller health from backend health, and the annotation spelling trap, annotations are controller-specific, sends many manifests to silently correct-looking no-ops.

## C.7 Node NotReady

A node stops reporting, and after the grace period the controller taints it and starts evicting Pods. The chain to check: `kubelet` running on the node, node's disk not full, certificates not expired (`kubeadm` clusters older than a year earn this one), and the container runtime healthy. `kubectl describe node` shows conditions and the `kubelet`'s last heartbeat; from the node, `systemctl status kubelet` and `journalctl -u kubelet` are the ground truth. Pods from a `NotReady` node reappear on other nodes only if their controller owns them, which is one more reason bare Pods are reserved for experiments.

## C.8 PVC Stuck Pending

A claim with no volume behind it waits in `Pending`, and the events name the blocker: no `StorageClass` matched, the named class's provisioner is not installed, capacity in the requested zone is exhausted, or `WaitForFirstConsumer` is correctly waiting for a `Pod` that itself cannot schedule, the circularity from Chapter 7. The fixes are equally specific: point the claim at an existing class, install or repair the CSI driver, or move the workload's topology constraints so a valid zone exists. After a `StatefulSet` scale-down, retained volumes make re-scale look like instant recovery; verify the old data story is what you actually want before celebrating.
