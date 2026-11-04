# Chapter 2 - IAM: Identity, Roles, and Least Privilege {#ch2}

## 2.1 The Four Primitives: Users, Groups, Roles, Policies

Every API call in this book was authenticated by an **IAM identity** and authorized by an **IAM policy** - and since every other service is behind that gate, IAM is the chapter that pays interest on itself for the rest of your career. The model has four primitives, and the fastest way to keep them straight is to ask *who* each one is. An **IAM user** is a named identity with permanent credentials, meant for a single human or machine - in 2026 the honest advice is that almost no new users should be created (humans federate through Identity Center per Section 2.5, machines assume roles per Section 2.4). An **IAM group** is a collection of users that shares attached policies; it is an administrative convenience for humans, not an identity that can authenticate. An **IAM role** is an identity with *no* permanent credentials: it is assumable, and whoever assumes it receives temporary credentials from **STS** (the Security Token Service) that expire on their own. An **IAM policy** is the document that defines permissions, and it is the only place where *what is allowed* actually lives.

The mental model that survives contact with production: *users and roles are who, policies are what, groups and trust policies are how access gets organized and delegated*. When something cannot talk to something else in AWS, the debugging path is nearly always the same three questions - who authenticated, under what policy, and against which resource - and Sections 2.2 through 2.7 give each question a concrete answer.

## 2.2 Anatomy of a Policy Document

