# Chapter 11 - Cloud Storage and Cloud SQL: The Managed Data Path {#ch11}

## 11.1 Cloud Storage: Buckets Without Prefix Games

**Cloud Storage** is the S3 analog with the fewest surprises in the platform's favor: a globally flat bucket namespace, objects in regional, dual-region, or multi-region locations, and four **storage classes** - Standard, Nearline, Coldline, Archive - that map to the S3 tiering story with 30/90/365-day minimum-duration pricing. The everyday verbs live in the `gcloud storage` family; `gsutil`, the tool every old tutorial quotes, is legacy and this book does not use it:

```bash
gcloud storage buckets create gs://shopnow-assets-eu \
  --location=europe-west3 --uniform-bucket-level-access

gcloud storage cp ./assets/* gs://shopnow-assets-eu/assets/
gcloud storage ls -l gs://shopnow-assets-eu/assets/
gcloud storage sign-url --uri=gs://shopnow-assets-eu/assets/logo.png \
  --duration=15m    # the presigned-URL analog (v4 signing)
```

The controls carry over with new names and one genuinely better default. **Uniform bucket-level access** turns off object-level ACLs entirely - one IAM model ([Chapter 9](#ch9)) instead of two - and **public access prevention** is a bucket- or org-level setting that makes "public by accident" impossible rather than discouraged. **Versioning**, **soft delete** (a seven-day recovery window after deletes, on by default for new buckets), **retention policies** (the Object Lock analog, up to lock-in for compliance), and **lifecycle rules** (age- and prefix-based transitions and deletes in JSON, applied with `gcloud storage buckets update --lifecycle-file=...`) complete the S3 mapping. **Autoclass** automates the tiering for workloads with unpredictable access patterns - the Intelligent-Tiering analog.

::: {.note}
**Best practice - create every bucket with `--uniform-bucket-level-access` and prevention on**

The two flags above cost nothing at creation and remove the two oldest classes of storage incident: an ACL that quietly overrides your IAM design, and an object that goes public because someone toggled the wrong checkbox. New buckets you create can have both; the org policy `storage.publicAccessPrevention` makes the second one a rule instead of a habit - the same enforcement reflex as the Azure chapter's `--allow-blob-public-access false`.
:::

## 11.2 Static Sites, With One Honest Difference

GCP serves static content well, but not from the bucket alone: a **Cloud Storage bucket website** speaks HTTP, and HTTPS needs the **global external load balancer** from [Chapter 10](#ch10) (bucket backend + managed certificate) in front of it. That is the honest delta against Azure's `$web` endpoint and S3's website hosting - one more object to create for TLS termination - and it is why small static sites on GCP often ship as a **Cloud Run** service ([Chapter 13](#ch13)) serving a directory of files, which buys the HTTPS endpoint, custom domain, and zero-scale of the serverless platform in exchange for a one-line Dockerfile. The running example takes the Cloud Run path; the bucket remains the asset store behind it.

## 11.3 Cloud SQL: PostgreSQL Without the Pager

**Cloud SQL** is the RDS of GCP: managed MySQL, PostgreSQL, and SQL Server with automated backups, point-in-time recovery, **high availability** (a synchronous standby in another zone of the region with automatic failover), **read replicas** (including cross-region ones for the DR story), storage autogrow, and maintenance windows you schedule. Creation is one command, and the two flags that matter most are the same two as Azure's [Chapter 4](#ch4) - the network answer and nothing public:

```bash
gcloud sql instances create psql-shopnow-dev \
  --database-version=POSTGRES_16 \
  --tier=db-custom-2-7680 \
  --region=europe-west3 \
  --availability-type=REGIONAL \
  --no-assign-ip \
  --network=projects/shopnow-dev-eu/global/networks/vpc-shopnow \
  --backup-start-time=03:00
```

`--no-assign-ip` is the flag that keeps the database off the internet (see the warning below), and the VPC path above uses **Private Service Connect** to attach a private IP inside `vpc-shopnow` from [Chapter 10](#ch10). The connection tool that makes the platform's security model usable from anywhere is the **Cloud SQL Auth Proxy**: a local binary (or sidecar container) that authenticates with your IAM identity and tunnels to the database over TLS - so developers, pipelines, and pods all connect the same way, with database usernames and passwords carried by the database, not the network. **IAM database authentication** takes it one step further and logs Postgres in with the Google identity, the passwordless story of both previous clouds.

Two siblings complete the picture and deserve their one paragraph each. **AlloyDB** is the premium PostgreSQL line - columnar engine, faster stock Postgres, the choice when Cloud SQL's ceiling shows up. **Spanner** is the horizontally scaled, globally consistent database for the day the workload outgrows vertical scaling entirely - a genuinely unique product, and a decision big enough to demand its own document, not a paragraph in a handbook.

::: {.warn}
**Watch out - a Cloud SQL instance without `--no-assign-ip` has a public IP**

Creating a Cloud SQL instance in the console or without the flag assigns a public IP and *authorizes* connections by network - which is a working default and a bad one. Public-IP-with-authorized-networks is a legacy posture, not a design. Create with private IP (the PSC path above), or at minimum pair the public IP with the Auth Proxy and IAM authentication and treat the public address as an inert string the platform happens to show you.
:::

## 11.4 The Data Path of the Running Example

shopnow's data path on GCP now reads end to end: assets in `gs://shopnow-assets-eu` behind uniform access and prevention ([Section 11.1](#ch11)), PostgreSQL in `psql-shopnow-dev` with private IP and regional HA ([Section 11.3](#ch11)), and the application tier - GKE in the next chapter, Cloud Run in the one after - connecting through the Auth Proxy as a sidecar or a Unix socket, with the service's own identity carrying the `roles/cloudsql.client` grant. The same three-layer shape as the AWS book's RDS chapter and Part I's database chapter, and the shape that [Chapter 15](#ch15) will deploy three times in one evening.

**See also:** [Chapter 10](#ch10) built the network this database lives on, [Chapter 12](#ch12) and [Chapter 13](#ch13) connect the application tier to it, and [Chapter 9](#ch9) owns the `roles/cloudsql.client` grant the Auth Proxy needs.
