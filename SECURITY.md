# Security Policy

> Security policy and vulnerability reporting procedures for LIA

**Version**: 1.1
**Date**: 2026-07-16
**Last Updated**: 2026-07-16
**Next review**: 2027-01-31

---

## Table of Contents

- [Supported Versions](#supported-versions)
- [Reporting a Vulnerability](#reporting-a-vulnerability)
- [Security Measures](#security-measures)
- [Security Best Practices](#security-best-practices)
- [Standards Mapping](#standards-mapping)
- [Security Updates](#security-updates)
- [Contact](#contact)

---

## Supported Versions

LIA follows semantic versioning on a single `1.x` line. Security fixes land on
the latest release; there is no long-term-support branch for older minors.

| Version | Supported | Notes |
|---------|-----------|-------|
| Latest `1.x` release | :white_check_mark: | Actively maintained — apply security fixes here |
| Older `1.x` releases | :warning: | Best effort — please upgrade to the latest release |
| `< 1.0` | :x: | Pre-release, unsupported |

**Recommendation**: always run the latest release for the best security posture.

---

## Reporting a Vulnerability

### Do NOT report publicly

> **IMPORTANT**: do NOT create a public GitHub issue for a security
> vulnerability. Public disclosure before a fix is available puts users at risk.

### Private disclosure process

**Step 1 — Report privately.** Use GitHub's private vulnerability reporting:

- **[Report a vulnerability](https://github.com/jgouviergmail/LIA-Assistant/security/advisories/new)**
  (Repository → **Security** → **Report a vulnerability**)

A machine-readable contact is published at
[`/.well-known/security.txt`](apps/web/public/.well-known/security.txt) (RFC 9116).

Please include, where possible:

| Information | Description |
|-------------|-------------|
| **Summary** | Short description (e.g. "IDOR in `/api/v1/...`") |
| **Details** | What the issue is and why it is a problem |
| **Reproduction** | Clear, minimal steps |
| **Impact** | Data exposure, privilege escalation, DoS, … |
| **Affected version** | Release/commit you tested |
| **Suggested fix** | Optional |

**Step 2 — Acknowledgment.** We aim to acknowledge a report within **7 days**.

**Step 3 — Assessment & fix.** We triage by severity (CVSS), develop a fix, and
coordinate a disclosure timeline with you. Complex issues may take longer; we
will keep you informed.

**Step 4 — Resolution.** Once fixed, a security advisory is published, a CVE is
requested when applicable, and credit is given if desired.

> Timelines are best-effort commitments from a small maintainer team, not a
> contractual SLA.

### In scope

Authentication/authorization bypass, session handling, injection (SQL, command,
etc.), SSRF, sensitive-data exposure (including secrets in logs), cryptographic
misuse, insecure defaults, prompt-injection / agent-tool abuse, and known-CVE
dependencies.

### Out of scope

Self-XSS requiring attacker-controlled victim actions, social engineering,
physical attacks, DoS against development-only endpoints, and best-practice
hardening findings with no demonstrated impact.

---

## Security Measures

The controls below are implemented in the codebase and configuration. This list
is descriptive, not a guarantee of completeness — see
[Standards Mapping](#standards-mapping).

### Authentication & authorization

| Measure | Implementation |
|---------|----------------|
| **OAuth 2.1** | PKCE (S256) required on OAuth flows; `state` (CSRF) validated single-use |
| **BFF pattern** | Server-side sessions; auth cookie is `HttpOnly` + `Secure`, never in `localStorage` |
| **Sessions** | Redis-backed, server-side validation, rotation on login |
| **Passwords** | Hashed with bcrypt; strength validation on set/reset |
| **Verification / reset tokens** | Single-use (JTI), Redis-blacklisted after use, short TTL |
| **Ownership checks** | Resource access is authorized per-owner across API routes |

### Data protection

| Measure | Implementation |
|---------|----------------|
| **Encryption at rest** | Fernet encryption for connector/OAuth credentials and selected sensitive fields |
| **Encryption in transit** | TLS 1.2/1.3 only (1.0/1.1 rejected) at the public edge |
| **Log hygiene** | Central structured-log PII filter: email pseudonymization, secret/token redaction, OAuth `state` fingerprinting, URL query-credential stripping |
| **Data-subject rights** | Data export and cascade erasure (account lifecycle) |

### API & application

| Measure | Implementation |
|---------|----------------|
| **Rate limiting** | Redis-based limits on authentication and other sensitive endpoints |
| **Input validation** | Pydantic v2 (backend) and Zod (frontend), strict schemas |
| **Output handling** | Markdown sanitization (`rehypeSanitize`), JSON-LD escaping |
| **Security headers** | CSP, `nosniff`, COOP/COEP, frame protections, HSTS |
| **CORS** | Allowlist-based origin validation |
| **Widget isolation** | Third-party MCP-App widgets run in a sandboxed, opaque-origin iframe |

### LLM / agent security

| Measure | Implementation |
|---------|----------------|
| **HITL controls** | Human approval interrupts for sensitive/destructive tool calls |
| **Semantic validation** | Plan/argument validation before execution |
| **Bounded agency** | Loop/token/time limits; read-only, allowlisted sub-agents |
| **Token attribution** | Per-user usage tracking and budgets |

### Supply chain & CI

| Measure | Implementation |
|---------|----------------|
| **Dependency scanning** | `pip-audit`, `pnpm audit`, Trivy |
| **Code scanning** | CodeQL, Bandit, Ruff security rules, Semgrep |
| **Secret scanning** | Gitleaks |
| **Pinned actions** | GitHub Actions pinned by commit SHA |
| **SBOM** | Generated in CI |

---

## Security Best Practices

### For contributors

| Practice | Description |
|----------|-------------|
| **No secrets in code** | Use `.env`; never commit real credentials |
| **Validate input** | Pydantic (backend) / Zod (frontend) |
| **No raw SQL** | Use the SQLAlchemy ORM / parameterized queries |
| **No secrets in logs** | Rely on the central PII filter; never log tokens, `state`, or signed URLs |
| **Vet dependencies** | Check advisories before adding a dependency |

### For operators

| Practice | Description |
|----------|-------------|
| **Restrict `.env`** | Owner-only permissions (`0600`) on secret files |
| **HTTPS only** | Terminate TLS at the edge; enable HSTS |
| **Isolate data stores** | Never expose PostgreSQL/Redis to the internet |
| **Patch promptly** | Apply OS and dependency security updates |
| **Monitor** | Enable alerting on suspicious activity |

---

## Standards Mapping

LIA's controls are mapped to the **OWASP Top 10**, **OWASP ASVS**, and the
**OWASP GenAI / LLM** guidance, and are reviewed through periodic internal
security audits (see [`docs/audit/`](docs/audit/)). This mapping is a working
reference to guide hardening — it is **not** a certification, an attestation, or
a claim of complete mitigation. Findings from each audit are tracked and
remediated on a risk-prioritized basis.

Data-subject rights relevant to GDPR (access/export and erasure) are supported
through the account-lifecycle features.

---

## Security Updates

Security advisories are published via the repository's **Security** tab and
referenced in release notes and the `CHANGELOG`. Severity guides urgency:

| Severity (CVSS) | Target |
|-----------------|--------|
| Critical (≥ 9.0) | Fast-tracked patch release |
| High (7.0–8.9) | Prioritized, typically within days |
| Medium (4.0–6.9) | Next scheduled release |
| Low (< 4.0) | Best effort |

Dependencies are monitored continuously (Dependabot) and scanned in CI.

---

## Contact

Report vulnerabilities through **[GitHub Security Advisories](https://github.com/jgouviergmail/LIA-Assistant/security/advisories/new)**
(the machine-readable entry point is [`/.well-known/security.txt`](apps/web/public/.well-known/security.txt)).

For sensitive details, mention it in your initial report and we will agree on a
secure channel.

---

## Acknowledgments

We thank the security researchers who help improve LIA. Report a valid
vulnerability to be credited (with your consent) in the advisory.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **1.1** | 2026-07-16 | Corrected supported versions to the `1.x` line; moved reporting to GitHub Security Advisories; added RFC 9116 `security.txt`; removed unverified control claims; reframed the OWASP matrix as a non-certifying standards mapping |
| **1.0** | 2026-02-03 | Initial security policy |

---

<p align="center">
  <strong>LIA</strong> — Security is a priority, not an afterthought
</p>
