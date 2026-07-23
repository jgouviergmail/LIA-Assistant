# ADR-143: Strong Authentication — WebAuthn Passkeys, TOTP, Step-Up (D1)

**Status**: ✅ IMPLEMENTED (2026-07-23) — Lot 1 (passkeys), Lot 2 (TOTP + two-step login), Lot 3 (step-up + password disabling) all delivered; `MFA_ENABLED=false` in prod until release smoke
**Date**: 2026-07-23
**Deciders**: jgouvier + Claude (security program, 8 arbitrations decided 2026-07-23)
**Technical Story**: `docs/superpowers/specs/2026-07-23-security-account-program.md` (facts F1–F29, arbitrations A1–A8). The instance is publicly exposed (Cloudflare tunnel) and holds mail, calendar, health, psychological memory and telephony data behind password + Google OAuth only.

---

## Context and Problem Statement

Authentication was password + Google OAuth over the BFF session pattern (HTTP-only `lia_session` cookie, Redis-backed, fixed 7/30-day TTL). No second factor, no phishing-resistant method, no re-authentication for sensitive actions, no per-account brute-force budget (only per-IP). For a single-admin, publicly reachable instance, credential theft = full personal-data compromise.

## Decision Drivers

1. **Maximum security AND maximum comfort** — passkeys give both (Face ID/fingerprint one-tap, phishing-resistant, device-bound).
2. **BFF invariant untouched** — no secret ever client-side; sessions stay server-side Redis + HTTP-only cookie.
3. **Zero-regression rollout** — `MFA_ENABLED=false` default; routers unmounted when off; legacy Redis session payloads keep validating.
4. **House patterns, not new machinery** — `hm_` revealed-once token conventions, Fernet for reversible secrets, Redis sliding-window rate limiting, centralized error raisers, versioned prompts/i18n rules.

## Decision (Lot 1 — implemented)

- **Library**: `py_webauthn 2.8.0` (pinned; 3.x requires cryptography ≥ 49, repo pins 48.0.1 for CVE posture — revisit at the next crypto bump).
- **Model**: `webauthn_credentials` — base64url `credential_id` (unique) + COSE `public_key`, BigInteger `sign_count`, `transports` JSONB, `aaguid`, `device_type`, `backed_up`, user-supplied `label`, `last_used_at`. Classified `USER_PURGED`/`EXCLUDED` in `user_data_map` (Lot 0 guard enforces purge + export-exclusion).
- **Ceremonies** (A1): discoverable credentials — enrollment requires `resident_key=REQUIRED` + `user_verification=REQUIRED`; login sends no `allowCredentials` (zero account enumeration) and the frontend arms **conditional UI** (passkey autofill via `autocomplete="username webauthn"`) plus an explicit button.
- **Challenges**: single-use in Redis (`webauthn:reg:{user_id}`, `webauthn:auth:{challenge_id}`), TTL `WEBAUTHN_CHALLENGE_TTL_SECONDS` (300 s), consumed with GETDEL.
- **Session payload v2**: `auth_methods` tags (`password`, `oauth_google`, `passkey`) written at session creation; `from_dict` defaults keep pre-v2 sessions valid (round-trip tested). Foundation for Lot 3 step-up and D2 device display.
- **Sign-count policy**: py_webauthn rejects counter regressions (clone signal) → generic 401 + WARN log + failure metric; `new_sign_count` persisted on success; 0→0 accepted (synced passkeys).
- **Rate limiting**: anonymous ceremony endpoints per-IP (existing factory); enrollment/management per-user (`create_user_rate_limiter`, key `auth:{action}:user:{id}`) so IP rotation cannot reset a targeted account's budget.
- **Capability probe**: public `GET /auth/features` (always mounted) exposes `mfa_enabled` so the frontend gates passkey UI without probing unmounted routers. The login page's hermetic-E2E invariant becomes "no API call except the capability probe".
- **RP config**: `WEBAUTHN_RP_ID` / `WEBAUTHN_EXPECTED_ORIGIN` empty-default to the `FRONTEND_URL` host/origin (dev `localhost`, prod frontend subdomain — F21).
- **Errors**: anonymous path collapses every failure to generic 401 (`raise_invalid_credentials`, no enumeration); enrollment path uses 400 `raise_invalid_input`. Metrics `webauthn_ceremonies_total{ceremony,status}`.

## Lot 2 — TOTP (implemented 2026-07-23)

