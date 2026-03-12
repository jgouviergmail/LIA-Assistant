# Security Policy

> Security policy and vulnerability reporting procedures for LIA

**Version**: 1.0
**Date**: 2026-02-03
**Last Updated**: 2026-02-03

---

## Table of Contents

- [Supported Versions](#supported-versions)
- [Reporting a Vulnerability](#reporting-a-vulnerability)
- [Security Measures](#security-measures)
- [Security Best Practices](#security-best-practices)
- [Compliance](#compliance)
- [Security Updates](#security-updates)
- [Contact](#contact)

---

## Supported Versions

We provide security updates for the following versions:

| Version | Supported | Notes |
|---------|-----------|-------|
| 6.x.x | :white_check_mark: | Current release, full support |
| 5.5.x | :white_check_mark: | Security patches only |
| 5.x.x | :x: | No longer supported |
| < 5.0 | :x: | No longer supported |

**Recommendation**: Always use the latest version for the best security posture.

---

## Reporting a Vulnerability

### Do NOT Report Publicly

> **IMPORTANT**: Do NOT create public GitHub Issues for security vulnerabilities.

Public disclosure before a fix is available can put users at risk. Please follow the private disclosure process below.

### Private Disclosure Process

**Step 1: Contact Us**

Send an email to **security@lia-assistant.dev** with:

| Information | Description |
|-------------|-------------|
| **Subject** | Brief description (e.g., "SQL Injection in /api/v1/users") |
| **Description** | Detailed description of the vulnerability |
| **Steps to Reproduce** | Clear reproduction steps |
| **Impact** | Potential impact (data exposure, privilege escalation, etc.) |
| **Affected Versions** | Which versions are affected |
| **Suggested Fix** | Optional: your suggested remediation |
| **Your Contact** | How to reach you for follow-up |

**Step 2: Acknowledgment**

We will acknowledge receipt within **48 hours**.

**Step 3: Investigation**

We will investigate and keep you informed of progress:

| Timeline | Action |
|----------|--------|
| 48 hours | Acknowledgment |
| 7 days | Initial assessment |
| 30 days | Patch development |
| 45 days | Public disclosure (coordinated) |

**Step 4: Resolution**

Once fixed:
- Security advisory published
- CVE assigned (if applicable)
- Credit given (if desired)
- Patch released

### Bug Bounty

Currently, we do not have a formal bug bounty program. However, we recognize security researchers in our security advisories and CHANGELOG when appropriate.

### What We Consider Security Issues

| Category | Examples |
|----------|----------|
| **Authentication** | Bypass, session hijacking, credential exposure |
| **Authorization** | Privilege escalation, IDOR, access control bypass |
| **Injection** | SQL, NoSQL, command, LDAP, XPath injection |
| **Data Exposure** | PII leaks, sensitive data in logs, unencrypted storage |
| **Cryptographic** | Weak algorithms, key exposure, improper implementation |
| **Configuration** | Insecure defaults, debug mode in production |
| **Dependencies** | Known CVEs in third-party packages |

### What We Do NOT Consider Security Issues

| Category | Reason |
|----------|--------|
| Rate limiting bypasses on non-critical endpoints | Expected behavior |
| Missing security headers (unless exploitable) | Best practice, not vulnerability |
| Self-XSS | Requires attacker-controlled victim actions |
| Social engineering | Not a technical vulnerability |
| Physical attacks | Out of scope |
| DoS on development endpoints | Expected behavior |

---

## Security Measures

### Authentication & Authorization

| Measure | Implementation |
|---------|----------------|
| **OAuth 2.1** | PKCE (S256) mandatory for all OAuth flows |
| **BFF Pattern** | HTTP-only cookies, no tokens in localStorage |
| **Session Management** | Redis-backed, 24h TTL, server-side validation |
| **Password Storage** | bcrypt with 12 rounds |
| **JWT** | RS256 signing, short expiry (15min access, 7d refresh) |

### Data Protection

| Measure | Implementation |
|---------|----------------|
| **Encryption at Rest** | Fernet encryption for OAuth credentials |
| **Encryption in Transit** | TLS 1.3 mandatory |
| **PII Filtering** | Automatic PII detection and masking in logs |
| **Data Minimization** | Only collect necessary data |
| **GDPR Compliance** | Full data export and deletion capabilities |

### API Security

| Measure | Implementation |
|---------|----------------|
| **Rate Limiting** | Redis-based sliding window (60 req/min default) |
| **Input Validation** | Pydantic v2 with strict mode |
| **Output Encoding** | Automatic JSON encoding |
| **CORS** | Whitelist-based origin validation |
| **CSRF Protection** | SameSite=Lax cookies |

### Infrastructure Security

| Measure | Implementation |
|---------|----------------|
| **Container Security** | Non-root users, read-only filesystems |
| **Secrets Management** | Environment variables, never in code |
| **Dependency Scanning** | Automated via pip-audit, safety, trivy |
| **Code Scanning** | CodeQL, bandit, Ruff security rules |
| **Network Security** | Internal networks, minimal port exposure |

### LLM-Specific Security

| Measure | Implementation |
|---------|----------------|
| **Prompt Injection** | Input sanitization, output validation |
| **Token Tracking** | Per-user attribution, budget controls |
| **HITL Controls** | Human approval for high-risk operations |
| **Data Privacy** | No user data sent to LLM training |
| **API Key Security** | Encrypted storage, masked logging |

---

## Security Best Practices

### For Contributors

| Practice | Description |
|----------|-------------|
| **No Secrets in Code** | Use `.env`, never commit credentials |
| **Input Validation** | Always validate user input with Pydantic/Zod |
| **Parameterized Queries** | Use SQLAlchemy ORM, never raw SQL |
| **Secure Dependencies** | Check CVEs before adding dependencies |
| **Code Review** | Security-focused review for auth/data handling |

### For Operators

| Practice | Description |
|----------|-------------|
| **Environment Variables** | Use `.env.prod` with real secrets |
| **HTTPS Only** | Terminate TLS at load balancer |
| **Firewall Rules** | Restrict database/Redis access |
| **Regular Updates** | Apply security patches promptly |
| **Monitoring** | Enable alerting for suspicious activity |

### Security Checklist

Before deployment:

- [ ] All secrets in environment variables
- [ ] HTTPS enabled with valid certificate
- [ ] Database not exposed to internet
- [ ] Redis password protected
- [ ] Rate limiting enabled
- [ ] PII filtering enabled in logs
- [ ] Monitoring and alerting configured
- [ ] Backup strategy implemented
- [ ] Incident response plan documented

---

## Compliance

### OWASP Top 10 2024

| Vulnerability | Mitigation Status |
|---------------|-------------------|
| A01 - Broken Access Control | :white_check_mark: Authorization checks on all endpoints |
| A02 - Cryptographic Failures | :white_check_mark: TLS 1.3, Fernet, bcrypt |
| A03 - Injection | :white_check_mark: SQLAlchemy ORM, Pydantic validation |
| A04 - Insecure Design | :white_check_mark: BFF Pattern, HITL approval flows |
| A05 - Security Misconfiguration | :white_check_mark: Secure defaults, .env template |
| A06 - Vulnerable Components | :white_check_mark: Automated scanning (Dependabot, pip-audit) |
| A07 - Auth Failures | :white_check_mark: OAuth 2.1 PKCE, session timeout |
| A08 - Software Integrity | :white_check_mark: SBOM generation, signed commits |
| A09 - Logging Failures | :white_check_mark: Structured logging with PII filter |
| A10 - SSRF | :white_check_mark: URL validation, no user-controlled requests |

### GDPR

| Requirement | Implementation |
|-------------|----------------|
| Right to Access | Data export endpoint |
| Right to Erasure | GDPR deletion cascade |
| Data Minimization | Only necessary fields collected |
| Purpose Limitation | Clear data usage policies |
| Consent | Explicit opt-in for data collection |
| Breach Notification | Incident response procedures |

### SOC 2 (Preparation)

We are implementing controls towards SOC 2 Type II compliance:

- Security policies documented
- Access controls enforced
- Audit logging enabled
- Incident response procedures
- Change management process

---

## Security Updates

### Notification Channels

Security updates are announced via:

| Channel | URL/Contact |
|---------|-------------|
| GitHub Security Advisories | Repository Security tab |
| Release Notes | GitHub Releases |
| Email (critical) | Registered users |

### Update Frequency

| Type | Frequency |
|------|-----------|
| Critical (CVSS ≥ 9.0) | Immediate patch release |
| High (CVSS 7.0-8.9) | Within 7 days |
| Medium (CVSS 4.0-6.9) | Next scheduled release |
| Low (CVSS < 4.0) | Best effort |

### Dependency Updates

We regularly update dependencies:

| Tool | Frequency |
|------|-----------|
| Dependabot | Daily PR checks |
| pip-audit | Weekly scans |
| Trivy | On each build |
| npm audit | On each build |

---

## Contact

### Security Team

| Contact | Usage |
|---------|-------|
| **security@lia-assistant.dev** | Report vulnerabilities |
| **conduct@lia-assistant.dev** | Code of conduct issues |
| **contact@lia-assistant.dev** | General inquiries |

### Encrypted Communications

If you need to communicate sensitive details about a vulnerability, please mention it in your initial report and we will establish a secure communication channel.

### Response Times

| Priority | Response Time |
|----------|---------------|
| Critical | < 4 hours |
| High | < 24 hours |
| Medium | < 48 hours |
| Low | < 7 days |

---

## Acknowledgments

We thank the security researchers who have helped improve LIA's security:

| Researcher | Date | Issue |
|------------|------|-------|
| *Your name could be here* | — | — |

Want to be listed? Report a valid security vulnerability!

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **1.0** | 2026-02-03 | Initial security policy |

---

<p align="center">
  <strong>LIA</strong> — Security is a priority, not an afterthought
</p>

<p align="center">
  Report issues: security@lia-assistant.dev
</p>
