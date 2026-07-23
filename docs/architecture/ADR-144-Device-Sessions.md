# ADR-144: Device Sessions — "My Devices" Visibility & Revocation (D2)

**Status**: ✅ IMPLEMENTED (2026-07-23)
**Date**: 2026-07-23
**Deciders**: jgouvier + Claude (security program, arbitrations A3/A4 decided 2026-07-23; A4 revised after user challenge)
**Technical Story**: `docs/superpowers/specs/2026-07-23-security-account-program.md` — BFF Redis sessions existed with zero user visibility or control (facts F2/F6/F7).

---

## Context and Problem Statement

Sessions were server-side Redis blobs (`{user_id, remember_me, created_at}`) with `last_accessed_at` deliberately removed in 2024 for PII minimization. The user had no way to see which devices hold a session or to revoke one remotely; `/auth/logout-all` killed everything including the current session; live SSE streams survived revocation (authenticated once at connect).

## Decision

- **Bounded PII reversal (A3)** — session payload **v4** adds ONLY: browser/OS **families** (~6 each, in-house parser — never the raw UA), **truncated IP** (IPv4 /24 → `a.b.c.x`, IPv6 first 3 hextets), `last_seen_at` at ≥ 15 min grain (`keepttl` rewrites), and `fcm_token_id` (attestation). Single extraction chokepoint `core/client_metadata.py`. Data lives and dies with the session (TTL ≤ 30 d, purged with the account); legacy payloads default to "unknown device".
- **Opaque display ids** — rows are addressed by `sha256(session_id)[:16]`; the raw session id (= the cookie secret) NEVER reaches the client.
- **Endpoints** (`/auth/sessions`, mounted unconditionally): list (current-session badge, attested device names), `DELETE /{display_id}` (plain auth — a thief revoking devices only helps the victim), `POST /revoke-others` (**step-up required**, keeps the caller's session). Metrics `session_revocations_total{scope}`.
- **SSE cut** — `session_watch.session_still_valid` (single Redis GET, fail-open) checked at every keepalive tick of the shared broker relay `stream_run_as_sse` (incl. ADR-117 reattach) AND both legacy inline loops; a revoked subscriber closes with the `: session-revoked` transport comment within one tick. Detached producers continue by design (stated in the UI copy).
- **New-login notification (A4, revised)** — `user_fcm_tokens` IS the de facto device registry. Attestation: a login presenting a **valid active FCM token of the account** proves device possession (a stolen password alone cannot suppress the alert) ⇒ known, no notification, `fcm_token_id` stored (UI shows the real device name). Passkey logins = known by definition (device-bound). OAuth callback = always notify (a GET redirect cannot carry the token safely — documented deviation). Two-step logins carry the attestation outcome inside the Redis pending payload. Preference `users.login_notifications_enabled` (default TRUE — security-first), localized push (backend i18n ×6, zh-CN canonical), best-effort (`login_notifications_total{status}`).

## Consequences

- Migration `a8c4e6f21b73` (preference column); USER_COLUMNS classification enforced by the Lot 0 guard.
- Coarse `touch_last_seen` wired into `get_current_session` (best-effort, suppressed) — bounded write load by construction.
- Frontend: `DeviceSessionsSettings` rendered OUTSIDE the MFA gate (device hygiene is flag-independent), step-up-guarded revoke-others, i18n ×6.
- Rejected: persistent device registry (cookie device-id + table) — new durable-PII surface for marginal gain over FCM attestation; sliding session expiration (fixed TTL remains the documented truth since Lot 0).
