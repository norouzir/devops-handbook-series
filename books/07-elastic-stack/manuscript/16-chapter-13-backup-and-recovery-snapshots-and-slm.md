# Chapter 13 - Backup and Recovery: Snapshots and SLM {#ch13}

## 13.1 What Snapshots Cover, and What Else Does

Elasticsearch gives replicas and ILM all the resilience of the cluster, and neither is a backup. Replicas protect against *node* loss while the cluster lives; ILM deletes data on schedule, by design. The only mechanism that survives cluster loss, operator error (`DELETE logs-*` is one mistyped wildcard away), and corruption is the **snapshot**: a point-in-time, incremental, content-addressed copy of indices into a repository *outside* the cluster. The backup discipline this chapter builds has one hard rule that separates real backups from rituals: **a snapshot that has never been restored is a hypothesis** - [Lab 5](#lab5) exists to keep it a fact.

What snapshots cover: every index you include - settings, mappings, documents - plus the cluster's global state (templates, ILM policies, ingest pipelines) when you snapshot against a cluster-level pattern, and the system indices (`.security-*`, `.kibana*`) when you include them, which restores users, roles, and dashboards along with data. What they do not cover: configuration files (`elasticsearch.yml`, keystore) - keep those in your config management - and anything not in indices. Snapshots are **incremental** per repository: after the first copy, only new or changed Lucene segments are stored, which makes daily snapshots of a log estate cheap and retention over months normal.

## 13.2 Snapshot Repositories

A **repository** is a registered storage location with a plugin-provided type. The supported backends are object storage first - S3 (`repository-s3`), Azure Blob, Google Cloud Storage - plus shared filesystems and, for dev, the local path. Registration is a one-time API call per repository:

```text
PUT _snapshot/logs-backup
{
  "type": "s3",
  "settings": {
    "bucket": "es-prod-snapshots",
    "base_path": "logs-cluster",
    "region": "eu-central-1",
    "compress": true
  }
}
```

For the Compose sandbox and the lab, the **shared filesystem** type with a mounted volume stands in for S3:

```text
PUT _snapshot/local-backup
{
  "type": "fs",
  "settings": { "location": "/usr/share/elasticsearch/backup", "compress": true }
}
```

Two operational notes belong to registration day. Repository contents must be *dedicated to Elasticsearch* - one repository per cluster, no shared folders, because the content-addressed layout assumes sole ownership; two clusters writing one repository corrupt each other. And `path.repo` (for `fs` repositories) must be set in `elasticsearch.yml` before the repository registers - the plugin needs to be told where on disk it is allowed to write. Object-storage plugins instead take credentials via the keystore (`elasticsearch-keystore add s3.client.default.access_key`), keeping secrets out of the config file and into the custody rules of [Chapter 12](#ch12).

## 13.3 Taking Snapshots: Manual and Policy-Driven

A snapshot names a repository and the indices to include; the cluster does the rest in the background:

```text
PUT _snapshot/logs-backup/snapshot-2026.10.30
{
  "indices": ["logs-*", "metrics-*", ".security-*", ".kibana*"],
  "include_global_state": true,
  "partial": false
}
```

`include_global_state: true` captures templates and policies (the cluster state); `partial: false` refuses to snapshot an index with unavailable shards - the default and the right choice, because a "successful" partial backup is a future restore surprise. Progress and the full history are readable (`GET _snapshot/logs-backup/_all`, `GET _snapshot/_status`), and snapshot names that embed dates keep the listing self-documenting.

The policy layer - **Snapshot Lifecycle Management (SLM)** - automates the schedule exactly as ILM automates retention ([Chapter 10](#ch10)):

```text
PUT _slm/policy/nightly-logs
{
  "schedule": "0 30 1 * * ?",
  "name": "<nightly-logs-{now/d}>",
  "repository": "logs-backup",
  "config": {
    "indices": ["logs-*", "metrics-*", ".security-*", ".kibana*"],
    "include_global_state": true
  },
  "retention": {
    "expire_after": "30d",
    "max_count": 90,
    "min_count": 7
  }
}
```

Every night at 01:30, a snapshot named for the day lands in the repository; retention keeps a month of dailies (at least seven, at most ninety). The `retention` block is the answer to the question that ends every backup argument: how far back can you restore, and at what storage cost - and because snapshots are incremental, the answer is usually "further than you assumed, cheaper than you feared." SLM status and history (`GET _slm/stats`, the policy's `stats` block: success and failure counts) belong in the monitoring set from [Chapter 11](#ch11) - a backup system that does not alert on its own failures is a superstition.

::: {.note}
**Best practice - one policy per importance class, and an off-cluster copy**

Audit logs and business-critical indices justify their own SLM policy with tighter cadence and longer retention than bulk logs. And for the disaster scenario where the cluster *and* its object-storage bucket are compromised or misconfigured, the mature estates add an out-of-band copy - bucket replication, or periodic restore into a cold second cluster - because the backup must not share a failure domain with the thing it protects.
:::

## 13.4 Restoring: The Only Test That Counts

A restore maps snapshot data back into the cluster. The minimal case replaces an index you lost or fat-fingered:

```text
POST _snapshot/logs-backup/nightly-logs-2026.10.29/_restore
{
  "indices": "logs-nginx-default",
  "include_global_state": false
}
```

The index comes back with its settings, mappings, and ILM policy attachment - including lifecycle state, so a restored warm index continues aging. Two restores cover the special cases. **Rename-and-compare** (`"rename_pattern": "logs-(.+)", "rename_replacement": "restored-logs-$1"`) restores an older copy alongside the live index - the pattern for "what did the data say *then*?" forensics and for verifying a snapshot without touching production. **Cluster-state restore** (`include_global_state: true` during restore, feature-flagged subsets via `feature_states`) brings back templates, policies, security, and Kibana objects - the mechanism behind full-cluster rebuilds, used sparingly because it overwrites global state.

The restore drill belongs in the runbook with a schedule, not in the appendix of good intentions: quarterly, pick one recent and one month-old snapshot, restore into a scratch namespace or a staging cluster, run the queries your teams would run, record how long it took. The drill validates the three things that silently break backups: the repository credentials still work, the data inside is what the name claims, and the restore time fits your recovery-time objective - three facts no amount of green check marks in SLM history can prove.

## 13.5 Lab 5: Snapshot Policy and a Restore Drill

::: {.lab}
### Lab 5 - Back up the sandbox, then prove it works {#lab5}

1. Secure the stack minimally for the lab: keep it simple, but ensure the data volume has a sibling - add a `backup` volume and mount it at `/usr/share/elasticsearch/backup`, and set `path.repo: ["/usr/share/elasticsearch/backup"]` in `elasticsearch.yml` (restart the stack).
2. Register the repository: `PUT _snapshot/local-backup` (type `fs`, location `/usr/share/elasticsearch/backup`). Verify with `GET _snapshot` and a `POST _snapshot/local-backup/_verify`.
3. Generate data worth protecting: rerun the Chapter 4 load generator until `logs-nginx-default` holds a few thousand documents; note the exact count (`GET logs-nginx-default/_count`).
4. Take a manual snapshot of your log stream plus the Kibana system indices, named `first-drill`. Watch it complete (`GET _snapshot/_status`), then list the repository and note the snapshot's index list and size.
5. Take a *second* snapshot after generating more traffic, and compare the repository listing: the incremental delta is small - this is the incremental property, observed.
6. The destructive test: `DELETE logs-nginx-default`. Confirm it is gone (`GET _cat/indices?v`), do not panic, then restore it from `first-drill` with rename-replacement `restored-logs-nginx-default` first, verify the count matches step 3, delete the restore, and repeat the restore *without* renaming to bring the original stream back.
7. Automate it: create the SLM policy `nightly-logs` from Section 13.3 with a schedule a few minutes ahead, wait for it to fire, and read `GET _slm/stats` to see it recorded. Then simulate the failure case: stop the stack, rename the backup volume, start the stack, run `GET _snapshot/local-backup/_all` - and record what the error looks like, because recognizing a broken repository in production is half the recovery.
8. Write the runbook paragraph: repository name, policy name, restore commands for the two cases (forensic and in-place), and the drill schedule.

Deliverable: a sandbox with an automated, retained, *restore-tested* backup loop - and the muscle memory that separates backup theater from backup discipline.
:::

**See also:** [Chapter 11](#ch11) for the recovery-speed sizing that restore drills measure, and [Chapter 14](#ch14) for running this whole loop under ECK on Kubernetes.
