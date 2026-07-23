# Security Program — Lot 2: TOTP + Backup Codes Implementation Plan

> **For agentic workers:** inline execution (no subagents). Master doc: `docs/superpowers/specs/2026-07-23-security-account-program.md` (A2: backend QR data-URI). Builds on Lot 1 (ADR-143).

**Goal:** TOTP as second factor for password login (enroll via QR shown once, confirm, disable) + 10 single-use backup codes (revealed once, `hm_` pattern). Passkey login stays single-step (device-bound strong factor); Google OAuth stays single-step (IdP carries its own MFA — documented in ADR-143).

**Design (locked):**
- Deps: `pyotp==2.10.0`, `qrcode==8.2` (+ existing Pillow).
- Tables (in `domains/auth/models.py`): `user_totp` (unique `user_id`, `secret_encrypted` Fernet TEXT, `confirmed_at` nullable, `last_used_step` BigInteger nullable — anti-replay of the same 30 s step) and `mfa_backup_codes` (`user_id`, `code_hash` SHA-256 String(64) unique, `used_at` nullable). Both USER_PURGED/EXCLUDED in user_data_map + purge entries (Lot 0 guard drives).
- Protocol invariants as constants: 6 digits, 30 s interval, ±1 step window, 10 codes of 10 hex chars. Settings: `mfa_pending_ttl_seconds` (300).
- Enrollment: `POST /auth/totp/enroll` (authenticated, user-rate-limited) → generates secret (`pyotp.random_base32()`), stores Fernet-encrypted UNCONFIRMED (replaces any prior unconfirmed; 400 if already confirmed), returns `{secret, otpauth_uri, qr_data_uri}` ONCE. `POST /auth/totp/confirm {code}` → verify (window ±1) → `confirmed_at`, generate + return the 10 backup codes ONCE (hashes stored). `DELETE /auth/totp` → drops totp + codes (step-up guard arrives in Lot 3). `GET /auth/totp/status` → `{active, confirmed_at, backup_codes_remaining}`. `POST /auth/totp/backup-codes/regenerate` → new set ONCE, old invalidated.
- Login two-step: `AuthService.login` returns the user; the ROUTER checks TOTP-active → no cookie; Redis `mfa:pending:{token}` = `{user_id, remember_me}` TTL 300 single-use (GETDEL); response `AuthResponseBFF`-shaped with `user=None, mfa_required=True, mfa_token`. `POST /auth/mfa/verify {mfa_token, code}` (IP-rate-limited) → TOTP (anti-replay `last_used_step`) OR backup code (`used_at` stamped) → session `auth_methods=["password","totp"]`.
- Metrics: reuse `webauthn_ceremonies_total`? No — add `totp_verifications_total{context=login|confirm, status}` in `metrics_mfa.py`.
- Frontend: SecuritySettings gains a TOTP block (status, enroll dialog: QR `<img src=data:...>` + secret copy + confirm code input; backup codes shown once with copy/download; disable confirm; regenerate). Login form: when `mfa_required` → code step (TOTP or backup code input) → `/auth/mfa/verify`. i18n ×6 (script), vitest component tests, e2e smoke (mocked API) for the two-step login UI.

## Tasks
### Task 1 — Models + migration + data-map + purge (guard-driven TDD)
### Task 2 — Constants + settings (`mfa_pending_ttl_seconds`) + .env ×2 (no inline comments on empty values!)
### Task 3 — `totp_service.py` TDD (enroll/confirm/verify/backup/disable/status; anti-replay; Fernet; QR data-URI)
### Task 4 — Router (`totp_router` under MFA flag) + login two-step + `/auth/mfa/verify` + schemas + metrics
### Task 5 — Frontend (SecuritySettings TOTP block, login second step, i18n ×6, vitest)
### Task 6 — Gates (lint, fast suite, replay-check, tsc, ratchets) + e2e smoke + runtime rebuild + ADR-143 status update + program doc
