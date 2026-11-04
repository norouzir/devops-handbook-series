# Chapter 8 - Container Networking {#ch8}

Networking is where container behavior becomes visible to the rest of the world, and where a surprising share of production incidents live: unreachable services, port conflicts, DNS that works in one container and not another, and firewalls that disagree with the daemon. This chapter builds the model - network namespaces, bridges, and the daemon's firewall rules - and then walks the drivers you will actually operate.

## 8.1 The Model: Namespaces, Bridges, and veth Pairs

Every container gets its own network namespace: private interfaces, routing table, and iptables view. To give those private stacks connectivity, the daemon creates a Linux bridge (by default `docker0`) and wires each container to it with a virtual ethernet pair - one end in the container, one end in the host bridge. Container-to-container traffic flows through the bridge; container-to-outside traffic is masqueraded through NAT; outside-to-published-port traffic is DNATed back to the container by rules the daemon programs. Almost every networking symptom you will debug reduces to one of those three flows being missing or misdirected - so when something fails, ask which flow you expected and inspect exactly that path.

## 8.2 The Default Bridge versus User-Defined Bridges

Out of the box, containers land on the default `bridge` network. It works, but it has two severe limitations: containers on it cannot resolve each other by name, and it is a single shared L2 segment for everything that did not ask for better. The professional rule is simple - create a user-defined bridge per application and attach containers to it explicitly:

```bash
docker network create appnet

docker run -d --name api --network appnet myorg/api:1.0
docker run -d --name db --network appnet -e POSTGRES_PASSWORD=x postgres:16-alpine

# DNS resolution by container name just works on user-defined bridges
docker exec api ping -c1 db

docker network inspect appnet   # see members and their addresses
```

On user-defined bridges the daemon's embedded DNS server (reachable from containers at `127.0.0.11`) resolves container names, service aliases, and network-scoped aliases automatically. This is the mechanism Compose uses to let a service reach `db:5432` by name, and it is why `--link` - the deprecated legacy mechanism that required restarts and order bookkeeping - should appear nowhere in your infrastructure. Containers may join several networks at once, which is how you compose, say, a private data network with a shared egress network.

## 8.3 Publishing Ports

Publishing is how the outside world reaches in, and `-p` has more nuance than its brevity suggests. `-p 8080:80` binds host 8080 on all interfaces; `-p 127.0.0.1:8080:80` binds only loopback - the right default for services that should be reachable only through a reverse proxy or an SSH tunnel on the host; `-p 8080:80/udp` selects the protocol; and `-P` publishes every EXPOSE'd port to random high ports, which is mostly useful in test harnesses. Multiple `-p` flags compose for multi-port services. Remember what publish does NOT do: it does not make a container reachable from other containers (that is network membership plus DNS), and it does not create firewall exceptions beyond what the daemon programs - host firewalls with their own policy chains (ufw, firewalld, cloud security groups) sit in front and must be configured deliberately, as the next section explains.

```
-p 8080:80                    # all interfaces, host 8080 -> container 80
-p 127.0.0.1:8080:80          # loopback only - proxy or SSH tunnel frontends this
-p 53:53/udp                  # protocol matters for DNS and game servers
-p 9000-9005:9000-9005        # ranges for multi-port workloads
```

## 8.4 The Daemon and the Host Firewall

The daemon programs the host firewall directly: it owns a DOCKER chain for its NAT and filtering rules and inserts a DOCKER-USER chain that is always evaluated first for traffic you want to constrain. That ordering is the cause of a classic surprise - a host firewall that claims to block a port while the published container port stays open, because the daemon's rules matched first. Anything you add to protect published containers goes in DOCKER-USER (by source IP, interface, or port), not in front of the DOCKER chain. Engine v28 and v29 modernized this story in two steps: hardened default behavior around published ports, and an experimental nftables backend enabled with `--firewall-backend=nftables` in daemon.json or the CLI flag - worth trialing on new hosts since iptables support is on a deprecation path, but verify your DOCKER-USER rules survive the translation before adopting it fleet-wide.

::: {.note}
**Best practice**

Bind management-plane and internal services to 127.0.0.1 and let a reverse proxy own the public interface. It shrinks the firewall conversation to one port and makes the proxy's TLS and auth policy the single front door.
:::

## 8.5 The Other Drivers: host, none, macvlan, overlay

Beyond bridges, four drivers cover the remaining cases. The `host` driver removes the namespace entirely - the container shares the host network stack, ports are just ports, and performance is native; it is legitimate for performance-critical agents and a bad habit everywhere else, because the container's isolation story shrinks to almost nothing. The `none` driver gives a container only a loopback interface - the sandbox extreme, useful for offline build steps and untrusted workloads. The `macvlan` driver attaches containers directly to the physical LAN, giving each a real MAC and IP in your subnet; it is the answer for legacy appliances that assume L2 adjacency and for DHCP-dependent software, at the cost of losing the daemon's NAT protections and consuming VLAN address space. The `overlay` driver builds encrypted (optionally) L2 networks spanning hosts and is the fabric of Swarm services; Kubernetes brings its own CNI-plugin fabrics instead. IPv6 support (`--ipv6` on networks, with ip6tables plumbing current on v29) is mature enough to enable per-network where your address plan needs it.

## 8.6 Troubleshooting Network Problems

Work the three flows in order. First, inside the container: is the interface there, is the route right (`docker exec c ip addr; ip route` - install iproute2 if the image is minimal), can it resolve names (`getent hosts db`)? Second, east-west: are both containers on the same user-defined network (`docker network inspect`), does the name resolve, is the target service listening on 0.0.0.0 rather than 127.0.0.1 inside the container - the single most common application-side mistake. Third, north-south: is the port published where you think (`docker port c`), is the host actually listening (`ss -lntp | grep 8080`), does curl work from the host before blaming the network, and does anything in DOCKER-USER or the corporate firewall disagree. Appendix C condenses this into a symptom-to-fix table for the failures that account for most real tickets: port already allocated, DNS failing in one container only, bind-mount permission denials mistaken for network issues, and firewall/NAT surprises.

::: {.lab}
### Lab 8 - Two services, one network {#lab8}

1. Create `docker network create labnet`, then start nginx and an alpine debug container on it; resolve the web server by name from the debug container with `getent hosts web`.
2. Start a second nginx on the default bridge and prove that name resolution works on labnet but not there; write the one-sentence rule this demonstrates.
3. Publish with `-p 127.0.0.1:8080:80` and confirm with `curl localhost:8080` from the host and connection refused from another machine (or by checking `ss -lntp`).
4. Inspect: run `docker network inspect labnet` and `docker exec` an `ip route` inside a container; sketch on paper which veth, bridge, and NAT rule carried your curl request.
:::

**See also:** [Chapter 9](#ch9) for Compose networks in practice, [Chapter 11](#ch11) for the networking model Kubernetes puts in its place, and [Appendix C](#appC) for the "it cannot reach the other container" family of bugs.
