# Chapter 12 - Security: TLS, Users, Roles, and API Keys {#ch12}

## 12.1 The Security Model, and What It Costs

Elasticsearch security used to be a paid feature and is now the default: since 8.0, a fresh cluster starts with security enabled - TLS on both layers, authentication required, generated certificates and an `elastic` bootstrap password - and since long before that (7.1), the **Basic** free tier has included the features a production cluster actually needs: TLS encryption, role-based access control, API keys, and basic audit-free operations. The chapters that follow this one assume a secured cluster; this chapter builds one from the sandbox of [Chapter 3](#ch3) and explains the model well enough to pass an audit conversation.

The model has three layers, each answering one question. **Authentication** - who are you: a user, an API key, a service account, a token. **Authorization** - what may you touch: roles granting index-, cluster-, and application-level privileges, optionally filtered to documents and fields. **Transport security** - who can listen: TLS on the HTTP layer (clients) and the transport layer (nodes), which is what keeps credentials and documents off the network between your edges. All three are configured in `elasticsearch.yml` and managed at runtime through the security APIs and Kibana's Stack Management.

## 12.2 TLS on Both Layers

Two TLS layers exist because two kinds of conversation exist. The **HTTP layer** (`xpack.security.http.ssl`) carries client traffic - Kibana, Agents, your curl - and its certificates are the ones browsers and shippers verify; certificates here come from your organization's CA (or a well-managed internal one). The **transport layer** (`xpack.security.transport.ssl`) carries node-to-node traffic - replication, cluster state, master elections - and is mandatory whenever security is on: an unencrypted transport layer means anyone on the segment can speak to your nodes as a peer, which is strictly worse than an HTTP exposure.

The certificate tooling ships with the distribution, and the minimal self-managed loop is:

```bash
# 1. Create a CA
bin/elasticsearch-certutil ca --out elastic-stack-ca.p12 --pass ""

# 2. Issue node certificates (one per node, or a wildcard)
bin/elasticsearch-certutil cert --ca elastic-stack-ca.p12 --out elastic-certificates.p12 --pass ""

# 3. Distribute to every node's config/certs/ and point the config at them
```

```yaml
xpack.security.transport.ssl.enabled: true
xpack.security.transport.ssl.verification_mode: certificate
xpack.security.transport.ssl.keystore.path: certs/elastic-certificates.p12
xpack.security.transport.ssl.truststore.path: certs/elastic-certificates.p12

xpack.security.http.ssl.enabled: true
xpack.security.http.ssl.keystore.path: certs/elastic-certificates.p12
```

`verification_mode: certificate` verifies the peer holds a cert signed by the trusted CA (the standard internal-cluster posture); `full` additionally verifies hostnames and is the internet-facing posture. Kibana and the shippers then need the HTTP layer's CA to trust: `elasticsearch.ssl.certificateAuthorities` in `kibana.yml`, the CA bundle in Filebeat/Agent output config. On Kubernetes, ECK ([Chapter 14](#ch14)) generates and rotates all of this automatically - one of the operator's strongest arguments - but the concepts it automates are these, and knowing them makes the operator's outputs readable.

## 12.3 Users and Roles: RBAC in Practice

Elasticsearch ships with built-in users (`elastic` - the superuser; `kibana_system` - what Kibana uses to talk to the cluster) and expects your humans and machines to be named users or keys with scoped roles. A **role** is a bundle of privileges over resources; users are assigned roles; the check happens per request:

```text
PUT _security/role/log-reader
{
  "indices": [
    {
      "names": ["logs-nginx-*", "logs-app-*"],
      "privileges": ["read", "view_index_metadata"],
      "field_security": { "grant": ["@timestamp", "service.name", "level", "url.*", "http.*", "message"] },
      "query": { "term": { "environment": "production" } }
    }
  ]
}

PUT _security/user/alice
{
  "password": "correct-horse-battery-staple",
  "roles": ["log-reader"],
  "full_name": "Alice Operator"
}
```

This one role demonstrates the whole authorization surface, because it narrows in three independent directions: **index-level** (`names` + `privileges` - Alice reads only `logs-*`), **field-level security** (FLS - she sees the listed fields, not credentials or secrets that share the index), and **document-level security** (DLS - the `query` filter makes non-production rows invisible to her, at the storage layer, not the UI layer). FLS and DLS are included in the free tier and are the features that let one log cluster serve many teams without copying data per tenant. Roles compose; `elastic` overrides everything; and the principle to operate by is the same as any RBAC system - nobody human gets the superuser password, including you, because everything worth doing is expressible in a role.

::: {.note}
**Best practice - roles in version control, users in the directory**

Role definitions are JSON, which means they belong in Git next to your other infrastructure code, applied by CI ([Chapter 14](#ch14) shows the pattern) - role drift is a security finding with a boring fix. Human users scale through your identity provider: the Basic tier includes native realms (file, native user store); SSO via SAML/OIDC and LDAP/Active Directory integration are Enterprise-tier features, so teams that need SSO either license it or bridge at the edge (Kibana behind an authenticating proxy).
:::

## 12.4 API Keys and Service Accounts

Machines should not share the `elastic` password either, and the modern mechanism is the **API key** - a credential pair (an `id` and a secret, shown once at creation) that authenticates as its own grant, independent of any human:

```text
POST /_security/api_key
{
  "name": "filebeat-nginx-prod",
  "expiration": "365d",
  "role_descriptors": {
    "log-writer": {
      "indices": [
        { "names": ["logs-nginx-*"], "privileges": ["create_doc", "create_index"] }
      ]
    }
  }
}
```

Keys carry their own role descriptors (narrower than their creator's), optional expiration, and individual revocation (`DELETE /_security/api_key/<id>`) - which is the operational win over shared passwords: one shipper compromised, one key rotated, nothing else moves. Fleet-managed Elastic Agents get this for free - per-agent keys, generated and revocable from the UI ([Chapter 4](#ch4)) - and hand-configured Beats and scripts should use explicitly created keys. **Service accounts** (`_security/service`) are Elastic's second machine identity type - built-in identities for first-party components (Kibana, Logstash) that authenticate with bearer tokens rather than keys; you will meet them in stack monitoring setups. The rule that survives contact with production: every writer gets its own credential, named after what it writes, with an expiration date, recorded where rotation is a routine and not an archaeology.

## 12.5 Securing the Sandbox and Kibana

Turning the Chapter 3 sandbox into a secured single-node stack is a fifteen-minute exercise that touches every concept in this chapter, and it is the bridge between "learning config" and "runnable for real":

1. Remove `xpack.security.enabled=false` from the Elasticsearch environment; keep `discovery.type=single-node`.
2. On first start, run the reset tool inside the container: `bin/elasticsearch-reset-password -u elastic -i` - set a real password; this is the bootstrap superuser credential.
3. Generate certificates with `elasticsearch-certutil` as in Section 12.2, mount them, and enable both SSL blocks in `elasticsearch.yml`.
4. Point Kibana at the secured cluster: `ELASTICSEARCH_HOSTS=https://elasticsearch:9200`, `ELASTICSEARCH_USERNAME: kibana_system` (password via the keystore tool `bin/kibana-keystore create`), `ELASTICSEARCH_SSL_CERTIFICATEAUTHORITIES` at the CA, plus `xpack.encryptedSavedObjects` keys for alerting credentials.
5. Log in as `elastic`, create named users and the `log-reader` role of Section 12.3, then create the Filebeat API key of Section 12.4 and switch the shipper's output to `https://` with that key.
6. Verify the negative case: `curl http://localhost:9200` (no TLS) now fails, and a request without credentials gets a 401 with a `security_exception` body - the two rejections that prove the layers are up.

::: {.warn}
**Watch out - security that is on but unverified is a rumor**

Every security change should end with a *negative* test: the wrong user cannot read the index, the expired key gets 401, the DLS query hides the document you know is there. Positive tests ("Alice can log in") prove plumbing; negative tests prove policy - and audits, like attackers, test the second kind.
:::

**See also:** [Chapter 13](#ch13) makes sure the `.security` indices ride your snapshots, and [Chapter 14](#ch14) automates this chapter's manual loop on Kubernetes.
