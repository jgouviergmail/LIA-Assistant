# ADR-363 — A password reset is bounded per account, bound to the account, and never a door for a federated or administrator account

**Status**: accepted — 2026-10-23 (owner request after an automated attack on the
production instance's authentication: « A. un plafond silencieux par compte… B. aucun
lien pour un compte sans mot de passe ni pour un super-admin… C. un jeton lié à
l'empreinte du mot de passe… D. une métrique et une alerte… », then « oui » to keeping
the passkey escape hatch)
**Amends**: ADR-143 (arbitration A8: the e-mail reset stays the way back for an account
that disabled its password for passkeys — and only for an account that may hold one),
ADR-260 (one more `USER_RUNTIME` family), ADR-119 (two core alerts)

## Context

Everything below was read on production on 2026-10-23, read-only, or measured in the
code the same day.

1. **The reset e-mail was a harassment channel.** `POST /auth/request-password-reset` was
   bounded per client IP only. From rotating addresses across several countries, a script
   sent the administrator's account four reset e-mails in an afternoon; nothing bounded
   what ONE account could receive.
2. **A reset link could CREATE a password.** The flow sent a link to any account an
   address named, and `reset_password` wrote the new hash whatever the account held
   before. Of the instance's 230 accounts, 199 sign in with Google and have no password,
   and the administrator is one of them: a link used on such an account opens a second
   door — password sign-in — outside the provider's protection.
3. **A deleted account still received links.** Deletion keeps the address (billing) and
   clears the password; the lookup found the row and a link left to a person who had
   left.
4. **A link outlived what it was issued for.** The token carried the address alone: a
   reset finished on one link left every other link of the hour valid, and an account
   deleted then re-created at the same address inherited the departed account's links.
   The attacker played the whole flow on throwaway accounts first (five completed
   resets), then submitted forged and replayed tokens — every one refused by the
   signature, the type or the single-use check.
5. **Nothing told anyone.** About twenty-eight accounts were created that day, the
   requests were refused by the per-IP limiter eighteen times, and no alert existed for
   either; the owner learned of it from the e-mails.
6. **The rate-limit metrics named who they throttled.** `extract_key_prefix` removed
   purely numeric segments only: of the 56 `key_prefix` series, 27 carried a client IP
   and 25 an account id — a label that grows with every visitor, and identifiers in
   Prometheus. A limiter keyed by account would have added one series per account.
7. **The passkey escape hatch is documented.** `POST /auth/step-up/password/disable`
   (arbitration A8) lets an account with two passkeys drop its password and states that
   the e-mail reset remains its way back; no account uses it today, the promise stands.
8. **Registration already reveals an account.** `raise_email_already_exists` answers a
   sign-up for a known address, so the reset route's response time (an e-mail is sent
   synchronously for an existing account) teaches nothing registration does not.
9. **The settings promised the reset to everyone without a password.** The Security
   page's password block read « Email password-reset remains available as the recovery
   path » to every account whose password is off — the Google accounts and the
   administrator included — and so did the dialog that turns a password off.

## Decision

1. **Who may receive a link is ONE decision, applied when the link is asked for AND when
   it is used** (`domains/auth/password_reset_policy.decide_reset`):

   | Account (first row that applies) | Request | Use of a link |
   |---|---|---|
   | deleted | nothing | refused |
   | administrator (`is_superuser`) | nothing | refused |
   | signs in with a provider, no password (A8 included) | a NOTICE (« you sign in with Google ») | refused |
   | a password, or passkeys only and no provider (A8) | a link | allowed |

   The notice carries no token; an administrator receives no e-mail at all, so the
   harassment of the most exposed mailbox ends, and the attempt is ALERTED instead. The
   provider's name comes from `SIGN_IN_PROVIDER_LABELS`, held equal to every literal the
   code writes into `users.oauth_provider` by a unit test.

   The same rule is what the Security settings state as the way back:
   `recovery_without_password` reads it for the account without its password, and
   `GET /auth/step-up/status` publishes the answer (`password_recovery`: `email_link`,
   `provider` or `none`, with `sign_in_provider`). The password block says it beside a
   password already off and in the dialog that turns one off — the provider the account
   signs in with, nothing for an administrator without one, otherwise the link. The two
   fields stay out of the chat's security read (`available_methods` already names the
   provider; the review is recorded in `assert_security_projection_coverage`).
