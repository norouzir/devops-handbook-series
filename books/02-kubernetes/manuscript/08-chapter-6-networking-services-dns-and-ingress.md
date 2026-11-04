# Chapter 6 - Networking: Services, DNS, and Ingress {#ch6}

Kubernetes networking has two layers, and keeping them separate in your head makes the whole subject easier. The lower layer is the pod network: a flat, routable space where every `Pod` can reach every other `Pod` without NAT, implemented by the CNI plugin on every node. The upper layer is `Service` discovery and ingress: stable virtual IPs, DNS names, and HTTP routing that stand in front of Pods, which are ephemeral by design. This chapter builds the lower layer just enough to reason about failures, then spends most of its time on the upper layer where daily work happens.

## 6.1 The Pod Network and CNIs

The contract of the pod network is simple: Pod-to-Pod traffic across nodes arrives without NAT, and each `Pod` sees itself as its own IP's owner. Every CNI plugin satisfies the contract differently, and the differences are operational choices rather than trivia. Flannel hands out routes and keeps it simple; Calico adds policy enforcement and BGP routing options; Cilium replaces the packet path with eBPF programs and adds observability and load balancing in the kernel. Whatever the plugin, the node's routing behavior is where connectivity mysteries end up, and `kubectl describe node` plus the CNI's own diagnostics are the first stop when Pods cannot talk across nodes.

## 6.2 Services: Stable Virtual IPs

A `Service` is a stable address in front of a moving set of Pods, selected by labels. `ClusterIP`, the default, allocates a virtual IP reachable inside the cluster, and the moment it exists `CoreDNS` serves a DNS name for it. `NodePort` opens the same `Service` on every node at a high port, useful for demos and edge cases; `LoadBalancer` asks the platform, the cloud controller or MetalLB on bare metal, for a real external IP pointed at the `Service`. `ExternalName` is the odd one out, a DNS `CNAME` in disguise. Behind the address, endpoints track the live, ready Pods, which is why readiness probes from Chapter 4 are load-balancing decisions, not just health niceties.

| Type | Reachable from | Typical use |
| ----------- | -------------------- | ------------------- |
| `ClusterIP` | Inside the cluster | Internal service-to-service traffic; the default |
| `NodePort` | Outside, node IP + high port | Demos, labs, legacy firewall allowances |
| `LoadBalancer` | Outside, one provider IP | Public or partner-facing TCP/HTTP services |
| `ExternalName` | Inside cluster | DNS alias to an external hostname during migrations |

: Table 6.1 - Service types at a glance

How the virtual IP becomes real traffic depends on the node's data plane. `kube-proxy` in `iptables` mode programs NAT rules per `Service`, the long-standing default; `nftables` mode, GA since v1.33, replaces those rules with a more efficient `nftables` pipeline and is worth opting into on modern kernels; Cilium can take the whole job into eBPF. You rarely tune this by hand, but you should know which mode your cluster runs, because `Service` behavior under large scale, and some subtle timeout behaviors, differ between them, and the `kube-proxy` `Pod` logs are the diagnostic source when a `ClusterIP` answers but its backends do not.

## 6.3 Cluster DNS

`CoreDNS` turns Services into names, and the name grammar is worth memorizing: a `Service` in your namespace answers at `service-name`; another namespace needs `service-name.other-namespace`; the fully qualified form appends `svc.cluster.local`. Pods get search domains so short names resolve locally first, which is exactly why cross-namespace access usually fails with a lookup error until you use the qualified name. DNS-dependent outage patterns follow: a `Service` name that resolves but connects nowhere means empty endpoints, while a name that does not resolve at all usually means a namespace or selector typo. Chapter 12 shows how to watch DNS health itself, because when `CoreDNS` struggles, everything that depends on names struggles with it.

## 6.4 Ingress and the Gateway API

Services are Layer 4 addresses; HTTP deserves smarter routing, and that is the ingress layer. An `Ingress` object declares host and path rules, and an ingress controller, ingress-nginx being the most common, implements them as reverse-proxy configuration with TLS termination. The model works but showed its age: annotations grew controller-specific, and cross-namespace or advanced traffic management outgrew the original API. The Gateway API is the designed successor, and by v1.5, released in February 2026, its `Gateway`, `HTTPRoute`, and `GRPCRoute` resources are the stable, expressive standard: a `Gateway` declares listeners on the infrastructure layer, HTTPRoutes attach to it by reference, and roles can be split so platform teams own Gateways while app teams own Routes without annotations.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: public
  namespace: infra
spec:
  gatewayClassName: nginx
  listeners:
    - { name: http, port: 80, protocol: HTTP }
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api
  namespace: prod
spec:
  parentRefs:
    - { name: public, namespace: infra }
  hostnames: [ "api.example.com" ]
  rules:
    - matches: [ { path: { type: PathPrefix, value: / } } ]
      backendRefs:
        - { name: api, port: 8080 }
```

::: {.note}
**Best practice**

For new HTTP workloads in 2026, start with the Gateway API and keep `Ingress` knowledge for the estates that already run it. The stable resources cover TLS, header rewrites, weighted traffic, and cross-namespace delegation, and the same objects are what progressive delivery tools in Chapter 13 drive for canary releases, so learning one API serves both routing and rollout day.
:::

**See also:** [Chapter 4](#ch4) for the pods behind every Service, [Chapter 9](#ch9) for NetworkPolicy, and [Appendix C](#appC) for the debugging loop when DNS is the suspect.
