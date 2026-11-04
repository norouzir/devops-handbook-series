# Chapter 5 - S3: Object Storage as a Platform {#ch5}

## 5.1 Objects, Buckets, and the Flat Namespace

**S3** is object storage: buckets hold objects, objects are byte blobs plus metadata, and every object is addressed by a key. The model sounds trivial and is anything but - S3's design guarantees (eleven-nines durability as a design objective, unlimited total size, per-object sizes up to 5 TB, and read-after-write *strong consistency* since December 2020) are why it has become the default substrate of data engineering, backups, static hosting, and half of this book's plumbing: EBS snapshots live in S3 (Section 3.5), RDS backups live in S3 ([Chapter 6](#ch6)), Terraform state will live in S3 ([Chapter 11](#ch11)), and container layers of ECR live in S3 ([Chapter 7](#ch7)).

Two vocabulary points prevent daily confusion. First, the namespace is *flat*: `assets/logo.png` is not a file inside a folder - it is one string key, and "folders" are purely a console display convention over key prefixes. Tools that behave like filesystems (`aws s3 cp -r`, mounting via s3fs) are conveniences over `ListObjectsV2` and copy semantics; the object model underneath has no rename and no directories. Second, a bucket name is globally unique across all of AWS (they share one namespace with the DNS name space: bucket names are also URLs), which is why `aws s3 mb s3://shopnow-assets-eu-central-1-prod` style names - project, purpose, Region, environment - are the convention worth copying.

```bash
aws s3 mb s3://shopnow-assets-eu-central-1-prod --region eu-central-1
aws s3 cp ./logo.png s3://shopnow-assets-eu-central-1-prod/assets/logo.png
aws s3 ls s3://shopnow-assets-eu-central-1-prod/assets/
```

## 5.2 Storage Classes: Paying for the Access Pattern

Every object has a storage class, and choosing it well is the difference between a sensible bill and an embarrassing one. The classes are a spectrum from instant to archival, and the honest way to keep them straight is access pattern, not price-per-GB alone:

| Class | Retrieval | Fits | Watch out for |
| --- | --- | --- | --- |
| Standard | Instant | default active data | most expensive per GB |
| Standard-IA | Instant | infrequent access | retrieval fee per GB |
| One Zone-IA | Instant | re-creatable data | single AZ durability |
| Intelligent-Tiering | Instant | unpredictable patterns | monitoring fee per object |
| Glacier Instant Retrieval | Instant (ms) | quarterly archives | retrieval fee |
| Glacier Flexible Retrieval | minutes-hours | backups, DR copies | no instant access |
| Glacier Deep Archive | hours | compliance keeps | restore is a project |

Intelligent-Tiering deserves special mention for DevOps workloads: log archives, build artifacts, and user uploads rarely announce their access pattern, and the class moves objects between tiers automatically, charging a small monitoring fee for the privilege. It is the correct default for anything whose future access is a guess.

## 5.3 Lifecycle Policies: Automation Over Discipline

Manual tiering does not survive contact with real workloads; **lifecycle policies** apply rules automatically, and they are where S3 stops being storage and starts being an operations platform. A rule matches a prefix or tag and either *transitions* objects between classes or *expires* them, with age conditions:

```json
{
  "Rules": [
    {
      "ID": "archive-old-assets",
      "Filter": { "Prefix": "assets/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30, "StorageClass": "INTELLIGENT_TIERING" },
        { "Days": 180, "StorageClass": "GLACIER_IR" }
      ]
    },
    {
      "ID": "expire-deploys",
      "Filter": { "Prefix": "deploys/" },
      "Status": "Enabled",
      "Expiration": { "Days": 90 }
    }
  ]
}
```

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket shopnow-assets-eu-central-1-prod \
  --lifecycle-configuration file://lifecycle.json
```

The second rule is the one pipelines depend on: every deploy to S3 accumulates artifacts, and an expiration rule means old deploys delete themselves instead of accumulating until a human does an archaeology pass. Noncurrent-version rules (next section) do the same for versioned buckets.

## 5.4 Versioning, Replication, and Protecting Data

**Versioning** is a bucket property that changes delete semantics from "gone" to "marked": overwrites and deletes create new versions, and any previous version remains restorable - which makes it the first-line defense against both bugs (a bad `aws s3 sync --delete`) and ransomware (which deletes what it can reach, not what versioning preserves). Versioned buckets need their own lifecycle hygiene, because old versions accumulate forever otherwise: a rule with `NoncurrentVersionExpiration` keeps, say, three generations and expires the rest.

```bash
aws s3api put-bucket-versioning \
  --bucket shopnow-assets-eu-central-1-prod \
  --versioning-configuration Status=Enabled
```

**Cross-Region Replication** copies objects (and their metadata) asynchronously to a bucket in another Region as they arrive - the disaster-recovery story for data that must survive a Regional problem, requiring versioning on both ends and an IAM role to do the copying. It is also, notably, one-way and near-real-time rather than a backup: deletes propagate unless replication rules say otherwise, so replication complements rather than replaces snapshots and versioning.

## 5.5 Encryption: SSE-S3, SSE-KMS, and the Default

Every new object written to S3 has been automatically encrypted with **SSE-S3** (AES-256, keys managed by S3) since January 2023 - encryption at rest is the floor, not a decision. The decision that remains is *who holds the keys*: SSE-S3 for simplicity, or **SSE-KMS**, where the keys live in KMS, every use is logged, and access can be governed per key by policy - the standard choice for data with compliance obligations, at a small per-request cost. In transit, S3 speaks TLS on every endpoint and supports bucket policies that *deny* non-TLS requests, which closes the last plaintext gap. Buckets additionally carry a **public access block** - four switches that, by default and by AWS recommendation, stay on in every account; public content is served deliberately (Section 5.6) or not at all.

::: {.warn}
**Watch out - "the bucket was public"**

Public S3 buckets are the most published data-breach category in cloud history, which is why the public access block exists, why Account Level settings can force it on every new bucket, and why [Chapter 2](#ch2)'s Access Analyzer flags any bucket reachable from outside. If a bucket genuinely must serve the public, do it through CloudFront with an Origin Access Control identity - the bucket stays private and the CDN is the only door.
:::

## 5.6 Sharing Safely: Presigned URLs and Static Hosting

Two patterns cover most "share S3 data" needs. A **presigned URL** is a time-boxed URL that grants one operation on one object - generated by an identity that *has* the permission, usable by anyone who has the URL until it expires:

```bash
aws s3 presign s3://shopnow-assets-eu-central-1-prod/assets/logo.png \
  --expires-in 900
```

This is how applications hand out private downloads without proxying bytes, and how upload flows let browsers PUT directly to S3 with a policy instead of a credential. The second pattern is **static hosting**: a bucket configured as a website endpoint serves `index.html` for a site. The website endpoint requires public-read objects, so the production shape is bucket-private + CloudFront in front with an Origin Access Control - which also gives you HTTPS (bucket website endpoints are HTTP-only), caching, and custom domains in one move. The lab builds both patterns end to end.

## 5.7 S3 as Infrastructure: Events, State, and the Platform View

Two final roles make S3 infrastructure rather than storage. **Event notifications** let S3 push on object events (`s3:ObjectCreated:*`) to Lambda, SQS, or SNS - the trigger of every "process the upload" pipeline, and the first meeting of this book's serverless chapter ([Chapter 8](#ch8)) with real work. And **S3 as a backend** is where [Chapter 11](#ch11) stores Terraform state: a dedicated, versioned, encrypted bucket that makes IaC safe to share across a team. The pattern generalizes - S3 underlies ECR image layers, CloudTrail audit logs, Flow Logs from [Chapter 4](#ch4), and Glue data lakes - and once you see it, the platform view of AWS is mostly "compute services arranged around S3".

## 5.8 Lab 3: Versioned, Life-Cycled, and Served

::: {.lab}
### Lab 3 - An S3 Bucket Done Properly {#lab3}

1. Create a uniquely-named bucket in your Region and enable versioning. Upload a file twice (modify it between uploads) and list versions with `aws s3api list-object-versions` - both generations should be visible.
2. Delete the object, then fetch it again by its explicit version ID from the version listing. Restore the object by copying an old version back onto the base key. That drill is the ransomware answer.
3. Apply the Section 5.3 lifecycle JSON (adjust prefixes to your test layout), then run `aws s3api get-bucket-lifecycle-configuration` to confirm.
4. Add a `NoncurrentVersionExpiration` rule keeping one day of noncurrent versions, and add a small rule expiring everything in a `tmp/` prefix after 1 day - then upload to `tmp/` and note that S3 enforces expiry within about a day, not instantly.
5. Static site: upload a minimal `index.html` and `error.html` under a `site/` prefix... then instead of making them public, prove the private path - attempt to fetch the object URL anonymously and confirm the `AccessDenied` XML.
6. Generate a 15-minute presigned URL for `index.html` and fetch it with `curl` before and after expiry - one succeeds, one fails, and that pair is the whole presigning model.
7. Cleanup: empty the bucket (`aws s3 rm s3://... --recursive`) - versioned buckets need `--recursive` plus `aws s3api delete-objects` for noncurrent versions or the lifecycle rule will do it within a day - then delete the bucket.

Deliverable: a bucket whose protection settings (versioning, lifecycle, encryption defaults, public block) you can enumerate from memory, with shell history proving each behaved as claimed.
:::

**See also:** [Chapter 6](#ch6) consumes S3 for database backups, [Chapter 8](#ch8) hangs a Lambda function off `s3:ObjectCreated:*`, [Chapter 9](#ch9) deploys the static site through a pipeline, and [Chapter 11](#ch11) moves Terraform state into a bucket exactly like this one.
