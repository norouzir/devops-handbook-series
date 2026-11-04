# Chapter 10 - Compute and Networking: VPCs, Compute Engine, and Managed Instance Groups {#ch10}

## 10.1 VPCs: Global by Design, Regional by Subnet

The GCP VPC breaks the habit the two previous clouds built: it is a **global** resource. One VPC spans every region, its **subnets** are regional slices of its ranges, and a VM in Frankfurt and a VM in Tokyo can share a VPC and talk over the same L3 space - no peering, no transit gateway, just one network object. The consequences run through everything: IP planning is a global exercise done once, "multi-region network" is the default rather than a project, and the per-VPC regionalism of AWS and Azure becomes a deliberate choice rather than gravity. The daily CLI stays familiar:

```bash
gcloud compute networks create vpc-shopnow \
  --subnet-mode=custom

gcloud compute networks subnets create snet-eu-dev \
  --network=vpc-shopnow --region=europe-west3 \
  --range=10.10.0.0/20

gcloud compute routes list --filter="network:vpc-shopnow"
```

Firewalls follow the same one-object model: **firewall rules** live on the VPC (stateful, default-deny on ingress except the default network's rules) and select their targets by **network tags** or by service account - `--target-tags=web`, `--source-ranges=10.10.1.0/24`, `--allow=tcp:443`. Tags are the security-group abstraction of GCP: attach the tag to the instances that share a role, write rules against the tag, and the rules stay readable in a way that neither SG IDs nor NSG GUIDs ever manage. Two platform features complete the private story: **Private Google Access** lets subnet-internal VMs reach `googleapis.com` over internal IPs, and **Private Service Connect** is the private-endpoint pattern for *your own* and Google's services - the interface-endpoint analog of both previous clouds. **Cloud NAT** supplies managed egress for private VMs, with no NAT instance to babysit.

::: {.warn}
**Watch out - the default network ships with permissive rules**

Every new project starts with a `default` VPC carrying legacy rules - `default-allow-ssh`, `default-allow-rdp`, `default-allow-icmp` - open to `0.0.0.0/0`. Leaving it in place and building next to it is how GCP projects end up with an unplanned network and five open ports. The professional posture: build on a custom-mode VPC like `vpc-shopnow` above, delete the default network when the project no longer needs it, and enforce the posture with an org policy (`compute.skipDefaultNetworkCreation`) so *new* projects are born without it.
:::

## 10.2 Compute Engine: Machines Without Mystery

A Compute Engine instance is the EC2 analog with its own accent: **machine families** named E2 (cost-optimized, the steady-state web-tier default), N4/N2 (general purpose), C4 (compute-bound), M-series (memory), and the GPU lines - plus a capability neither previous cloud matched so directly, **custom machine types**, where you dial vCPU and memory to the workload instead of choosing the nearest size and paying for the gap. Pricing has its own vocabulary: **sustained-use discounts** apply automatically to runs that last the month, **committed use discounts (CUDs)** are the one-or-three-year reservation, and **Spot VMs** are the interruptible tier from the EC2 spot chapter. Images are public OS images (Debian and Ubuntu at the front of the list, no Amazon-Linux equivalent), instance **metadata** plays the user-data role with `--metadata=startup-script=...`, and creation is one command:

```bash
gcloud compute instances create shopnow-web-01 \
  --zone=europe-west3-a \
  --machine-type=e2-small \
  --image-family=debian-12 --image-project=debian-cloud \
  --network=vpc-shopnow --subnet=snet-eu-dev \
  --no-address \
  --tags=web \
  --metadata=startup-script='#! /bin/bash
apt-get update && apt-get install -y nginx'
```

`--no-address` is the flag that keeps the instance private - reach it through the network, not the internet - and `--tags=web` is what the firewall rules from [Section 10.1](#ch10) select on. SSH needs no key distribution: `gcloud compute ssh shopnow-web-01` brokers the key through your IAM identity (OS Login underneath), the Session Manager story of the AWS book with different verbs.

## 10.3 Managed Instance Groups: Autoscaling That Spans Zones

The **managed instance group (MIG)** is the Auto Scaling Group, and in its best form it is better by default. Built on an **instance template**, a *regional* MIG spreads its instances across three zones of the region automatically, with target distribution and redistribution on zone loss - the multi-AZ posture the AWS book configured explicitly, here for free. **Autohealing** replaces instances that fail an application-level health check (not merely a host check), the **autoscaler** scales on CPU, load-balancer capacity, or custom metrics, and **rolling updates** roll new template versions through the group with surge and availability guarantees:

```bash
gcloud compute instance-templates create tpl-shopnow-web \
  --machine-type=e2-small --image-family=debian-12 --image-project=debian-cloud \
  --network=vpc-shopnow --subnet=snet-eu-dev --no-address --tags=web \
  --metadata=startup-script='#! /bin/bash
apt-get update && apt-get install -y nginx'

gcloud compute instance-groups managed create mig-shopnow-web \
  --template=tpl-shopnow-web --size=2 --zones=europe-west3-a,europe-west3-b,europe-west3-c \
  --health-check=hc-shopnow-http --initial-delay=60

gcloud compute instance-groups managed set-autoscaling mig-shopnow-web \
  --region=europe-west3 --max-num-replicas=8 --min-num-replicas=2 \
  --target-cpu-utilization=0.65
```

In front of it all sits GCP's home-field advantage, the **global external load balancer**: a single anycast IP, cross-region health checking, HTTP(S) termination at the edge - the piece of GCP that the other clouds approximate with regional constructs. This book touches it where the labs need an entry point; the platform's own documentation owns the deep end.

## 10.4 Where the Servers End

The honest guidance mirrors the AWS book's EC2 chapter: virtual machines are where stateful oddities, licensed software, and special agents live - not where a modern web tier starts. shopnow's web tier on GCP runs on GKE Autopilot ([Chapter 12](#ch12)) or Cloud Run ([Chapter 13](#ch13)), and the MIG pattern above earns its keep for the few workloads that genuinely need full VM control. The capstone in [Chapter 15](#ch15) runs the comparison with real bills, and the pattern holds across all three clouds: *the smaller your VM fleet, the smaller your pager*.

::: {.note}
**Best practice - one template per workload class, MIGs for everything long-running**

The instance template is to Compute Engine what the launch template was on AWS: the unit of review. When every long-running VM belongs to a MIG with a template, a health check, and an owner label, patching becomes a template update and a rolling restart - and the unmanaged one-off VM, the one nobody patches, never gets created.
:::

**See also:** [Chapter 8](#ch8) set the project these objects live in, [Chapter 11](#ch11) adds the storage and database path, and [Chapter 12](#ch12) runs the same workloads on managed Kubernetes.
