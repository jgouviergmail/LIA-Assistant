# TurnstileUnavailable - Runbook

**Severity**: Warning
**Component**: Authentication (Cloudflare Turnstile bot check)
**Impact**: Sign-ups and password-reset requests are refused while Cloudflare does not answer; sign-ins proceed WITHOUT the bot check
**SLA Impact**: Partial — nobody can create an account or ask for a reset e-mail meanwhile

---

## 📊 Alert Definition

**Alert Name**: `TurnstileUnavailable` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression** (template form):
```promql
round(sum(increase(turnstile_verifications_total{outcome="unavailable"}[15m]))) > THRESHOLD
```

`for: 5m`. `THRESHOLD` is `ALERT_CORE_TURNSTILE_UNAVAILABLE_PER_15M`
(`infrastructure/observability/prometheus/thresholds/*.env`). `round()` absorbs the
edge extrapolation of `increase()`.

The password doors (sign-up, sign-in, reset request) carry the Turnstile widget's token
and the API asks Cloudflare's siteverify about it
([ADR-364](../../architecture/ADR-364-Turnstile-Bot-Check-On-The-Password-Doors.md)).
`turnstile_verifications_total{action, outcome}` counts what each check concluded:

| `outcome` | Meaning |
|---|---|
| `passed` | Cloudflare vouched for the token, made for this door on this instance's pages |
| `missing` | no token while Cloudflare answers the server — a script that never ran the widget, or a browser that blocks it |
| `rejected` | Cloudflare refused the token, or it was made for another door or site |
| `unavailable` | Cloudflare gave no usable answer — this alert |

When `unavailable`, the owner's rule applies (2026-10-24): **only the sign-in proceeds**.
A person must always reach their account; a new account and a reset e-mail can wait.
An outage usually reaches the browser too: the widget cannot load and the sign-in form
sends the request without a token. Such a sign-in is counted `unavailable` and proceeds
only while Cloudflare does not answer the server either (one shared check of Cloudflare
per worker at most once per `TURNSTILE_REACHABILITY_TTL_SECONDS`); when Cloudflare
answers the server, it is `missing`.

**Labels**:
- `severity`: warning
- `component`: auth
- `tier`: core

---

## 🔍 Symptoms

- Dashboard 09, row « Account security », panel « Bot check — Turnstile »: the
  `unavailable` series grows.
- On the sign-up and forgot-password pages, people see « The anti-robot check could not
  load » (the widget, when the outage reaches their browser) or « The anti-robot check is
  unavailable right now » (the API); their sign-ins go through.

---

## 🎯 Possible Causes

### Cloudflare's siteverify does not answer
An outage on Cloudflare's side, or the API host has lost its route to
`challenges.cloudflare.com` (DNS, outbound network). The API logs
`turnstile_siteverify_unanswered` (a timeout, a 5xx, Cloudflare's own `internal-error`).

### The instance's own secret or request is wrong
Cloudflare answered `invalid-input-secret`, `missing-input-secret` or `bad-request`:
the API logs `turnstile_siteverify_refused_the_server` at ERROR. A mistyped
`TURNSTILE_SECRET_KEY`, or a key rotated in the Cloudflare dashboard but not on the
server. These are read as « no usable answer » on purpose: read as « bad token », one
typo would refuse every sign-in.

### A testing key in production
Cloudflare's documented testing secret answers every dummy token, so in production
its answers are read as « no usable answer » too: the API logs
`turnstile_testing_key_in_production` at ERROR. Put the widget's real keys in
`TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY`.

---

## 🔧 Diagnosis

1. Which doors, since when:
   ```promql
   sum by (action, outcome) (increase(turnstile_verifications_total[15m]))
   ```
2. Which cause: in Loki (`container="lia-api-prod"`),
   `turnstile_siteverify_refused_the_server` (the secret),
   `turnstile_testing_key_in_production` (a testing key) or
   `turnstile_siteverify_unanswered` (the network or Cloudflare).
3. From the API container, the route to Cloudflare:
   `curl -sS -o /dev/null -w '%{http_code}\n' https://challenges.cloudflare.com/turnstile/v0/siteverify -d 'secret=x&response=x'`
   (an HTTP status means the route is fine; a timeout means it is not).

---

## 🛠️ Resolution

- **The secret**: copy it again from the Cloudflare dashboard (Turnstile → the widget →
  Settings) into `TURNSTILE_SECRET_KEY`, then recreate the API so it reads the new value
  — a plain `restart` keeps the environment the container was created with:
  ```bash
  docker compose -f docker-compose.prod.yml up -d --force-recreate api
  ```
  (with the same file list the instance starts with — a self-hosted install adds
  `-f docker-compose.install.yml`).
- **Cloudflare or the network**: nothing to repair on LIA's side — sign-ins keep working;
  the refusals end on their own when Cloudflare answers again.
- **To stop refusing sign-ups during a long outage**: set `TURNSTILE_ENABLED=false` and
  recreate the API the same way — the doors then run without the bot check (the per-IP
  limiters and the per-account reset budget still stand). Switch it back on afterwards.

---

## ✅ Verification

The `unavailable` series stops growing and `passed` resumes; the alert resolves within
15 minutes of the last unanswered check (the length of its window).
