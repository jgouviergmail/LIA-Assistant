# PasswordResetAbuse - Runbook

**Severity**: Warning
**Component**: Authentication (password reset)
**Impact**: None on the account by itself — nothing leaves past an account's e-mail budget and an administrator is never sent a link; the signal is that someone is aiming the reset route at an account
**SLA Impact**: No

---

## 📊 Alert Definition

**Alert Name**: `PasswordResetAbuse` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression** (template form):
```promql
(round(sum(increase(password_reset_requests_total{outcome="throttled"}[1h]))) > THRESHOLD)
or
(round(sum(increase(password_reset_requests_total{outcome="refused_superuser"}[1h]))) > 0)
```

`for: 5m`. `THRESHOLD` is `ALERT_CORE_PASSWORD_RESET_THROTTLED_PER_HOUR`
(`infrastructure/observability/prometheus/thresholds/*.env`). `round()` is there because
`increase()` extrapolates slightly at the edges of its window: without it, two refusals
could read as 2.02 and pass a threshold of two.

`POST /api/v1/auth/request-password-reset` answers the same sentence whatever it did, so
an address never reveals an account. What it did is counted on
`password_reset_requests_total{outcome}`
([ADR-363](../../architecture/ADR-363-Password-Reset-Bounded-Per-Account-And-Bound-To-It.md)):

| `outcome` | Meaning |
|---|---|
| `link_sent` | a reset link left |
| `notice_sent` | the account signs in with a provider and has no password: it was told so, with no link |
| `send_failed` | the e-mail did not leave (SMTP) |
| `throttled` | the account's own e-mail budget was spent (`PASSWORD_RESET_ACCOUNT_INTERVAL_SECONDS`, `PASSWORD_RESET_ACCOUNT_DAILY_MAX`) |
| `unknown_account` | no account has that address |
| `refused_deleted` | the account was deleted (its address is kept for billing) |
| `refused_superuser` | an administrator account: never reset by e-mail |

The label never names an account: a burst aimed at ONE account reads as `throttled`.
The per-IP limiter still stands in front of the route (`ip_rate_limit_exceeded` in the
log); the per-account budget is what holds when the source rotates its addresses.

**Labels**:
- `severity`: warning
- `component`: auth
- `tier`: core

---

## 🔍 Symptoms

- Dashboard 09, row « Account security »: the requests panel shows `throttled` or
  `refused_superuser` growing.
- The person who owns the account may have received a few reset e-mails (never more than
  its budget), or none at all if it is an administrator.

---

## 🎯 Possible Causes

### A script aims the route at a known address
The 2026-10-23 incident: rotating addresses across several countries, an administrator's
address taken from the public commit history, accounts created first to learn the flow.

### A person clicks the button again and again
A few `throttled` refusals — the threshold exists so that this stays below it.

### An administrator forgot their password
On a self-hosted instance the first account is an administrator WITH a password (the
installer creates it). Its « Forgot password? » counts `refused_superuser` and sends
nothing, by design: an administrator is never recovered by e-mail. The server's operator
sets a new password inside the API container —
`python -m scripts.data.set_password --email <address>` (asked twice, hidden) — which
also signs the account out of every device.

---

## 🔧 Diagnosis

1. What the requests did:
   ```promql
   sum by (outcome) (increase(password_reset_requests_total[1h]))
   ```
2. Which account: in Loki (`container="lia-api-prod"`), the `password_reset_throttled` and
   `password_reset_refused` events carry the account id, never its address.
3. From where: the `ip_rate_limit_exceeded` events and the request lines carry the client
   address and its geolocation; forged or replayed links show as `rejected_token` on
   `password_reset_confirmations_total`.

---

## 🛠️ Resolution

- Nothing to repair on the account: no link left past its budget, an administrator was
  sent nothing, and a link is single-use and bound to the password it was issued for.
- If the instance runs no bot check yet, turn on Cloudflare Turnstile ([ADR-364](../../architecture/ADR-364-Turnstile-Bot-Check-On-The-Password-Doors.md),
  `docs/guides/GUIDE_SELF_HOSTING.md` § 4.6): a script that never runs a browser is then
  refused at the reset door, whatever addresses it rotates through.
- If it persists, block the source at the edge (a Cloudflare rule on the route's path
  meets a rotating source better than an address block).
- Tighten the budget if needed (`PASSWORD_RESET_ACCOUNT_*` in the instance `.env`), then
  recreate the API so it reads them — a plain `restart` keeps the old environment:
  `docker compose -f docker-compose.prod.yml up -d --force-recreate api` (with the
  instance's own file list).
- For the targeted person: a second factor (a passkey or an authenticator app) makes a
  password alone insufficient anyway.

---

## ✅ Verification

The two outcomes stop growing; the alert resolves within an hour of the last refusal
(the length of its window).
