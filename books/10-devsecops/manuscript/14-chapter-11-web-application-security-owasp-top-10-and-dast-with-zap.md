# Chapter 11 - Web Application Security: OWASP Top 10 and DAST with ZAP {#ch11}

## 11.1 SAST Sees Code; DAST Sees the Running System

Semgrep and CodeQL ([Chapter 4](#ch4)) analyze what the developer wrote; **dynamic application security testing (DAST)** attacks what is actually deployed - the running HTTP surface with its real headers, real redirects, real authentication, and the misconfigurations that exist only in the assembled system. The two find different defects: no static scanner notices that a staging endpoint returns stack traces, that a cookie lacks `Secure`, or that `/admin` answers 200 without a session - because those are *runtime* properties. This chapter pairs the OWASP Top 10 (the industry's consensus taxonomy of web application risk) with the OWASP Zed Attack Proxy (**ZAP**), the standard open-source DAST scanner, running as a gate in the same CI pipeline as everything else in Part I.

## 11.2 The OWASP Top 10, Mapped to `shopnow`

The Top 10 (2021 edition) is worth knowing as a vocabulary, and it maps cleanly onto controls this series already has or builds here:

| OWASP 2021 | The failure, concretely | Control in this series |
|---|---|---|
| A01 Broken Access Control | `/orders/1042` returns *anyone's* order when IDs are guessed (IDOR) | Authorization tests ([11.5](#ch11)); audit logs ([Chapter 12](#ch12)) |
| A02 Cryptographic Failures | Plaintext HTTP, weak TLS config, unhashed passwords | TLS at ingress; secrets in Vault ([Chapter 2](#ch2)) |
| A03 Injection | SQL built by string concatenation; command injection | Semgrep patterns ([Chapter 4](#ch4)); parameterized queries |
| A05 Security Misconfiguration | Verbose errors, default creds, directory listing, debug endpoints | ZAP baseline (this chapter); IaC scanning ([Chapter 10](#ch10)) |
| A07 Identification & Auth Failures | Weak passwords, no rate limit, session tokens that never expire | Rate limiting at ingress; session hygiene |
| A08 Software & Data Integrity Failures | Unsigned artifacts, unverified updates | Signing and provenance ([Chapter 6](#ch6)) |
| A10 Server-Side Request Forgery | App fetches an attacker-supplied URL from inside the network | Egress NetworkPolicy ([Chapter 9](#ch9)); input validation |

: Table 11.1 - The OWASP Top 10 (2021) against the series' running platform (full list of ten at owasp.org; the rows above are where the series has the most to say)

The mapping cuts both ways and is worth internalizing: the pipeline controls of Part I exist largely for **A08**, the cluster controls of Part II for **A10**, and the *application's own code* remains the owner of **A01** - no admission policy or scanner can decide for `shopnow` whether user 42 may read order 1042. That decision is a code review with an authorization test attached, which is why access control gets its own section at the end of this chapter.

## 11.3 Secure Defaults at the Edge

Most Top 10 findings in a containerized stack are fixed once, at the ingress, rather than per endpoint. The `shopnow` ingress (nginx from the Kubernetes book) carries the security headers, TLS, and rate limiting as platform-level defaults:

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/limit-rps: "20"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "Content-Security-Policy: default-src 'self'";
      more_set_headers "Referrer-Policy: strict-origin-when-cross-origin";
```

HSTS forces TLS for returning browsers, `nosniff` and CSP close the injection-adjacent browser primitives, and the rate limit turns credential stuffing from a script into a job. These are one-time defaults that every route inherits - the "make the compliant path the zero-effort path" principle from [Chapter 8](#ch8), applied at the edge.

## 11.4 The ZAP Baseline in CI

ZAP's **baseline scan** is the pragmatic CI entry point: a passive crawl of the running application that flags missing security headers, cookie flags, TLS issues, information leaks in errors, and CSP weaknesses - without actively attacking, which keeps it safe against staging. The scan runs in the deploy pipeline against the *staging* environment, after deploy, before production promotion:

```yaml
  dast:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - name: ZAP baseline scan
        uses: zaproxy/action-baseline@b3448ba9c66c1a4d99a48ef6ac4f47e7a71c873a # v0.12.0
        with:
          target: 'https://staging.shopnow.example'
          fail_action: true
          allow_issue_writing: false
```

The gate policy follows the series pattern - fail on the alerts that are unambiguous (missing HSTS, no `Secure` on session cookies, error pages with stack traces), report the rest into the pull request or the Security tab. A **full scan** (active attack mode: fuzzing, injection probes) is for a scheduled weekly job against staging with a test data set, never casually against production, and never against anything an external SLA protects. DAST's honest limitation is coverage: ZAP crawls what it can reach and authenticate to, so the baseline catches the platform layer reliably but sees nothing behind login unless given one authenticated session (ZAP's auth context configuration or a replayed session token) - which is exactly why [11.5](#ch11) exists.

## 11.5 The Control No Scanner Owns: Authorization

Broken access control tops the OWASP list for a reason: it is not a pattern in code but a decision about every endpoint, and scanners mostly cannot see it. The engineering fix is test-shaped: for `shopnow`, a table-driven authorization test suite that asserts, for each sensitive endpoint, the matrix of *who may do what* - user A reading user B's order must be 404, not 200; the admin endpoint must be 403 for a plain user; the ID in the URL must be checked against the session principal server-side, every time. These tests run in the same `quality-gates` job as SAST, and a new endpoint without its authorization test is a code review failure, because [Chapter 1](#ch1)'s rule applies with extra force here: a control that is not automated is not a control. When an IDOR *does* reach production, the audit logs of [Chapter 12](#ch12) are what turn a suspicious support ticket into a bounded, evidenced incident.

**See also:** [Chapter 12](#ch12) records what the scanners and attackers both probe; the OWASP Top 10 and ZAP project documentation own the moving details of rules and scan modes; the Kubernetes book's ingress chapter holds the full ingress annotation reference.
