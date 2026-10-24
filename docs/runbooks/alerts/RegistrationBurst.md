# RegistrationBurst - Runbook

**Severity**: Warning
**Component**: Authentication (sign-up)
**Impact**: None by itself — a new account stays inactive until an administrator activates it; each password sign-up still sends a verification e-mail to the address it names
**SLA Impact**: No

---

## 📊 Alert Definition

**Alert Name**: `RegistrationBurst` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression** (template form):
```promql
round(
  (sum(increase(user_registrations_total{status="success"}[1h])) or vector(0))
  + (sum(increase(oauth_user_creation_total[1h])) or vector(0))
) > THRESHOLD
```

`for: 5m`. `THRESHOLD` is `ALERT_CORE_REGISTRATIONS_PER_HOUR`
(`infrastructure/observability/prometheus/thresholds/*.env`). The two counters are the
two ways an account is created — a password sign-up and a first Google sign-in — and each
`or vector(0)` keeps the sum alive while one of them has never fired
([ADR-363](../../architecture/ADR-363-Password-Reset-Bounded-Per-Account-And-Bound-To-It.md)).

**Labels**:
- `severity`: warning
- `component`: auth
- `tier`: core

---

## 🔍 Symptoms

- Dashboard 09, row « Account security »: the registrations panel climbs well above its
  usual handful a day.
- The administration's user list, sorted by creation date, shows many new inactive
  accounts, often with throwaway domains or addresses at the instance's own domain.

---

## 🎯 Possible Causes

### A script creates accounts
The 2026-10-23 incident: about twenty accounts in an afternoon, unverified addresses at
the instance's own domain and at `example.com`, two verified throwaway addresses used to
learn the password-reset flow.

### A real wave of sign-ups
An announcement or a shared link — the accounts then carry ordinary addresses and verify
them.

---

## 🔧 Diagnosis

1. How many, and how:
   ```promql
   sum(increase(user_registrations_total{status="success"}[1h]))
   sum by (provider) (increase(oauth_user_creation_total[1h]))
   ```
2. In Loki (`container="lia-api-prod"`): the `user_registered` and
   `new_user_created_via_oauth` events, and the client addresses of their requests.

---

## 🛠️ Resolution

- Delete the throwaway accounts from the administrator list (inactive accounts reach no
  feature in the meantime).
- If the instance runs no bot check yet, turn on Cloudflare Turnstile ([ADR-364](../../architecture/ADR-364-Turnstile-Bot-Check-On-The-Password-Doors.md),
  `docs/guides/GUIDE_SELF_HOSTING.md` § 4.6): a script that never runs a browser is then
  refused at the sign-up door. Google sign-ups are not covered by it yet.
- If it persists, block the source at the edge (a Cloudflare rule on
  `/api/v1/auth/register`).

---

## ✅ Verification

The registrations panel falls back to its usual level; the alert resolves within an hour
of the last sign-up of the burst (the length of its window).