`pyotp==2.10.0` + backend-generated QR data-URI (`qrcode==8.2`, rendered via `asyncio.to_thread`); secret Fernet-encrypted in `user_totp` with `last_used_step` — the matched timestep is resolved explicitly and must strictly increase, so an accepted code (or an older one) can never replay; 10 SHA-256-hashed single-use backup codes in `mfa_backup_codes`, revealed once, regeneration invalidates the prior set. Login is two-state (`LoginResponseBFF`): password OK + TOTP active → no cookie, single-use Redis `mfa:pending:{token}` (TTL `MFA_PENDING_TTL_SECONDS`, GETDEL) → `POST /auth/mfa/verify` (strict per-IP limit) creates the session with `auth_methods=["password","totp"]`. Passkey login stays single-step (device-bound strong factor); Google OAuth stays single-step (the IdP carries its own MFA). A failed second step consumes the pending token — the client returns to the credential form (no code-guessing loop on one token). Migration `f7b2d8e14a59`; both new tables classified USER_PURGED/EXCLUDED + explicit purge entries. En-route ratchet extraction: the Google-avatar COEP proxy moved out of `auth/router.py` into `profile_image_router.py` (file-size cap, shrink-only).

## Lot 3 — Step-up + password disabling (implemented 2026-07-23)

Session payload **v3** adds `step_up_at` (legacy-safe defaults, round-trip tested); `SessionStore.mark_step_up` rewrites with `keepttl` so a step-up never extends the fixed session lifetime. Dependency `require_recent_step_up` guards 9 sensitive endpoints (passkey register/rename/revoke, TOTP enroll/confirm/disable/regenerate, password disabling) with the typed challenge **403 + `detail.error = "step_up_required"`** — NEVER a plain 401, which the api-client hard-redirects to `/login` (F26); `BaseAPIException.detail` was widened to `str | dict` for typed contracts. Verification endpoints under `/auth/step-up/*` (mounted UNCONDITIONALLY — password re-verify must work when MFA is off): password (generic 401 on mismatch), TOTP/backup code (delegates to the anti-replay verifier), and an allow-listed passkey ceremony (`webauthn:stepup:{user_id}` single-use challenge, ownership enforced). `GET /auth/step-up/status` reports the account's methods + freshness horizon for the UI. **Password disabling (A8)**: `POST /auth/password/disable` requires a fresh step-up AND ≥ 2 active passkeys; `delete_credential` refuses the last passkey of a password-less account; email reset remains the documented recovery path (stated in the UI copy). Frontend: `ApiStepUpError` raised by the api-client's 403 branch (extracted `handleForbidden`/`handleUnauthorized` helpers — frontend CC ratchet shrank 57→56), `useStepUpGuard` parks the failed action and replays it once after the `StepUpDialog` (passkey one-tap / password / TOTP, methods from the status endpoint) reports success.

## Step-up amendments (2026-07-23, post-field-report)

- **A fresh full authentication opens the sudo window**: `create_session` stamps `step_up_at` at creation (GitHub-style sudo mode). Rationale: right after signing in, the user just gave the strongest proof the account supports; and without it, an OAuth-only account (no password, no enrolled factor) could NEVER satisfy a step-up challenge — first-factor enrollment and export deadlocked (found live).
- **Identity-provider re-sign-in is a step-up method**: `step_up_status` advertises `oauth_{provider}` when the account has one; the `StepUpDialog` offers "Confirmer avec Google" (full re-sign-in → fresh stamped session; the parked action is retried by the user after the redirect). The dialog also explains itself when no method exists instead of showing a bare Cancel.
- **Step-up verification 401s never eject to /login**: the api-client exempts `/auth/step-up/*` from the global 401 redirect (`isCredentialCheckUrl`) — a mistyped password shows the inline error and lets the user retry, it does not destroy the flow. Pinned by `api-client.step-up-401.test.ts`.

## Operational note — trusted TLS certificate is a WebAuthn precondition

Chromium refuses every WebAuthn ceremony on an origin with an untrusted certificate (`NotAllowedError: WebAuthn is not supported on sites with TLS certificate errors.`), interstitial click-through included. **Dev** (self-signed): run `task dev:trust-cert` then fully restart the browser (verdicts cache for the process lifetime) — documented in GETTING_STARTED. **Prod**: nothing to do — Cloudflare serves valid certificates and rpId/origin derive from `FRONTEND_URL` (activation checklist in GUIDE_DEPLOYMENT). Related guard: `test_env_example_inline_comment_guard.py` closes the empty-value-inline-comment class that once poisoned the dev rpId (and later `DOCKER_HOST` through Task's dotenv).

## Considered Options

- **webauthn 3.0.0** — rejected for now: forces cryptography ≥ 49 (repo-wide bump out of this program's scope).
- **Identifier-first login** — rejected (A1): extra friction + account-enumeration surface vs. discoverable credentials.
- **Frontend QR library for TOTP** — rejected (A2): backend data-URI needs zero new JS deps and keeps one secret path.
- **JWT-based pending-MFA state** — rejected: Redis single-use tokens match the BFF architecture (nothing self-validating client-side).

## Consequences

- New table + migration (`e5a1c7d93b48`), replay-check green (F007/F042 structural equivalence).
- `MFASettings` module in the Settings MRO; 6 new env vars documented ×2 example files.
- The e2e suite gains a Chromium CDP virtual-authenticator ceremony proof (hermetic, mocked API).
- Follow-ups tracked in the program doc: D2 sessions UI reuses `auth_methods` + FCM attestation (A4); D3 export requires Lot 3 step-up.
