# Chapter 6 - RDS: Managed Databases Without the 3 a.m. Pages {#ch6}

## 6.1 What "Managed" Actually Means Here

**RDS** runs relational databases - PostgreSQL, MySQL, MariaDB, Oracle, SQL Server, plus Amazon's own **Aurora** line (a MySQL- and PostgreSQL-compatible engine with faster storage and extra features) - as a managed service. "Managed" deserves a precise definition, because the boundary is where every expectation mismatch begins. AWS handles: provisioning, OS and database patching, backups, failover mechanics, and the hardware underneath. You keep: schema and migrations, query performance, parameter tuning, engine version upgrade *timing*, and the access model. The deal is real - the 3 a.m. replication failure page genuinely disappears - but it is a service level for the *platform*, not a guarantee for your queries, and this chapter is about exercising the knobs that remain yours well.

The CLI workflow mirrors every service in this book: create with defaults, inspect with `describe`, connect from the network you built in [Chapter 4](#ch4).

```bash
aws rds create-db-instance \
  --db-instance-identifier shopnow-db \
  --engine postgres \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --max-allocated-storage 200 \
  --db-name shopnow --master-username admin \
  --manage-master-user-password \
  --vpc-security-group-ids sg-0db123 \
  --no-publicly-accessible
```

That single command already contains three production decisions worth naming: `db.t4g` (Graviton database instances - the price-performance default, same as EC2 in [Chapter 3](#ch3)), `--max-allocated-storage` (storage autoscaling, which absorbs growth spikes without a resize event), and `--manage-master-user-password` (the master password is generated and stored in Secrets Manager instead of a CLI flag - [Chapter 2](#ch2)'s "no secrets in commands" made manifest).

## 6.2 High Availability: Multi-AZ vs Read Replicas

The two availability mechanisms of RDS are constantly confused, and the distinction is one sentence: **Multi-AZ is synchronous redundancy for availability; read replicas are asynchronous copies for read scale.** A Multi-AZ deployment maintains a standby in another AZ of the same Region, kept in lockstep; writes commit to both, failover flips the endpoint in about a minute automatically, and the standby serves *no* traffic in normal operation. A read replica streams changes asynchronously and can lag by seconds; it serves reads, takes reporting or analytics load off the primary, and can be *promoted* to a standalone primary - a migration tool as much as a scaling tool.

| Property | Multi-AZ (standby) | Read replica |
| --- | --- | --- |
| Purpose | availability / failover | read scaling, offloading |
| Replication | synchronous | asynchronous (can lag) |
| Serves queries normally | no | yes |
| Failover | automatic, ~1 minute | manual promotion |
| Cross-Region | no (same Region, other AZ) | yes (cross-Region supported) |

The running example uses Multi-AZ for the production database (the shop cannot write during an AZ failure) and adds a replica only when read load justifies it. A common maturity path is worth remembering: replicas also give you a low-risk upgrade lane - upgrade the replica first, test, promote - and a Multi-AZ DB *cluster* configuration (distinct from classic Multi-AZ) exists for engines where two readable standbys are worth the cost. Start simple: single-AZ for dev, Multi-AZ for anything that must survive an AZ.

## 6.3 Backups: Automated, PITR, and Snapshots

RDS gives you two backup mechanisms, and the discipline is knowing what each is for. **Automated backups** run continuously against the storage layer with a retention window of 1-35 days (0 disables them - a setting nobody should ever type twice), and enable **point-in-time recovery**: restore to any second within the window, into a new instance. **Manual snapshots** are explicit, retained until deleted, survive instance deletion (with `--final-db-snapshot-identifier` at delete time - see the Watch out box), and are the unit of long-term and cross-Region backup: copy them to another Region for DR, share them, or ship them to S3/Glacier archives. The restore model from [Chapter 3](#ch3) applies unchanged - *a backup that has never been restored is a hope* - and a quarterly "restore the production snapshot into a scratch instance and run the smoke tests" drill is the cheapest insurance in this book.

::: {.warn}
**Watch out - deleting the database deletes the backups**

`aws rds delete-db-instance` without `--final-db-snapshot-identifier` removes the instance and (after the retention window) its automated backups. The one-line habit that prevents the story: always pass `--final-db-snapshot-identifier shopnow-db-final-$(date +%F)`. Snapshot deletion is separately confirmable, and manual snapshots outlive everything - which is exactly why the important ones are manual.
:::

## 6.4 Networking and Access: The Database Nobody Can Reach

An RDS instance lives inside the VPC of [Chapter 4](#ch4), and its security posture is decided at creation: **no public IP** (`--no-publicly-accessible`, the default and the correct setting), an SG admitting only 5432 from *the app tier's SG* (Section 4.4's SG-referencing), and TLS enforced per engine's parameter settings. Connecting from a bastion or an admin laptop is the exception pattern, not the design - the healthy default is that only the application tier can open a socket to the database at all, and everything else uses approved paths (a read-replica for analytics, a bastion-less SSM session into the app tier for debugging).

Credentials complete the posture: the master password belongs in **Secrets Manager** (Section 6.1's flag put it there), applications fetch it at startup with their role, and *rotation can be automated* - Secrets Manager's rotation Lambda swaps the password on a schedule without a deploy. Combined with least-privilege *database* users (separate read/write/migrate users per service, not one superuser shared by three apps), the database stops being the soft center of the platform.

## 6.5 Parameter Groups, Maintenance, and Upgrades

The knobs that remain explicitly yours live in **parameter groups** (engine configuration - `max_connections`, `shared_buffers`, `log_min_duration_statement`) and **option groups** (engine add-ons), attached at creation. Changing a parameter ranges from immediate (dynamic) to "applies at the next maintenance window" (static), which is the natural segue to the window itself: a weekly slot, chosen by you, during which AWS may patch the OS or the engine - a Multi-AZ instance patches the standby first, fails over, patches the old primary, and the page you never get is the whole point of Section 6.1. Engine *major* version upgrades, by contrast, are your decision and your project: they are triggered manually (or by a maintenance window if you enable auto-upgrades), require testing - this is what the replica-upgrade lane from Section 6.2 is for - and deserve a rehearsed runbook, because they are the only RDS event with meaningful downtime potential.

Two observability integrations close the loop with [Chapter 10](#ch10): **Performance Insights** surfaces per-query load on the instance (the "what is slow" answer), and CloudWatch metrics (`CPUUtilization`, `FreeableMemory`, `DatabaseConnections`, replica lag) are what the alarms in [Chapter 10](#ch10) watch - including the free-storage alarm that saves more databases than any tuning exercise.

## 6.6 RDS Proxy and the Lambda Connection Problem

Serverless and relational databases meet at an awkward seam: Lambda scales to hundreds of concurrent executions, each opening its own database connection, and PostgreSQL falls over at a few thousand connections long before the CPU blinks. **RDS Proxy** is the managed connection pooler that stands between them - the function connects to the proxy (via a Secrets Manager-backed credential), the proxy multiplexes hundreds of function connections onto a handful of database connections, and failovers that would hard-drop client sessions are absorbed. The same pooling logic applies to any bursty fleet of short-lived clients, but the Lambda pairing is the classic. The chapter's rule of thumb: direct SG-to-SG connections for long-lived application servers ([Chapter 3](#ch3), [Chapter 7](#ch7)); a proxy when the client population is bursty or serverless.

**See also:** [Chapter 7](#ch7) places this database behind an EKS-hosted application tier with SG-referencing doing the access control, [Chapter 10](#ch10) alarms on its metrics, and [Chapter 11](#ch11) replaces `create-db-instance` with a Terraform resource carrying the same decisions as code.