2. **An account's e-mail budget, whatever IP asks** (`acquire_reset_send`): one e-mail per
   interval and a few per rolling day (`PASSWORD_RESET_ACCOUNT_INTERVAL_SECONDS`,
   `PASSWORD_RESET_ACCOUNT_DAILY_MAX`; defaults in `core/constants.py`). The short window
   is asked FIRST, so a refused attempt never reaches the day's count — the day counts
   e-mails admitted, and hammering the route cannot spend a victim's day. The notice
   spends the same budget. The limiter is the existing `RedisRateLimiter` (atomic, an
   attempt recorded only when admitted, open when Redis is unreachable — its own
   doctrine, with the per-IP limiter still in front). The key family
   `auth:password_reset_account` is `USER_RUNTIME`: a conversation reset that freed it
   would hand a fresh budget to whoever is hammering. The answer never changes.
3. **A link is bound to its account and to that account's password**
   (`create_password_reset_token` / `reset_token_matches_account`): the token carries the
   account id and an HMAC of the stored hash under the instance secret — never the hash,
   since a JWT is readable by whoever holds it. The use checks both against the account
   found by the address, at constant time: a password changed since (by this reset or any
   other) or an account re-created at the address retires the link. A token minted before
   this decision carries neither claim and is refused; such a link is at most an hour old
   when the change ships. In development, where the single-use JTI check does not run,
   the binding makes a used link stale all the same.
4. **What the route did is counted, never who it was done to**
   (`infrastructure/observability/metrics_auth.py`): `password_reset_requests_total{outcome}`
   (`link_sent`, `notice_sent`, `send_failed`, `throttled`, `unknown_account`,
   `refused_deleted`, `refused_superuser`) and `password_reset_confirmations_total{outcome}`
   (`completed`, `rejected_token`, `stale_token`, `unknown_account`, `ineligible`). Every
   outcome's series exists at zero from the start, so `increase()` sees the opening
   request of a burst and a panel reads a healthy 0, not « No data ». Dashboard 09 draws
   them beside the sign-ups (password and Google).
5. **Two core alerts** (`alerts-core.yml`, `core_auth`): `PasswordResetAbuse` — refusals at
   an account's budget past `ALERT_CORE_PASSWORD_RESET_THROTTLED_PER_HOUR` in an hour, or
   ONE request naming an administrator; `RegistrationBurst` — password and Google
   sign-ups together past `ALERT_CORE_REGISTRATIONS_PER_HOUR` in an hour. Both `round()`
   the `increase()`, whose edge extrapolation would read two events as 2.02. Each has its
   runbook, its promtool cases and its ADR-266 evidence recipe.