Policies are JSON documents built from statements. Here is a real one from the running example - a policy that lets a service read a specific S3 bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadAssetsBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::shopnow-assets",
        "arn:aws:s3:::shopnow-assets/*"
      ]
    }
  ]
}
```

Four fields do the work. `Effect` is `Allow` or `Deny` - and an explicit `Deny` wins over any `Allow`, anywhere in the evaluation, which is how SCPs and guardrails (Section 2.7) forbid things no other policy can re-permit. `Action` names API operations in `service:operation` form, and its plurals matter: `s3:GetObject` grants object reads, `s3:ListBucket` grants bucket listing - two different operations on two different ARN shapes, which is why the `Resource` block needs both the bucket ARN (`s3:::shopnow-assets`) and the object wildcard beneath it (`s3:::shopnow-assets/*`). `Resource` is an **ARN** - `arn:partition:service:region:account-id:resource` - and IAM is the service where ARNs become daily vocabulary. `Condition` adds fine-grained gates such as MFA requirements, source restrictions, or tag matches, and it is the difference between a policy that is merely correct and one that is defensible.

Evaluation is deny-by-default: if no statement allows the call, it fails with `AccessDenied`, and the two remedies are granting narrowly or - in diagnosis - reading the message, because since 2023 `AccessDenied` errors can carry policy and principal context when explicitly enabled, which turns guesswork into reading.

## 2.3 Managed vs Inline Policies

A policy exists independently of who uses it, and where it lives determines how it ages. **Customer managed policies** are standalone objects you attach to many identities; when the permissions change, one edit updates every principal that carries it, and versioning keeps history. **AWS managed policies** are Amazon's pre-built common bundles - `AmazonS3ReadOnlyAccess`, `PowerUserAccess` - useful for learning and dangerously broad for production (`ReadOnlyAccess` spans every service, which is rarely what "read-only" means to a business). **Inline policies** are embedded in a single identity, cannot be reused, and are easy to lose track of; their legitimate niche is one-off, deliberately personal permissions. The working rule: customer managed policies as the default, AWS managed ones read before trusting, inline ones treated as tech debt with a reason attached.

::: {.warn}
**Watch out - the wildcard habit**

`"Action": "*"` on `"Resource": "*"` is how every credential-leak postmortem begins. Wildcards have honest uses - `s3:GetObject` on `arn:aws:s3:::bucket/*` scopes the wildcard to the *resource*, not the action namespace - but `Action: "*"` attached to a human or a CI role means the next mistake is unrecoverable. If a policy needs a wildcard to work, narrow the resource first and the action second.
:::

## 2.4 Roles: The Identity That Changed the Industry

A role has two attached documents. The **permissions policy** is the JSON of Section 2.2. The **trust policy** says *who may assume this role* - another AWS principal, an AWS service (`ec2.amazonaws.com`, `eks.amazonaws.com`), an external identity provider such as GitHub's OIDC endpoint, or another account. Assuming it yields temporary credentials that expire automatically and rotate without anyone rotating anything.

This single mechanic explains most of what makes AWS feel different from a rack of servers. An EC2 instance launched with an **instance profile** can call `aws s3 ls` with no keys stored anywhere on the disk - the credentials arrive through the Instance Metadata Service and rotate continuously. A Lambda function *is* an execution role ([Chapter 8](#ch8)). A Kubernetes pod assumes a role through IRSA ([Chapter 7](#ch7)). A GitHub Actions pipeline assumes one per run ([Chapter 9](#ch9)), and the book's CI story is deliberately built on `id-token` federation instead of stored keys. Learning to ask "what role does this thing run as?" instead of "where are the keys?" is the habit that separates AWS-native thinking from server thinking.

```bash
# What identity am I right now? (the reflex from Chapter 1)
aws sts get-caller-identity
# Assume a role and get temporary credentials for an hour
aws sts assume-role \
  --role-arn arn:aws:iam::111122223333:role/platform-auditor \
  --role-session-name alice-audit
```

## 2.5 Humans: Identity Center, MFA, and Federation

For people, the modern answer is **IAM Identity Center**: named users live in it (or federate from your corporate IdP), get assigned **permission sets** - managed policies with session controls - to specific accounts, and sign in through a portal that issues temporary role sessions per account. No IAM users to provision per account, no access keys to rotate for humans, one place to revoke a leaver. Whether you are running Identity Center or a classic IAM user during migration, **MFA is not optional**: a password alone on an identity that can touch production is the finding auditors lead with. On the CLI side, humans should resolve to role sessions as well - short-lived credentials from Identity Center or `sts assume-role`, never a 90-day static key in a dotfile.

::: {.note}
**Best practice - least privilege is a process, not a launch requirement**

Nobody writes the perfect policy on day one, and pretending to is how teams end up with `AdministratorAccess` as a permanent condition. The working loop: grant a scoping-down of what the task needs, let it run, then read **IAM Access Analyzer** and the **last-used** timestamps on permissions to find what was never touched, and remove it on a schedule. Least privilege that is revisited monthly beats perfect privilege that never ships.
:::

## 2.6 Machines and Keys: The Last Resort

The honest hierarchy for non-human access, best first: *roles on the platform* (instance profiles, task roles, execution roles - the credential never exists as a secret at all); *OIDC-federated roles for external CI* ([Chapter 9](#ch9)); *`sts assume-role` sessions issued from your IdP*; and only then, when nothing else is possible, an **access key pair** on an IAM user - stored in a secrets manager, scoped to one service, and rotated on a schedule. Access keys are the credentials that leak in git commits and appear in breach dumps; they also happen to be the easiest to create, which is exactly why the path of least resistance needs a policy. The IAM **credential report** lists every user's keys, their age, and their last rotation, and makes a grimly effective monthly reading exercise.

## 2.7 Guardrails: Boundaries, SCPs, and the Analyzer

Three mechanisms sit above individual policies. A **permissions boundary** is a policy attached to a role or user that caps the maximum it can ever have, no matter what other policies grant - the standard way to let teams create their own roles without letting them escalate to admin. **Service Control Policies** are boundaries at the organization level: they apply to every account beneath them, and the classic SCP denies leaving a security group open to `0.0.0.0/0` on port 22 or creating IAM users with keys, making whole classes of mistake impossible rather than forbidden. **IAM Access Analyzer** reasons from outside in: it finds resources reachable from outside the account (a public bucket, a role trusted by a foreign principal) and can generate least-privilege policies from observed activity. Together they express the real goal of the chapter: not that every engineer is careful, but that the account makes carelessness survivable.

**See also:** every later chapter uses roles rather than keys; the pattern's flagship cases are instance profiles in [Chapter 3](#ch3), IRSA in [Chapter 7](#ch7), execution roles in [Chapter 8](#ch8), and the OIDC pipeline in [Chapter 9](#ch9). Appendix C collects the `AccessDenied` troubleshooting recipes that this chapter's model makes readable.
