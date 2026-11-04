# Chapter 4 - VPC: Networking You Can Reason About {#ch4}

## 4.1 The Mental Model: A Private Network You Own

A **VPC** (Virtual Private Cloud) is a software-defined network inside one Region that you control the way a network engineer controls a data center: you choose the address space, cut it into subnets, write the route tables, and decide exactly what is reachable from the internet. Everything this book has launched so far lived in the **default VPC** that every account ships with - convenient for learning, and a shared, awkwardly-CIDR'd legacy for anything real. This chapter builds the network the running example deserves.

The VPC gets one IPv4 CIDR block, chosen once and painful to change: `10.0.0.0/16` in this book (65,536 addresses - room for every subnet a platform will ever need). The cardinal rule is *do not overlap with anything you may one day connect to*: other VPCs in the architecture, the office network for VPN access, the corporate CIDRs of a future employer of your code. `10.0.0.0/8` is everyone's instinct; the collisions that rule exists to prevent are why two teams' VPCs sometimes cannot be peered at any price.

## 4.2 Subnets: Public and Private Is Routing, Not Magic

A **subnet** is a slice of the VPC CIDR bound to exactly one **Availability Zone** - the unit where "spread across AZs" becomes literal. Cut `10.0.0.0/16` into `/20` subnets (4,096 addresses each, AWS's own default) and place two per AZ: a `public` and a `private` pair in `eu-central-1a`, and the same again in `eu-central-1b`.

```bash
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications \
  'ResourceType=vpc,Tags=[{Key=Name,Value=shopnow-vpc}]'

aws ec2 create-subnet --vpc-id vpc-0abc --cidr-block 10.0.0.0/20 \
  --availability-zone eu-central-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=shopnow-public-a}]'
```

"Public" and "private" are not properties AWS stamps on subnets - they are consequences of routing. A subnet is *public* if its route table sends `0.0.0.0/0` to an **Internet Gateway** (IGW): resources in it can be given public IPs and talk to the world. A subnet is *private* if it does not: instances boot, run, and serve, but the only path in or out is through something you place deliberately (Section 4.3). Each subnet has its own route table by default; the clean design is one shared route table for the public subnets (local traffic plus IGW) and one per private group (local traffic plus NAT).

Two mechanical facts round out the model. First, AWS reserves five addresses per subnet - the first four and the last - so a `/20` yields 4,091 usable IPs, and a sizing exercise that forgets this meets a surprising capacity wall. Second, a *private* subnet's instances can still receive public IPs if asked; they just cannot use them. Reachability is routing plus gateways, never naming.

## 4.3 NAT Gateways: Outbound Only, On Purpose

Private subnets still need outbound internet: package downloads, API calls, updates. The **NAT gateway** provides it - an AWS-managed address translator that lives in a *public* subnet, holds an Elastic IP, and serves the private route tables as the `0.0.0.0/0` target. Traffic flows private → NAT → IGW → internet, and the reply path is the only way back in; nothing from the internet can initiate toward a private instance. This asymmetry is the entire security story of the tier: your database in `private-b` can fetch its OS patches and cannot be scanned.

The NAT gateway is also the most famous line item in AWS surprise bills: it bills per hour *and* per gigabyte processed, and a chatty workload - multi-gigabyte container pulls from ECR on every deploy, S3 transfers that could have used an endpoint - turns it into a four-figure line before anyone notices. The standard mitigations: one NAT gateway per AZ for availability (accepting the cost) or for development environments a single shared one (accepting the cross-AZ dependency), plus the Section 4.5 endpoints that take S3 and ECR traffic off the NAT entirely. [Chapter 12](#ch12) returns to this bill line with numbers.

## 4.4 Security Groups vs Network ACLs

Two firewall layers guard a VPC, and confusing them causes real outages. A **security group (SG)** attaches to an instance or ENI, is *stateful* (return traffic is automatic), *allows-only* (no deny rules), and evaluates every rule as one set - the workhorse. A **network ACL (NACL)** attaches to a subnet, is *stateless* (responses need their own rules), supports allow *and* deny, and evaluates rules in numbered order - the blunt instrument for subnet-wide blocks and the only way to deny an IP outright. The running example uses SGs exclusively and NACLs remain the default-catch-all; the table is what interview questions and 2 a.m. debugging are made of:

| Property | Security group | Network ACL |
| --- | --- | --- |
| Attaches to | Instance / ENI | Subnet |
| State | Stateful - replies auto-allowed | Stateless - replies need rules |
| Rules | Allow only | Allow and deny |
| Evaluation | All rules together | Lowest rule number first |
| Reference other SGs | Yes - the killer feature | No, CIDRs only |
| Default | Deny all inbound; allow all outbound | Allow all in and out |

SGs reference other SGs as traffic sources, and that one feature is how tiers compose: the database's SG admits inbound 5432 *from the app tier's SG*, not from a CIDR - add an app server and the database needs no edit. It is also how the EKS and RDS chapters will wire the platform: [Chapter 6](#ch6) gives RDS an SG that admits only the cluster's SG, and the database becomes unreachable from everywhere else by construction.

::: {.warn}
**Watch out - the 0.0.0.0/0 port 22**

`--protocol tcp --port 22 --cidr 0.0.0.0/0` is the most-scanned address range on the internet, applied to the most-attacked port. Chapter 3 scoped SSH to one IP and Chapter 3's Session Manager removes the need for the rule entirely; when you inherit an account, this is the first thing to grep for, and mature organizations make it impossible with an SCP (Section 2.7).
:::

## 4.5 VPC Endpoints: Private Paths to AWS Services

A private-subnet instance calling S3 does not need the internet at all. A **gateway endpoint** for S3 (and DynamoDB) is a route-table entry - free of hourly charges - that steers `s3.` traffic into AWS's network. An **interface endpoint** (PrivateLink) does the same for hundreds of other services (SSM, ECR API, CloudWatch, STS): an ENI with a private IP inside your subnet, billed per hour and per GB. The pattern the running example uses: private subnets get a gateway endpoint for S3 plus interface endpoints for `ssm`, `ssmmessages`, `ec2messages`, `ecr.api`, `ecr.dkr`, `logs`, and `sts` - after which the private subnets need *no NAT gateway at all* for their day job, and the most expensive line item shrinks accordingly. Endpoint policies can then scope what the private path may touch - an S3 endpoint policy that admits only your buckets turns "no internet" into "no internet, and only our data".

## 4.6 Beyond One VPC: Peering, Transit Gateway, DNS, and Flow Logs

Platforms grow past one network, and three mechanisms cover the growth. **VPC peering** connects two VPCs privately; it is not transitive (A→B and B→C does not give A→C) and requires non-overlapping CIDRs - the reason for Section 4.1's cardinal rule. **Transit Gateway** is the hub-and-spoke answer: thousands of VPCs and VPNs attach to one router, routes are managed centrally, and the transitive problem disappears at a per-attachment price. Inside a VPC, **Route 53 Resolver** answers private DNS: `db.shopnow.internal` resolving to an RDS endpoint is the kind of thing Section 4.4's SG referencing pairs with nicely. Finally, **VPC Flow Logs** record accept/reject decisions for every connection, shipped to CloudWatch Logs or S3 - the tool that answers "why can't instance A reach B?" with data instead of theory, and a first-class citizen of [Chapter 10](#ch10)'s observability story.

## 4.7 Lab 2: A Two-Tier Network from Scratch

::: {.lab}
### Lab 2 - Build the shopnow VPC {#lab2}

1. Create the VPC `10.0.0.0/16` and enable DNS hostnames (`aws ec2 modify-vpc-attribute --enable-dns-hostnames`).
2. Create an IGW, attach it, and build a public route table: `local` plus `0.0.0.0/0 → igw`. Verify with `aws ec2 describe-route-tables`.
3. Create four `/20` subnets across `eu-central-1a` and `eu-central-1b`: `public-a`, `public-b`, `private-a`, `private-b`, named by tags. Associate both public subnets with the public route table.
4. Allocate an Elastic IP, create a NAT gateway in `public-a`, and build a private route table: `local` plus `0.0.0.0/0 → nat`. Associate both private subnets.
5. Launch a `t4g.micro` into `private-a` (AL2023, SSM instance profile, IMDSv2, no public IP) and reach it with `aws ssm start-session`. Inside, `curl -s https://checkip.amazonaws.com` - it should print the NAT gateway's Elastic IP, which is the proof that private outbound works.
6. From the same session, confirm inbound isolation: nothing from your laptop can reach the instance (`nc -vz <private-ip> 22` fails from outside even though the SG allows it, because routing offers no path).
7. Cleanup: terminate the instance, delete the NAT gateway first (it is the bill), then release the Elastic IP, delete subnets, route tables, IGW, and finally the VPC - deletion order teaches dependency order.

Deliverable: a script (or shell history) that builds the complete two-tier, two-AZ network in one run - the same design Chapter 11 turns into a Terraform module and Chapter 7's cluster will be born into.
:::

**See also:** [Chapter 5](#ch5) fills the network's object-storage tier, [Chapter 6](#ch6) places the database in `private-b` behind an SG that trusts only the app tier, and [Chapter 7](#ch7) creates an EKS cluster whose nodes and pods live in exactly this layout.
