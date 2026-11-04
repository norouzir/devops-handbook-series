# Chapter 3 - EC2: Virtual Machines in Practice {#ch3}

## 3.1 Instances, AMIs, and Instance Types

**EC2** is AWS's virtual machine service, and after a decade of containers it remains the workhorse: the nodes under every Kubernetes cluster ([Chapter 7](#ch7)), the databases behind managed services, and still - for many teams - the application servers themselves. An **instance** is a running VM; an **AMI** (Amazon Machine Image) is the template it boots from - operating system, patches, and any pre-baked software; and an **instance type** is the size and shape of the hardware slice. The type's name is a small grammar worth reading fluently: `t4g.small` means family `t4g` (burstable, Graviton) and size `small`; `m7g.xlarge` means general-purpose seventh-generation Graviton extra-large. The letter that matters most is the **`g`**: it marks **Graviton**, AWS's own arm64 silicon, which delivers measurably better price-performance than the equivalent x86 type for most workloads - the reason this book defaults to `t4g.micro`/`t4g.small` in examples and to arm64 build targets in [Chapter 9](#ch9). Families map to intents: `t4g` for burstable smalls, `m7g` for balanced general purpose, `c7g` for compute-heavy, `r7g` for memory-heavy, and the GPU families for ML.

Every Region ships curated **AMIs** - Amazon Linux 2023 (this book's default: systemd, SELinux-less, rpm/dnf-based, supported through 2028), Ubuntu, Debian, Windows. The professional AMI strategy is *golden images or baking*: your pipeline builds an image with the app preinstalled (Packer or EC2 Image Builder), and instances boot ready instead of configuring themselves at boot - but for learning and for the running example, a stock AMI plus boot-time configuration is the honest starting point, which is Section 3.4's business.

## 3.2 Launching the First Instance

Three objects must exist before an instance can boot: a **key pair** (the public half is injected into the instance for SSH), a **security group** (the firewall - properly explained in [Chapter 4](#ch4), minimal here), and the launch itself. The full CLI sequence for the running example:

```bash
# 1. Key pair (private key lands in the current directory - chmod 400 it)
aws ec2 create-key-pair --key-name shopnow-key \
  --query 'KeyMaterial' --output text > shopnow-key.pem
chmod 400 shopnow-key.pem

# 2. Security group in the default VPC: SSH from your IP only, HTTP from anywhere
aws ec2 create-security-group --group-name shopnow-web-sg \
  --description "shopnow web tier"
aws ec2 authorize-security-group-ingress --group-name shopnow-web-sg \
  --protocol tcp --port 22 --cidr 203.0.113.10/32
aws ec2 authorize-security-group-ingress --group-name shopnow-web-sg \
  --protocol tcp --port 80 --cidr 0.0.0.0/0

# 3. Launch: find the latest AL2023 AMI, then run it
AMI_ID=$(aws ssm get-parameters \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text)

aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t3.micro \
  --key-name shopnow-key \
  --security-group-names shopnow-web-sg \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=project,Value=shopnow},{Key=env,Value=dev}]'
```

Three details in that sequence carry production weight. The AMI lookup goes through **SSM Parameter Store's public AMI aliases** instead of a hand-copied ID, so the command never rots when a new image is released. The SSH rule is scoped to a single address rather than the planet. And the tags from [Chapter 1](#ch1) are set at creation, not retro-fitted. The instance finishes booting in under a minute; `aws ec2 describe-instances --query '...'` (or the table query from Chapter 1) fetches its public IP.

## 3.3 Reaching the Instance: SSH, Instance Connect, Session Manager

SSH with `ssh -i shopnow-key.pem ec2-user@<public-ip>` works and teaches the classic model, but production has moved on, and so should the reflex. **Session Manager** (part of **SSM**) opens a shell through the AWS API - no inbound port 22 at all, no key distribution, full session logging to CloudWatch or S3, IAM as the front door. It requires the instance to run the SSM agent (preinstalled on AL2023) and to have an instance profile with the `AmazonSSMManagedInstanceCore` policy - the first practical payoff of [Chapter 2](#ch2)'s roles-over-keys:

```bash
aws ec2 run-instances ... --iam-instance-profile Name=ssm-core-profile
aws ssm start-session --target i-0123456789abcdef0
```

No public IP is even required if the VPC has the right endpoints ([Chapter 4](#ch4) wires them). The working rule: SSH and port 22 survive for break-glass; Session Manager is the day-to-day door, and closing 22 entirely is a finding you can retire.

## 3.4 user data and cloud-init

**User data** is a script AWS hands the instance at first boot, executed by `cloud-init`. It is the difference between "a machine I still have to configure" and "a machine that starts ready":

```bash
#!/bin/bash
dnf install -y nginx
cat > /usr/share/nginx/html/index.html <<'EOF'
<h1>shopnow - served by EC2</h1>
EOF
systemctl enable --now nginx
```

Pass it with `--user-data file://bootstrap.sh` on `run-instances`, and the instance serves the page the moment it is reachable. Two honest limits: user data runs *once* (on every boot by default, but idempotent scripts are the discipline - the Ansible book of this series exists because configuration management beats boot scripts past a page of YAML), and secrets do not belong in it - anything sensitive should be fetched at boot from SSM Parameter Store or Secrets Manager with the instance role, not embedded in an unencrypted field readable by anyone who can describe the instance.

## 3.5 Storage: EBS Volumes, gp3, and Snapshots

Instance disks are **EBS** (Elastic Block Store) volumes - network-attached block devices that persist independently of the instance and can be detached and reattached elsewhere. The default type is **gp3**, where you provision IOPS and throughput independently of size (and unlike its gp2 predecessor, baseline performance is included without paying for a bigger disk - the free upgrade is [Chapter 12](#ch12) material). EBS lives inside a single AZ: a volume cannot attach to an instance in another AZ, which is the fact that makes snapshots matter.

A **snapshot** is a point-in-time, incremental, crash-consistent copy of a volume, stored in S3 under the hood and *Regional, not AZ-bound* - restore it into any AZ of the Region, or copy it to another Region entirely. Snapshots are how EBS participates in backup discipline ([Chapter 6](#ch6) does the same dance for managed databases) and how AMIs are made: an AMI from an instance is, mechanically, snapshots of its volumes plus the boot metadata.

```bash
aws ec2 create-snapshot --volume-id vol-0abc123 --description "shopnow web pre-upgrade"
aws ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[].[SnapshotId,Description,StartTime]' --output table
```

::: {.note}
**Best practice - practice the restore, not just the snapshot**

A snapshot that has never been restored is a hope, not a backup. The lab below creates one snapshot and then restores it to a fresh volume; the same drill belongs in production on a schedule - snapshot, restore to a scratch instance, verify the data, delete. Untested backups fail on the day they are needed, usually in creative ways.
:::

## 3.6 Instance Metadata and IMDSv2

Every instance exposes **instance metadata** - the instance ID, type, AZ, network config, and *the role's temporary credentials* - at `http://169.254.169.254` from inside the instance. It is the mechanism that makes roles work with no keys on disk, and for the same reason it is the classic SSRF target: trick an app into fetching that address and its credentials walk out the door. **IMDSv2** is the fix, and on current AMIs it is the default: metadata requests must begin with a `PUT` that obtains a session token, so a naive `GET` from a confused web server returns nothing useful. The instances this book launches enforce it with `--metadata-options "HttpTokens=required,HttpPutResponseHopLimit=1"`, and the same enforcement exists as an account-level guardrail in modern SCPs.

## 3.7 Pricing Models: On-Demand, Spot, and Savings Plans

The same instance has three prices depending on how you commit. **On-Demand** is the default: per-second billing, nothing promised in either direction. **Spot** is spare capacity auctioned at up to ~90% off, with the twist that AWS may reclaim the instance with two minutes' notice - which sounds terrifying until you design for it: stateless workers, checkpointed batch jobs, and cluster autoscalers that top up from on-demand. Spot is how the cheap parts of serious platforms are built. **Savings Plans** (and their older cousin, Reserved Instances) trade a one- or three-year commitment for double-digit discounts on the baseline you know you will run; the steady state of a mature platform is *savings plans for the floor, on-demand for the peaks, spot for the elastic and interruptible middle* - a line [Chapter 12](#ch12) turns into a routine.

## 3.8 Lab 1: Launch, Reach, Snapshot, Clean Up

::: {.lab}
### Lab 1 - A Real Instance from Zero {#lab1}

1. Run the Section 3.2 sequence: key pair, security group, AL2023 AMI lookup, `run-instances` with tags and IMDSv2 metadata options. Fetch the public IP with a `--query` on `describe-instances`.
2. Add a bootstrap: create `bootstrap.sh` from Section 3.4 and relaunch a second instance with `--user-data file://bootstrap.sh`. When it is up, `curl http://<ip>` from your machine and confirm the shopnow page.
3. Reach the first instance two ways: SSH with the key pair, then (after attaching an SSM-enabled instance profile) `aws ssm start-session --target <instance-id>`. Note that Session Manager needed no open port.
4. From inside the instance, query the metadata service with IMDSv2 (token via `PUT`, then `GET .../latest/meta-data/instance-id`) and confirm `aws sts get-caller-identity` shows the instance profile role, not a key.
5. Snapshot the instance's root volume, restore the snapshot to a new volume in another AZ of your Region, verify its size and state, then delete the restored volume.
6. Convert the running instance into an AMI (`aws ec2 create-image`) and inspect what AWS actually created - you will find the snapshot from step 5 underneath it.
7. Cleanup: terminate both instances (`aws ec2 terminate-instances --instance-ids ...`), delete the key pair, delete the security group (it will refuse while instances share it - a useful error), and confirm with the Chapter 1 table query that no instances remain.

Deliverable: a repeatable launch script (or shell history) that goes from nothing to a serving web instance in under five minutes, plus one restore-tested snapshot - the substrate the rest of Part I builds its network around.
:::

**See also:** [Chapter 4](#ch4) replaces the default VPC this lab quietly used with a network you design on purpose, and [Chapter 9](#ch9) replaces the manual launch with an AMI-baking pipeline. The rightsizing of whatever this lab leaves running is [Chapter 12](#ch12)'s opening example.
