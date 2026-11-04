# Appendix C - Troubleshooting Guide {#appC}

Symptoms first, causes second, fixes third - organized the way incidents arrive. Each entry names the chapter that owns the underlying concepts.

## Connectivity and Networking

**Instance is running, but nothing connects to its public IP.**
Causes in order of frequency: security group lacks the inbound rule for your port; the instance has no public IP (check `describe-instances` - a stopped/started instance may have received a *new* one); the subnet is private (route table has no IGW path - [Chapter 4](#ch4)); the local firewall on the instance itself. Diagnosis: `aws ec2 describe-instances` for IP and SG, then `aws ec2 describe-security-groups --group-ids <sg>` for rules, then Session Manager into the instance and test from inside (`curl -s localhost:80` proves the app; the missing piece is then network, not app).

**"Connection timed out" vs "connection refused" - read the difference.**
*Timed out* means no reply at all: a security group, NACL, or routing drop on the path (most likely), or the instance is stopped. *Refused* means something answered and said no: the host is reachable and the port is closed - the service is down or listening on another interface. This one distinction cuts most network debugging in half.

**A resource "disappeared".**
You are pointed at the wrong Region or profile. `aws sts get-caller-identity` and `aws configure get region` before anything else ([Chapter 1](#ch1)).

**SSM start-session fails with "unable to connect".**
The instance profile lacks `AmazonSSMManagedInstanceCore`, the VPC has no path to the SSM endpoints (add the interface endpoints from Section 4.5 or a NAT route), or the SSM agent is not running (Session Manager into a broken instance needs the agent healthy; EC2 Instance Connect or serial console is the fallback).

## IAM and Access

**`AccessDenied` from a resource you own.**
Three questions in order: *who* is calling (`aws sts get-caller-identity` - profile surprises are common), *what policy* governs that identity (list attached policies; check for explicit `Deny` including SCPs if the account is in an Organization - Section 2.7), and *what exact action* failed (the error or CloudTrail event names it - e.g. `s3:PutObject` vs `s3:ListBucket` mismatch is the classic, Section 2.2).

**`Not authorized to perform sts:AssumeRoleWithWebIdentity` in GitHub Actions.**
The OIDC token arrived but the role's trust policy refused it. Check, in order: the `sub` condition matches the repository *and* the token's actual format (the 2026 change added `@<org-id>/<repo-id>` suffixes for newer repositories - Section 9.2); the `aud` is `sts.amazonaws.com`; the workflow has `permissions: id-token: write`; the identity provider ARN in the trust policy is exact. Run the action with debug logging (`ACTIONS_STEP_DEBUG: true`) to see the token's claims.

**Assumed-role sessions expire mid-task.**
Session duration is set at the role or the assume call; long jobs should request a longer session at assume time (up to the role's maximum) or refresh credentials - not store the role's keys (Section 2.4).

## Compute

**Instance "system reachability check failed" on launch.**
Usually a bad user data script failing early or an overloaded launch; check the screenshot and console output (`aws ec2 get-console-output --instance-id <id>`) - the cloud-init log tells the truth ([Chapter 3](#ch3)).

**Spot instances keep dying.**
They are working as designed. Check interruption frequency per pool in the console, diversify instance types, and make the workload interruption-tolerant (checkpointing, draining) - Section 3.7.

**`exec format error` when a container starts on EKS.**
An amd64 image on arm64 (Graviton) nodes. Rebuild with `docker buildx build --platform linux/arm64` ([Chapter 7](#ch7), [Chapter 9](#ch9)).

## Storage and Databases

**S3 returns `AccessDenied` on an object that "is public".**
The bucket's public access block is doing its job (Section 5.5). If public serving is genuinely intended, use CloudFront with an Origin Access Control; if not, presign (Section 5.6). A `403` on a *versioned* bucket can also mean a `Deny` on the specific object version.

**S3 bucket delete refuses (`BucketNotEmpty`).**
Versioned buckets keep old versions after `aws s3 rm --recursive`. Delete versions explicitly (Appendix A's empty-bucket recipe) or let a lifecycle rule do it.

**RDS: application cannot connect.**
SG reference check first: the database SG must admit 5432 *from the app tier's SG* (Section 4.4, [Chapter 6](#ch6)); then `publicly_accessible` is false and the caller is outside the VPC (connect from inside the VPC or through an approved path); then credentials (Secrets Manager is the source of truth, Section 6.1); then the instance status (`describe-db-instances` - patching or failover windows exist).

**RDS failover took longer than expected.**
Multi-AZ failover is about a minute *plus* your application's connection retry behavior - apps with long TCP timeouts or no retry logic stretch every failover. Fix the app's retry budget, not the database.

**Lambda cannot reach the RDS database.**
The function needs VPC access (ENIs in private subnets, an SG the database's SG admits, Section 8.7), plus the [Chapter 4](#ch4) endpoints or NAT for its AWS API calls, plus RDS Proxy if connection counts are the symptom (Section 6.6).

## Kubernetes on EKS

**Nodes not joining / `NotReady`.**
The node group's IAM role is missing one of the three required policies (Section 7.2), the subnets have no route out for pulling images, or the CNI add-on is unhealthy. `aws eks describe-nodegroup --cluster-name <c> --nodegroup-name <ng>` names the failure.

**`kubectl` cannot reach the cluster.**
The kubeconfig entry is stale or for another profile: re-run `aws eks update-kubeconfig --name <cluster>` with the right Region and profile ([Chapter 1](#ch1)).

**Ingress creates no ALB.**
The AWS Load Balancer Controller is not installed, its IRSA role is wrong, or the Ingress lacks `ingressClassName: alb` (Section 7.6). Controller logs (`kubectl logs -n kube-system deploy/aws-load-balancer-controller`) state the specific refusal.

**Upgrade fails draining a node.**
A workload with `replicas: 1` and no PodDisruptionBudget cannot be evicted politely (Section 7.7). Add PDBs, or temporarily scale the workload before retrying the node roll.

## Cost

**The bill jumped and nobody deployed anything.**
Cost Explorer grouped by usage type first (`NatGateway-Bytes`, `DataTransfer-Regional`, `TimedStorage-...` are the usual suspects - Section 12.5), then by resource. Cross-check CloudTrail for creations nobody remembers: drift is often the cause, and `terraform plan` (Section 11.6) is the mirror.

**NAT gateway is the top line item.**
Move S3/ECR/API traffic onto VPC endpoints (Section 4.5) and check for a workload chattering cross-AZ. The endpoints pay for themselves in weeks at any real traffic level.

**Found unattached EBS volumes / EIPs.**
Delete by tag-verified script (Section 12.5) - they bill whether or not anything uses them, and they are invisible to dashboards not pointed at them.

## State and IaC

**`terraform plan` shows changes nobody made.**
Drift from console edits (Section 11.6): import the change into code (`terraform import` / import blocks) or apply to revert - decide deliberately, never ignore.

**`Error acquiring the state lock`.**
A previous apply died or a colleague is mid-apply. Check who (the lock object/table names the operation), wait if genuine, force-unlock *only* with the lock ID and after confirming no apply is running (Section 11.2).

**State file lost / bucket deleted.**
Versioning on the state bucket ([Chapter 5](#ch5), Section 11.2) is the recovery path - restore the previous version. This is why the state bucket's own settings are reviewed like production data, because that is what they are.