6. **A rate-limit metric label names no client** (`extract_key_prefix`): account ids
   (anywhere in the key) and the trailing client address (IPv4, or IPv6 across the
   key's own separators) are dropped with the numeric segments; the bounded words stay.
   No panel or rule reads a specific `key_prefix` value, so every reader keeps working
   on bounded series.

## Consequences

- The administrator's mailbox receives no reset e-mail whatever is sent at the route; an
  operator is told within minutes instead.
- A person who signs in with Google and forgets it is answered with how they sign in, not
  with a password they never had — and the Security settings no longer promise them, or
  an administrator, an e-mail reset the route would not send.
- A person clicking twice gets one e-mail; the forgot-password page says the last e-mail
  stays valid, without naming a number the code owns. The FAQ (privacy, question 21)
  says the same in six languages.
- The dead `rate_limit_forgot_password` dependency is gone.
- No migration and no new route; the reset routes answer as before, and the step-up
  status gains two fields (`password_recovery`, `sign_in_provider`).

## Stated limits

- **An administrator recovers a password from the server, never from the application.**
  No authenticated change-password route exists (security programme, finding F11) and the
  e-mail reset is refused to administrators. The production instance's administrator has
  no password, but every self-hosted instance's FIRST account has one: the installer
  creates it with a password (`scripts/data/create_admin`, which never resets an existing
  one). Its operator sets a new one with `scripts/data/set_password` (amendment below).
- **A provider account's only door is its provider.** An instance that stops offering
  Google sign-in leaves its Google accounts without a way in — by design: the link that
  used to create a password was a second door.
- **An attacker can spend an account's daily budget.** Those e-mails reach the account's
  own mailbox, where each link is usable for its hour; a later legitimate request may wait
  for the rolling day.
- **A failed send still spends the budget**: the attempt is what an attacker controls, the
  SMTP outcome is not.
- **Redis unreachable means no per-account budget** — the e-mail leaves; `RedisDown`
  alerts on the outage itself.
- **The response time still differs** between an existing and an unknown address
  (context 8: registration reveals the same fact by design).
- **Addresses are matched exactly**, as before: a local part typed in another case names
  no account.

## Rejected

- **A CAPTCHA on sign-up and reset** — a product choice the owner did not retain here;
  superseded the next day by [ADR-364](ADR-364-Turnstile-Bot-Check-On-The-Password-Doors.md)
  (a Cloudflare Turnstile check on sign-up, sign-in and reset requests).
- **A notice for administrators** — it would keep the harassment channel open; the alert
  says the same to the person who can act.
- **Removing the passkey escape hatch** — it would lock out a person who lost both
  passkeys (owner answer, 2026-10-23).
- **Telling forged from replayed tokens on the counter** — the exception keeps no
  structural reason, and reading its message is forbidden; the replay keeps its own log
  event (`password_reset_token_reused`).
- **A background e-mail dispatcher to equalise response times** — a new ownership
  pattern for a fact registration already gives away.

## Implementation references

- `apps/api/src/domains/auth/password_reset_policy.py` — decision, budget, outcomes,
  `recovery_without_password`
- `apps/api/src/domains/auth/step_up_router.py` (`step_up_status`),
  `apps/api/src/domains/auth/security_queries.py` (the reviewed projection set),
  `apps/web/src/components/settings/PasswordSettings.tsx` (four keys in six languages)
- `apps/api/src/domains/auth/service.py` — `_serve_password_reset_request`, `reset_password`,
  `_send_password_reset_notice`
- `apps/api/src/core/security/utils.py` — `password_fingerprint`, `reset_token_matches_account`
- `apps/api/src/infrastructure/email/email_service.py` — `send_password_reset_notice`
  (five msgids in the six gettext catalogs)
- `apps/api/src/infrastructure/observability/metrics_auth.py`,
  `apps/api/src/infrastructure/observability/metrics_redis.py`
- `infrastructure/observability/prometheus/alerts-core.yml.template` (`core_auth`),
  `thresholds/*.env`, `tests/alerts_core_test.yml`
- `docs/runbooks/alerts/PasswordResetAbuse.md`, `docs/runbooks/alerts/RegistrationBurst.md`
- Tests: `tests/unit/domains/auth/test_password_reset_policy.py`,
  `tests/unit/domains/auth/test_password_reset_flow.py`,
  `tests/unit/domains/auth/test_step_up.py`,
  `tests/unit/core/security/test_password_reset_token.py`,
  `tests/unit/infrastructure/observability/test_metrics_redis.py`,
  `tests/integration/test_password_reset_budget_redis.py` (the budget on the real Lua
  limiter), `apps/web/src/components/settings/__tests__/PasswordSettings.test.tsx`

## Amendment 2026-10-24 — an operator command sets a password from the server

Owner decision (« A »), after the review found that decision 1 left every self-hosted
instance's first administrator — created WITH a password by the installer — with no way
back from a forgotten password.

- `python -m scripts.data.set_password --email <address>`, inside the API container
  (`task db:set-password` on the development stack). Whoever can run it already holds the
  server; the administrator's mailbox still receives nothing, so decision 1 stands.
- The secret never travels through argv (piped stdin, or typed twice at a hidden prompt);
  the backend policy is the single authority; an unknown address and a deleted account
  change nothing.
- The new hash is COMMITTED, THEN the account is signed out of every device — the reverse
  order would leave a stolen session alive on a password that never changed. Every reset
  link issued earlier stops working by construction (decision 3).
- No `admin_audit_log` row: its `admin_user_id` is a NOT NULL reference to an account and
  the operator is none (the account-deletion precedent); the structured WARNING
  `account_password_set_from_server` records the act, by account id.
- A provider account may receive a password this way — the operator's explicit act — and
  the command says so.
- Tests: `tests/integration/test_set_password_db.py` (real PostgreSQL),
  `tests/unit/scripts/test_set_password_cli.py` (secret input, commit-then-revoke order,
  failures).
