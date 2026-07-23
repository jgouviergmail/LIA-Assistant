# Security & Account Program — Master Plan & Tracker (D1/D2/D3/D5)

**Status**: ✅ **PROGRAM COMPLETE** (2026-07-23) — all 7 lots delivered (ADR-143/144/145/146). Final evidence: backend 11 073+ tests / MyPy strict clean, frontend 2 511 tests / all ratchets hold (CC even lowered 57→56), e2e 44/44, migrations replay-checked to head `b9d5f7a32c84`, runtime proven per lot. REMAINING FOR THE USER: release surfaces (version bump + SW CACHE_VERSION bump together, CHANGELOG, FAQ changelog key, README), commit/push (never done by Claude), prod flag enablement (`MFA_ENABLED`, `ACCOUNT_EXPORT_ENABLED`) after release smoke, container rebuilds in prod (new deps: webauthn 2.8.0, pyotp 2.10.0, qrcode 8.2).
**Created**: 2026-07-23 · **Last updated**: 2026-07-23 (arbitrations decided, Lot 0 started)
**Owner process**: one lot at a time — per-lot TDD plan (`docs/superpowers/plans/`) → implementation → gates → deep self-review → runtime proof (Docker dev) → release surfaces.
**Continuity**: every implementation session MUST (1) read this document first, (2) work only on the active lot, (3) update the Status Tracker and Session Log at the end of the session.
**Mandate**: inline only (no subagents), strict TDD, maximum unit coverage backend + frontend, no git actions without explicit consent.

---

## 1. Program goal

Four user-facing account features on a publicly exposed instance (Cloudflare tunnel, personal data: mails, calendar, health, psychological memory, telephony):

- **D1** — Strong authentication: WebAuthn passkeys (primary) + TOTP fallback + backup codes + step-up re-authentication.
- **D2** — "My devices": list and revoke active BFF sessions.
- **D3** — Full GDPR-portability export (absorbs A9), mirroring the ADR-067 per-table purge map.
- **D5** — Offline PWA: app shell caching + branded offline page.

## 2. Verified facts this program relies on (do NOT re-derive)

Established by exhaustive source inspection + cross-verification on 2026-07-23. Re-verify only if the cited file changed since.

| # | Fact | Evidence |
|---|---|---|
| F1 | Login methods today = password + Google OAuth only. No WebAuthn/TOTP/2FA anywhere (backend, frontend, deps). The "OTP" hit in `ChannelSettings.tsx` is the Telegram linking code, not TOTP. | `domains/auth/router.py` (full read); greps `webauthn|passkey|totp|2fa` = 0 in `apps/api/src`, `apps/web/src` (1 false hit), `requirements.txt`, `package.json` |
| F2 | BFF sessions: Redis `session:{uuid}` storing ONLY `{user_id, remember_me, created_at}`; `last_accessed_at` was **deliberately removed** for PII minimization. HTTP-only cookie `lia_session`. | `infrastructure/cache/session_store.py:21-91` |
| F3 | A per-user session index `user:{user_id}:sessions` (Redis SET) already exists → D2 listing is O(1). | `session_store.py:157-175` |
| F4 | `SessionStore.refresh_session` is **dead code** (zero call sites). Sessions have a FIXED TTL (7d / 30d remember-me). The 410 `/auth/refresh` endpoint and several docstrings claim "sessions auto-refresh on each request" — doc-contradiction bug (systemic rule). Consequence: the index-TTL edge case is only latent; removing the dead code closes it. | grep `refresh_session(` = definition only; `auth/router.py:209-284` |
| F5 | `UserService._invalidate_all_user_sessions` duplicates invalidation with an O(N) SCAN over all sessions and a stale docstring proposing the index that `SessionStore.delete_all_user_sessions` already implements. `AccountDeletionService` uses the SCAN variant. | `users/service.py:1104-1144`; `account_deletion_service.py:322-341` |
| F6 | `/auth/logout-all` exists but kills ALL sessions including the current one; no session list endpoint, no single-session revocation endpoint anywhere. | `auth/router.py:330-368` |
| F7 | SSE streams authenticate once at connect (`get_current_active_session`); no session re-check during streaming; `sse_keepalive.py` has no session awareness. Revoking a session today does NOT cut its live SSE stream. | `agents/api/router.py:323-326,1109-1111`; grep in `sse_keepalive.py` |
| F8 | Per-IP sliding-window rate limiting on auth endpoints exists (factory `create_auth_rate_limiter`, Redis, fail-open). No per-account lockout. | `auth/dependencies.py:47-152` |
| F9 | "Revealed once" token pattern exists and is exactly imitable: `HealthMetricToken` = SHA-256 hash persisted, `token_prefix` for UI, `label`, `last_used_at`, `revoked_at`. | `health_metrics/models.py:114-169` |
| F10 | Fernet encryption utilities (`encrypt_data`/`decrypt_data`) exist and are the convention for secrets at rest (connectors, telephony, MCP, llm_config). | `core/security/utils.py:216-237`; 12 call-site files |
| F11 | No step-up / re-auth mechanism exists (connector "reauth" = OAuth reconnect, different concept). No `MFA_ENABLED` flag. No authenticated change-password endpoint (reset via email token only). Account deletion + GDPR erase are **admin-only** (`/users/admin/...`). No change-email endpoint. | greps; `users/router.py` endpoint census; `auth/router.py` |
| F12 | `hashed_password` is nullable — OAuth-only users have NO password. | `users/models.py:64-66` |
| F13 | ADR-067 purge map (`AccountDeletionService._purge_user_data_tables`) covers ~22 tables + LangGraph store/checkpoints + files, preserves billing tables. **Purge gaps confirmed**: `open_loops` and `phone_calls` are user-scoped but absent from the purge; their `ondelete=CASCADE` never fires because the user row is soft-deleted. Same defect class as audited N-207.1. | `account_deletion_service.py:560-641`; `__tablename__` census; `open_loops/models.py:56` |
| F14 | No account export of any kind exists (A9 unimplemented). Only consumption CSV exports exist (`/usage/export/*`, StreamingResponse, user-scoped) — a reusable precedent for download endpoints, not for archive jobs. | `google_api/user_export_router.py` |
| F15 | Keyset (cursor) pagination exists on conversation messages (`before_created_at`). | `conversations/repository.py:308-369` |
| F16 | Scheduler pattern: APScheduler jobs registered in `startup/schedulers.py::init_scheduler` behind leader election; durable user-triggered work uses a DB table + interval executor + `FOR UPDATE SKIP LOCKED` (scheduled_actions). APScheduler jobstore is in-memory → one-shot `run_date` jobs do not survive restarts. | `startup/schedulers.py:71-230`; `scheduled_actions/repository.py` |
| F17 | FCM push infra is complete (`FCMNotificationService.send_to_user`, token registry, `fcm_enabled` flag). | `notifications/service.py` |
| F18 | The ONLY service worker is `firebase-messaging-sw.js`, push-only (no `fetch`/`install`/`activate` handlers), registered at **scope `/`** — and ONLY inside the FCM-token flow (users who never enable notifications have NO SW at all). | `public/firebase-messaging-sw.js`; `lib/firebase.ts:169-171` |
| F19 | PWA foundation is fresh and guarded: 6 localized manifests + structural-parity test + layout metadata `manifest: /manifest-{lng}.json` + share_target route. `version.ts` exposes `APP_VERSION` from package.json. | `__tests__/pwa-manifests.test.ts`; `lib/version.ts`; `app/[lng]/share/page.tsx` |
| F20 | CSP: app policy has `worker-src 'self' blob:` (SW-compatible); CSP is per-document and test-pinned (ADR-098) — any directive change must update `csp.ts` + its test together. COOP/COEP headers active (Sherpa WASM). | `lib/csp.ts:112,118`; `next.config.ts:114-180` |
| F21 | API base URL: same-origin `/api/v1` when `NEXT_PUBLIC_API_URL` empty, absolute otherwise; prod = two sibling subdomains (`lia.` / `lia-back.` of one registrable domain) → same-site cookies work; WebAuthn RP ID must be configurable (frontend host or registrable domain). Dev = `localhost` (WebAuthn-allowed secure context). | `lib/api-client.ts:58-77`; `.env.prod.example:190,201` |
| F22 | Settings UI: tabs `preferences` / `features` / `administration` in `app/[lng]/dashboard/settings/page.tsx`, flat section components in `components/settings/`, hooks `useApiQuery`/`useApiMutation`, i18n ×6 with strict parity hook. | settings page read; `apps/web/CLAUDE.md` |
| F23 | Router wiring pattern for flag-gated domains: conditional import + `include_router` in `api/v1/routes.py` (`open_loops_enabled`, `telephony_enabled`). Flags live in `.env.example` (+`.env.prod.example`, `.env.min.prod`). | `routes.py:55-111`; `.env.example:1227,1326,1391` |
| F24 | Chat already shows an offline status pill (QW-12) — in-app awareness exists; the gap is cold-start/navigation offline (browser error page). | `dashboard/chat/page.tsx:739-752` |
| F25 | Sensitive-data map for export: encrypted at rest = home/last-known location, connector credentials, telephony `callee_phone` + `return_webhook_encrypted`, MCP auth; journals/memories/conversations are plaintext in DB (encryption socle is NO-GO, separate program). Telephony transcripts are purged after synthesis (only synthesis persists). | `telephony/models.py:63-142`; encrypt_data call sites; project memory |
| F26 | The frontend HARD-REDIRECTS to `/login` (`window.location.href`) on ANY 401 for non-public routes; the public-route allowlist is guarded by a filesystem completeness test. A step-up challenge must therefore NOT be a plain 401. | `lib/api-client.ts:114-182` |
| F27 | CSP `img-src` already includes `data:` in both policies → TOTP QR as data-URI needs NO CSP change. | `lib/csp.ts:110,237` |
| F28 | `iter_with_keepalive` is a generic, session-agnostic wrapper yielding `KeepalivePulse` sentinels; the router-level streaming loop consumes them. The shared SSE helper (`stream_run_as_sse`) serves all stream surfaces incl. ADR-117 reattach → single insertion point for a per-tick session re-check. | `agents/api/sse_keepalive.py` (full read); `agents/api/router.py:141` |
| F29 | `Pillow>=11.0.0` already pinned → `qrcode[pil]` needs no transitive addition. | `requirements.txt:128` |

## 3. Hypothesis verdicts (false positives / false negatives caught)

### Validated as stated
- D1: current auth = password + Google OAuth; Fernet convention; `hm_` revealed-once pattern; Redis sliding-window infra; BFF no-secret-client invariant; no MFA flag; migrations needed (F1, F8–F11).
- D2: sessions exist with zero user visibility/control; no list/revoke endpoints (F2, F6).
- D3: no export exists; purge map is the right starting inventory; keyset reusable; FCM for "ready" notification (F13–F17).
- D5: only the Firebase SW exists; no offline fallback; version.ts available for cache invalidation (F18, F19).

### Corrected (would have been false positives in the spec)
1. **D1 step-up target list**: "suppression de compte" and "changement d'email" are NOT user-facing endpoints (admin-only / nonexistent — F11). Step-up applies to what exists or is created by this program: MFA management (enroll/revoke/disable), D2 revoke-all, D3 export. Account deletion/email change join the list only if/when those endpoints are created (out of scope).
2. **D2 metadata**: the spec assumes session metadata exists to display; it does not — `last_accessed_at` was deliberately REMOVED for PII minimization (F2). D2 must consciously reverse a documented decision (arbitration A3), not just "expose" data.
3. **D2 "logout others"**: `/auth/logout-all` exists but is logout-ALL-including-current (F6); a new "all others" semantic + per-session revocation are required.
4. **D3 "job APScheduler"**: a one-shot APScheduler job does not survive restarts (in-memory jobstore, leader-gated — F16). The durable house pattern is a DB-backed job table + interval executor + `FOR UPDATE SKIP LOCKED` (arbitration A6, recommended).
5. **D5 "coexistence with distinct scopes"**: impossible as stated — the Firebase SW already owns scope `/` (F18). Either one unified SW (recommended) or a scope migration. Additionally, SW registration currently only happens when notifications are enabled; D5 requires unconditional registration at app boot.
6. **D1 "mot de passe conservé en fallback"**: OAuth-only users have no password at all (F12) — every method-availability decision must handle {password, oauth, both} × {passkey, totp}.

### False negatives caught (defects the spec's guards would have inherited)
1. **Purge gaps**: `open_loops` and `phone_calls` leak through account deletion TODAY (F13). A D3 completeness guard anchored on the purge list would have blessed the gap. Fix: guard anchored on the **model registry** (all tables with FK → `users.id`), classifying every table as purged+exported / purged+excluded(reason) / billing-retained(reason) — catches both purge and export gaps, including future tables (ADR-085 pattern).
2. **Doc-contradiction on session refresh** (F4): D2's "expires" display would have shipped a false claim. Fix in Lot 0 (delete dead code, correct docs).
3. **Duplicated session invalidation** (F5): D2 built next to the SCAN variant would entrench divergence. Consolidate in Lot 0.
4. **Live SSE survives revocation** (F7): the spec requires cutting SSE on revoke; without a mechanism this would be a silent false promise. Designed in Lot 4 (keepalive-tick session check).
5. **Legacy session payloads**: adding fields to the Redis session dict must not 401 existing sessions at deploy — `from_dict` needs defaults for every new field (round-trip test, systemic rule).

## 4. Lots (dependency-ordered)

Flags: `MFA_ENABLED` (Lots 1–3 routers), `ACCOUNT_EXPORT_ENABLED` (Lot 5), D2 rides on auth router (no flag needed beyond dark-launch via UI), D5 is frontend-only (dev no-op guard). All default **false** in prod until smoke-tested.

### Lot 0 — Corrective bedrock (no new feature, closes inherited defects)
1. Add `open_loops` + `phone_calls` purge statements to `_purge_user_data_tables` (+ counts, + tests).
2. Introduce `src/domains/users/user_data_map.py`: single registry classifying **every table in SQLAlchemy metadata** — user-data-purged+exported / user-data-purged+excluded(reason) / billing-retained(reason) / global-non-user — NOT just tables with a direct FK → `users.id` (that criterion would miss `conversation_messages`, which has no `user_id` and is purged via subquery). Plus a `users`-columns map (scrubbed / exported / retained) closing the `journal_portrait` defect class for future columns. CI completeness guard fails on any unclassified table or column (future-proof; reused by Lot 5).
3. Delete dead `SessionStore.refresh_session`; fix the `/auth/refresh` 410 payload + docstrings claiming auto-refresh (fixed TTL is the documented truth).
4. Replace `UserService._invalidate_all_user_sessions` SCAN with delegation to `SessionStore.delete_all_user_sessions` (single implementation, stale docstring gone).
Gates: `task lint`, `task test:backend:unit:fast`; deletion-service tests extended.

### Lot 1 — D1a: WebAuthn passkeys (register, login, manage)
- Deps: `webauthn` (py_webauthn) pinned in `requirements.txt` + `task deps:lock`.
- Table `webauthn_credentials` (UUIDMixin/TimestampMixin, FK CASCADE, `credential_id` unique, `public_key`, `sign_count`, `transports`, `aaguid`, `label`, `last_used_at`) — imitates F9 naming.
- Settings module `core/config/mfa.py` (added to Settings MRO): `mfa_enabled`, `webauthn_rp_id` (default derived from `frontend_url` host), `webauthn_rp_name`, `webauthn_expected_origin` (default `frontend_url`), challenge TTL. `.env.example` ×3 updated.
- Endpoints (new `domains/auth/mfa/` module, flag-gated router): register options/verify (authenticated), credential list/rename/delete, authenticate options/verify (anonymous; discoverable credentials + conditional UI). Challenges in Redis (`webauthn_challenge:{id}`, TTL 5 min, single-use). Session creation reuses `create_authenticated_session_with_cookie`; `sign_count` regression ⇒ reject + WARN (clone detection).
- Session payload v2: `auth_methods`, `auth_time` (backward-compatible defaults in `from_dict`; round-trip test).
- Frontend: `useWebAuthn` hook (`@github/webauthn-json` or native `navigator.credentials` — no secret storage), login page button + conditional UI, Security section skeleton in settings (`SecuritySettings.tsx`), i18n ×6, a11y (dialogs, focus, names).
- Rate limits: per-IP (existing factory) + per-user sliding window on verify endpoints. Metrics `webauthn_ceremonies_total{ceremony,status}`. Structured logs, no PII at INFO.
- E2E: Playwright Chromium virtual authenticator (hermetic) — enroll, login, revoke.

### Lot 2 — D1b: TOTP + backup codes
- Deps: `pyotp`, `qrcode` (backend QR PNG data-URI; Pillow already present).
- Tables: `user_totp` (one per user: `secret_encrypted` Fernet, `confirmed_at`, `last_used_step` for replay rejection), `mfa_backup_codes` (SHA-256 hash, `used_at`; 10 per generation, regeneration invalidates prior set — revealed once, F9 pattern).
- Flow: enroll (secret + QR shown once) → confirm (code) → active; login: password OK + MFA active ⇒ no cookie, Redis `mfa_pending:{token}` (TTL 5 min, single-use) ⇒ `/auth/mfa/verify` (TOTP or backup code) ⇒ session. ±1 step tolerance, strict per-user rate limit.
- Frontend: enrollment dialog (QR + manual secret + confirm), backup codes display/download once, login second-step screen. i18n ×6, a11y.

### Lot 3 — D1c: Step-up re-authentication
- Session payload: `step_up_at`; dependency `require_recent_step_up` (window from settings, default 5 min — parameterizable rule); `/auth/step-up` verify endpoints (password | passkey | TOTP — whichever the account has). Challenge contract: **HTTP 403 + `error_code: "step_up_required"`** (ADR-124-consistent) — NEVER a plain 401, which the api-client hard-redirects to `/login` (F26). Frontend: typed `ApiStepUpError` surfaced by `handleResponse`'s 403 branch + a `useStepUpGuard` wrapper that opens the re-auth dialog and replays the original call.
- Applied to: MFA management (enroll/revoke/disable, backup regeneration), password disabling, Lot 4 revoke-others, Lot 5 export request. (NOT applied to admin-only endpoints — F11.)
- Password disabling ("désactivable explicitement — jamais silencieusement"): allowed only with ≥ 2 active passkeys; blocked for the last strong method; OAuth-only users unaffected (nothing to disable).

### Lot 4 — D2: Devices / active sessions
- Session payload v3 at creation: `ua_family`/`os_family` (tiny in-house parser, ~6 families, "Unknown" fallback — no new dep), `ip_trunc` (IPv4 /24, IPv6 /48 — never full IP stored or logged), `last_seen_at` coarse-updated (≥ 15 min between writes). Legacy sessions display as "Unknown device (created …)".
- Endpoints: `GET /auth/sessions` (index + MGET pipeline, current-session badge), `DELETE /auth/sessions/{id}` (ownership check), `POST /auth/sessions/revoke-others` (step-up; new `SessionStore.delete_other_user_sessions`).
- SSE cut: session existence re-checked on `KeepalivePulse` handling inside the shared `stream_run_as_sse` helper (F28 — single insertion point covering all SSE surfaces incl. ADR-117 reattach; `iter_with_keepalive` stays pure/session-agnostic); stream closes ≤ 1 keepalive interval after revocation with a terminal SSE event. UI copy documents that detached background runs (ADR-117) continue server-side by design.
- `last_seen_at` coarse updates MUST preserve the remaining TTL (`SET ... KEEPTTL`), never reset it.
- New-login notification per revised A4: passkey logins silent (device-bound); password/OAuth logins suppressed only when the client presents a valid active FCM token owned by the account (password: request body; OAuth: attached to the Redis `state` at initiate); otherwise fire-and-forget FCM to all active tokens. Attested sessions carry `fcm_token_id` in the session payload → device list shows the FCM `device_name`. User-preference gated (default ON).
- Frontend: `DeviceSessionsSettings.tsx` in Security section, `useSessions` hook, confirm dialogs, i18n ×6, a11y. Metrics `session_revocations_total{scope}`.

### Lot 5 — D3: Full account export
- Table `account_export_jobs` (status enum pending/running/done/failed/expired, `scope` JSONB, `file_path`, `file_size_bytes`, `error_code`, timestamps, `expires_at`, `download_count`; partial unique index: one non-terminal job per user).
- Executor: interval job (60 s, leader-elected, flag-gated) consuming via `FOR UPDATE SKIP LOCKED` + atomic status transition; global concurrency 1 (RPi5); crash ⇒ stale-running requeue after timeout; ZIP built via `asyncio.to_thread` into temp file then atomic rename under `{exports_storage_path}/{user_id}/`; retention sweep purges expired files+rows.
- Exporters registered in `user_data_map.py` (Lot 0) — one per domain, JSON (stable schemas) + Markdown rendering; conversations support period scope (created_at range; keyset iteration). Encrypted fields exported decrypted via their owning services (F25). Exclusion list (tested, byte-level assertion on the archive): connector credentials, MCP credentials, token hashes (hm_, backup codes), FCM tokens, telephony webhooks, `hashed_password`, WebAuthn key material.
- Completeness: Lot 0 guard extended — every purged personal table is exported or excluded-with-reason; CI fails otherwise.
- API: request (step-up, scope payload), status, authenticated download (ownership + expiry + FileResponse), cancel. FCM "export ready". Audit: counters + structlog (never content). Metrics `account_export_jobs_total{status}`, duration histogram.
- Frontend: `AccountExportSettings.tsx` (scope pickers, job status, download), i18n ×6, a11y.

### Lot 6 — D5: Offline PWA (independent — can run any time)
- Single unified SW: extend `public/firebase-messaging-sw.js` (keeps existing registrations; push handlers untouched) with `install`/`activate`/`fetch`: precache `offline.html` + core icons; runtime stale-while-revalidate for same-origin static assets (`/_next/static`, icons, fonts); navigation requests network-first with `offline.html` fallback; **never** cache non-GET, `/api/*`, the `NEXT_PUBLIC_API_URL` origin, or SSE.
- Registration moves to app boot (layout effect, prod-only; FCM flow reuses the registration — idempotent). Cache name versioned `lia-shell-v{version}` injected at build from package.json (prebuild script); `activate` deletes stale caches. `Cache-Control: no-cache` header for the SW file in `next.config.ts`.
- `offline.html`: self-contained (inline CSS + inline logo), 6 languages inline selected from the i18next cookie / `navigator.language`, retry button. (Static file outside the React tree — i18n parity hook does not apply; parity asserted by a dedicated unit test on the file content.)
- Edge cases: share_target GET navigation falls back like any navigation; COEP/CORP preserved on cached responses; dev container unaffected (registration skipped in development).
- E2E: Playwright `context.setOffline(true)` — offline navigation shows branded page; recovery on reconnect; push regression check (SW still handles push).

### Cross-cutting (every lot)
16-point runtime integration checklist (config MRO, constants, model registration ×3, migration single-head, router wiring, lifespan, scheduler, i18n ×6 parity, observability, exceptions via raisers, deps:lock, docs). Systemic rules enforced by existing AST/CI guards (UTC datetimes, JSONB new-dict, no empty except, file-size ratchet ≤ 600 SLOC per module, i18n via central mechanisms). ADRs: one per feature (next free numbers after ADR-142; check index at write time). Gates per impact: `task lint`, `task test:backend:unit:fast`, `task test:frontend`, clean `tsc --noEmit --incremental false`, ratchets, `task db:migrate:replay-check` for migration lots, hermetic Playwright for changed journeys. Runtime proof in Docker dev before any "done".

## 5. Arbitrations — ALL DECIDED 2026-07-23 (user accepted every recommendation)

| ID | Question | Recommendation |
|---|---|---|
| A1 | Passkey login UX: identifier-first vs discoverable credentials + conditional UI (autofill) | Conditional UI + explicit button (best UX, py_webauthn supports it) |
| A2 | TOTP QR: backend PNG data-URI vs frontend QR lib | Backend (zero new frontend dep, uniform secret path) |
| A3 | Reopen PII-minimization for session metadata (UA family, truncated IP, coarse last-seen in Redis) | Yes, scoped: families + /24-truncated IP + ≥15-min-granularity last-seen; documented in the ADR as a conscious reversal |
| A4 | New-login notification: which sessions count as "known device"? | REVISED after user challenge (2026-07-23): `user_fcm_tokens` IS a de facto device registry (device_type/device_name/is_active — models.py:30-80, already listed in NotificationSettings UI). Attestation design: passkey login = known by definition (device-bound); password login (XHR) and OAuth (token attached to the OAuth `state` in Redis) present the client's FCM token — valid+active+account-owned ⇒ known, no notification; absent/invalid/rotated ⇒ notify all active tokens (fail-safe toward notifying). Attested sessions store `fcm_token_id` ⇒ D2 list shows the real `device_name`. Push-disabled devices are always "unknown" (documented in UI — incentive to enable push). Default ON, opt-out. FCM list (who receives push) ≠ D2 sessions (who has access): both kept, cross-referenced. |
| A5 | D3 archive scope for binary files: include `attachments/` uploads? RAG originals? | Include attachments + RAG source documents; exclude derived chunks/vectors; size cap setting |
| A6 | D3 job mechanism | DB table + interval executor (F16) — survives restarts, resumable, idempotent |
| A7 | D5 SW strategy | Single unified SW (F18 makes two-SW impossible at scope `/` without migration) |
| A8 | Password disabling guard | Allowed only with ≥ 2 active passkeys; never the last strong method |

## 6. Status tracker

| Lot | Content | Status |
|---|---|---|
| 0 | Corrective bedrock (purge gaps, dead code, consolidation, data map + guard) | ✅ delivered 2026-07-23 |
| 1 | D1a Passkeys (A1: conditional UI + button, resident keys) | ✅ delivered 2026-07-23 (ADR-143) |
| 2 | D1b TOTP + backup codes (A2: backend QR data-URI) | ✅ delivered 2026-07-23 |
| 3 | D1c Step-up (403 + `step_up_required`) + password disabling (A8) | ✅ delivered 2026-07-23 |
| 4 | D2 Devices (A3: bounded PII; A4: FCM-token attestation) | ✅ delivered 2026-07-23 (ADR-144) |
| 5 | D3 Export (A5: attachments + RAG sources, 2 GiB cap; A6: table + executor) | ✅ delivered 2026-07-23 (ADR-145) — scope selection deferred (see completeness audit) |
| 6 | D5 Offline PWA (A7: unified SW) | ✅ delivered 2026-07-23 (ADR-146) — **PROGRAM COMPLETE** |

## 7. Session log

### Lot 1 delivery notes (2026-07-23)

**Delivered** (plan: `plans/2026-07-23-security-lot1-passkeys.md`, ADR-143 + ADR_INDEX entry):
backend = model+migration `e5a1c7d93b48` (replay-check green, F007/F042), `MFASettings` (+ leaked-env-comment fail-fast validator), session payload v2 (`auth_methods`, legacy-safe), `WebAuthnService`+repository+router (7 endpoints, flag-gated), per-user rate limiter factory, `GET /auth/features` capability probe, metrics `webauthn_ceremonies_total`; frontend = `lib/webauthn.ts` pure helpers, `useWebAuthn`/`usePasskeys`/`useAuthFeatures`, login passkey button + conditional UI (`autocomplete="username webauthn"`), `SecuritySettings` section (list/add/rename/revoke, both settings layouts), i18n ×6 (script-injected, parity by construction); e2e = CDP virtual-authenticator ceremony spec + public-login invariant widened to "only /auth/features".
**Evidence**: backend fast suite **11 006 passed / 0 failed**, lint Black/Ruff/MyPy(956 files) clean; frontend **2 482 passed / 251 files**, `tsc --incremental false` exit 0, a11y ratchet 0, hooks 34 holds, CC 57 holds, coverage 63.11%; e2e **44/44** (Chromium, hermetic); runtime = dev image rebuilt from lockfile, `alembic current = e5a1c7d93b48 (head)`, `/auth/features` → `{"mfa_enabled":true}`, live ceremony options served with derived rpId.
**Real bug found & fixed en route**: docker compose passes `KEY=   # comment` as the VALUE when the value is empty → the dev rpId became the comment string. Fix: no inline comments on empty-valued vars in both `.env.example`s + `MFASettings` boot-fail validator + 4 tests (`test_mfa_settings.py`).
**Deferred to Lot 3** (documented): step-up on credential delete/rename.
**Ops note**: dev stack now runs with `MFA_ENABLED=true` in the local `.env`; prod examples stay `false`.

### Lot 2 delivery notes (2026-07-23)

**Delivered** (plan: `plans/2026-07-23-security-lot2-totp.md`; ADR-143 updated): backend = `pyotp==2.10.0`/`qrcode==8.2` locked, `user_totp` + `mfa_backup_codes` (migration `f7b2d8e14a59`, replay-check green, user_data_map + purge guard-driven), `TOTPService` (enroll draft→confirm, explicit matched-timestep anti-replay, backup codes revealed-once, single-use Redis pending tokens) + repository + router (5 management endpoints + anonymous `/auth/mfa/verify` at 5/min per IP), two-state `/auth/login` (`LoginResponseBFF`), `mfa_pending` metric label, `totp_verifications_total`; frontend = `useTotp`, `TotpSettings` (QR dialog, backup codes revealed-once with copy, disable/regenerate confirms), `LoginForm` MFA step (single-use token → back-to-credentials on failure), `auth.tsx` `login→LoginResult` + `verifyMfa`, i18n ×6 (~40 keys, script-injected). **En-route ratchet fix**: `auth/router.py` blew its frozen SLOC cap (+19) → COEP avatar proxy extracted to `profile_image_router.py` (cohesive module, wired unconditionally). TDD caught a real bug: regenerate didn't invalidate the prior code set.
**Evidence**: backend **11 027 passed / 0 failed** + lint clean; frontend **2 492 passed / 253 files**, tsc clean, a11y/hooks/CC ratchets hold; e2e **44/44** (first pass had 2 cold-compile flakes on the restarted dev container; clean re-run 44/44 in 3.2 m); runtime = image rebuilt from lockfile, `alembic current = f7b2d8e14a59 (head)`, `/auth/features` live.

### Lot 3 delivery notes (2026-07-23) — D1 COMPLETE

**Delivered** (ADR-143 finalized): session payload v3 (`step_up_at`, `mark_step_up` with keepttl), `require_recent_step_up` dependency (typed 403, `BaseAPIException.detail` widened to `str | dict`), `/auth/step-up/*` router mounted unconditionally (password | TOTP | allow-listed passkey ceremony + status endpoint), step-up applied to 9 sensitive endpoints, **password disabling A8** (`/auth/password/disable`, ≥ 2 passkeys + fresh step-up; last-passkey guard in `delete_credential`); frontend = `ApiStepUpError` + extracted `handleForbidden`/`handleUnauthorized` (CC ratchet SHRANK 57→56), `useStepUpGuard` (park + single replay), `StepUpDialog` (3 methods), guard wired into SecuritySettings/TotpSettings/PasswordSettings (new A8 UI block), i18n ×6.
**Evidence**: backend **11 042 passed / 0 failed**, MyPy strict clean (961 files); frontend **2 500 passed / 255 files**, tsc clean, ratchets hold (CC lowered); e2e **44/44** (warm re-run; first pass = known cold-compile flakes); runtime = step-up route mounted (401-not-404 without session), containers restarted healthy.
**TDD catch**: the new last-passkey guard correctly broke the old delete happy-path test (passwordless fixture) — fixed by making the fixture explicit + 2 new guard tests.

### Lot 4 delivery notes (2026-07-23) — D2 COMPLETE

**Delivered** (ADR-144, plan `plans/2026-07-23-security-lot4-devices.md`): session payload **v4** (bounded A3 metadata via `core/client_metadata.py` chokepoint + `fcm_token_id`, legacy-safe), opaque `display_id` (sha256[:16] — raw session id never leaves the server), `SessionStore` fleet ops (`list_user_sessions`, `delete_session_by_display_id`, `delete_other_user_sessions`, coarse `touch_last_seen` keepttl wired into `get_current_session`), `/auth/sessions` router (list + revoke + step-up-guarded revoke-others, `session_revocations_total`), **SSE cut** at every keepalive tick (`session_watch.py` fail-open; broker relay + reattach + both legacy inline loops; `: session-revoked` comment), **A4 attestation** (`login_notification.py`: valid active FCM token ⇒ known ⇒ silent + real device name in the list; passkey known by definition; OAuth always notifies; outcome carried in the two-step pending payload), `users.login_notifications_enabled` (migration `a8c4e6f21b73`, default TRUE, PATCH preference endpoint, localized push ×6); frontend `useSessions` + `DeviceSessionsSettings` rendered OUTSIDE the MFA gate (design review catch: device hygiene must not vanish when MFA is off), i18n ×6.
**Evidence**: backend **11 068 passed / 0 failed** + MyPy strict clean (965 files) + replay-check green; frontend **2 505 passed / 256 files**, tsc clean, all ratchets hold; e2e **44/44** (warm pass); runtime = migration at head `a8c4e6f21b73`, `/auth/sessions` mounted (401-not-404).

### Lot 5 delivery notes (2026-07-23) — D3 COMPLETE

**Delivered** (ADR-145): `domains/account_export/` bounded context — durable `account_export_jobs` (migration `b9d5f7a32c84`, partial-unique active-per-user), metadata-driven `builder.py` (FULL-policy tables only ⇒ EXCLUDED secrets unexportable BY CONSTRUCTION; per-column redaction + Fernet decryption specs; dual-format JSON+Markdown; A5 files ZIP_STORED; 2 GiB cap; atomic rename), `executor.py` (SKIP LOCKED claim, crashed-run detection, retention sweep, FCM "export ready" ×6), flag-gated router (step-up request / latest / ownership-scoped download with counter), scheduler job registered behind the flag, `AccountExportSettings` config module + `.env` section [83], `test_export_completeness.py` guard (FULL-scopeability + exclusion assertions + column-verified specs — it caught 2 invented column names during development); frontend `AccountExportSettings` (step-up guarded, status badge, download, self-hiding on 404), i18n ×6.
**Evidence**: backend **11 073 passed / 0 failed**, MyPy strict clean (971 files), replay-check green; frontend **2 505 passed / 256 files**, tsc clean, ratchets hold; e2e **44/44** (warm pass); runtime = head `b9d5f7a32c84`, `/account/export/latest` mounted (401-not-404), dev runs with `ACCOUNT_EXPORT_ENABLED=true`.

### Staged-code review (2026-07-23, full inline pass over the 131 staged files)

No blocking defect. 12 findings; 7 fixed on the spot, 5 tracked:

**Fixed** — (1) recurring unjustified local imports hiding real graph edges (no cycle existed): hoisted in `auth/router.py` (login), `totp_router.py`, `login_notification.py`, `session_watch.py`, `session_dependencies.py` (`require_recent_step_up`), `builder._row_to_dict` (per-row import overhead), `executor._notify_ready`; patch targets in tests re-aimed accordingly. (2) `user_id/job_id: object` typing dodges → `uuid.UUID` (3 sites). (3) `request_export` race loser: concurrent create hit the partial unique index as a raw 500 → `IntegrityError` now mapped to the same 400 (+ `test_export_router.py`, 2 tests). (4) `_render_markdown` column names unguarded (a rename would silently empty the readable rendering) → pinned in `test_export_completeness.py`. (5) `_copy_user_files` followed symlinks (could embed content from outside the user dir) → excluded. (6) `AccountExportSettings` missing from config `__all__`/MRO docstring. (7) stale "ADR pending" docstring in `auth/models.py`.

**Tracked, not fixed** — (a) builder materializes all tables in RAM before writing (ADR-145 Deferred, same work as period scoping); (b) `touch_last_seen` re-GETs the session already loaded by `get_current_session` (1 redundant Redis GET per authenticated request); (c) `/auth/features` has no rate limit (static, no I/O — accepted); (d) narrow race deleting the last 2 passkeys of a password-less account concurrently (recoverable via email reset); (e) cap-hit at `verify_registration` emits no failure metric.

- 2026-07-23 — Program created: full hypothesis verification (25 facts, 6 corrections, 5 false negatives caught), lots + arbitrations defined. No code.
- 2026-07-23 — Adversarial self-review pass (user challenge): 5 residual assumptions verified → F26–F29 added; 2 design corrections applied (step-up challenge = 403+code, NOT 401 — the api-client hard-redirects 401s to /login; completeness guard = total metadata classification + users-columns map, NOT FK-census which missed `conversation_messages`); SSE-cut insertion point pinned to `stream_run_as_sse` KeepalivePulse handling; KEEPTTL edge noted. Still no code.
- 2026-07-23 — A4 revised after user challenge: `user_fcm_tokens` acknowledged as a de facto device registry (my "no device registry" claim was too absolute — it exists, limited to push-enabled devices). New attestation design: passkey=known, FCM-token-at-login=known (fail-safe toward notifying), `fcm_token_id` in session payload enriches the D2 device list with real device names. Still no code.
### Completeness audit (2026-07-23, post-"program complete" challenge)

A fresh spec-vs-delivered sweep found **3 gaps**; 2 fixed on the spot, 1 documented as a tracked remainder:

1. **A4 attestation was one-legged (FIXED)** — the backend accepted `fcm_token` at login but the frontend never sent it, so every login notified (fail-safe, but the "known device stays silent" promise was dead code). `lib/auth.tsx` `login()` now resolves the FCM token silently when push permission is already `granted` (dynamic import, try/catch toward notifying) and sends `fcm_token` in the body; the pinned login-contract test now asserts the field.
2. **`login_notifications_enabled` had no UI (FIXED)** — the preference existed (column + PATCH endpoint + push suppression) but nothing exposed it. `UserBase` now serializes it, and `DeviceSessionsSettings` gained a Switch (persist → `refreshUser`, error toast; 2 behavioral tests), i18n `notify_title`/`notify_description` ×6.
3. **D3 scope selection NOT implemented (DOCUMENTED, deferred)** — `account_export_jobs.scope` is a reserved NULL column: no scope payload on the request, builder always full-account, no frontend pickers, and `export_too_large` has no self-service mitigation. The spec's "scope pickers / period scope" lines above were plan, not delivery. Recorded in ADR-145 ("Deferred (tracked)"), the column comment, and the config description (the false "scope hint" wording removed).

Cross-cutting docs also aligned: `ARCHITECTURE.md` (security section: 4-capability table + flags), `GETTING_STARTED.md` (flag table + post-smoke footnote), `docs/INDEX.md` (ADR counts 145/ADR-146).

### UX review fixes (2026-07-23, user field report)

The user's first hands-on pass found two defects; root-causing them surfaced two more. All four fixed and runtime-proven in the browser (real account, dev stack):

1. **Security sections broke the settings design** — the three components rendered bare `<section>` blocks instead of the `SettingsSection` accordion card every other section uses. All three now wrap in `SettingsSection` (collapsible cards: `security-auth` "Authentification forte" / `security-devices` / `security-export`, icon tiles, title+description in the trigger, `collapsible={false}` escape hatch for tests, new `settings.security.auth.*` keys ×6). `AccountExportSettings` blew the frontend CC ratchet in the process (17 > 15) → decomposed (`ExportJobStatus` extracted); ratchet holds at 56.
2. **Step-up dialog was a dead end for OAuth-only accounts** — an account with no password and no enrolled factor got `methods=[]`: a "Confirmez que c'est bien vous" dialog with only Cancel, deadlocking first-factor enrollment AND export (chicken-and-egg). Two-part fix: (a) `create_session` now stamps `step_up_at` at creation — a fresh full authentication IS the sudo window (GitHub-style; right after signing in, no dialog at all); (b) `step_up_status` advertises `oauth_{provider}` for identity-provider accounts and the dialog renders a "Confirmer avec Google" button (full re-sign-in → fresh stamped session) plus an explanatory empty-state instead of a bare Cancel.
3. **Wrong password in the dialog ejected the user to /login** — the step-up verification endpoints answer 401 on a bad password/code, and the api-client's global 401 handler hard-redirects every 401. Found live (a mistyped password destroyed the whole settings flow). Fix: `isCredentialCheckUrl` exempts `/auth/step-up/*` from the eject (inline error instead), pinned by `api-client.step-up-401.test.ts`.
4. Runtime proof (browser, throwaway account `test-securite-ui@example.dev`, deleted after): accordion design matches sibling sections; fresh login → "Activer" TOTP opens the QR dialog DIRECTLY (no step-up prompt — sudo window); full enrollment completed (real pyotp code, backup codes revealed once, badge "Activé"); devices list + A4 toggle rendered; export queued ("En attente" + toast). API-level: `login:200 → step-up/password:200 → totp/enroll:200` inside the window.

### Passkey-enrollment field failure (2026-07-23, root-caused — environment, not code)

The user's passkey enrollment failed on the dev stack. API logs showed `register/options` 200 (twice) with NO `register/verify` behind — the failure was client-side. Reproduced in a driven browser; exact console error: **`NotAllowedError: WebAuthn is not supported on sites with TLS certificate errors.`** Chromium hard-refuses WebAuthn on any origin with an untrusted certificate (the interstitial click-through does not help); the dev stack serves a self-signed cert for `$SSL_DOMAIN`. The e2e passkey spec never hit this because Playwright trusts the cert (`ignoreHTTPSErrors`-class context), which Chrome's WebAuthn gate exempts.

Fix = trust the dev cert once: extracted `cert.pem` from the `lia_ssl_certs` volume → `certutil -f -user -addstore Root` → **browser restart required** (cert verdicts cache for the browser's lifetime; the first retry after import still failed until Chrome was relaunched). Proof after restart: full ceremony end-to-end — `navigator.credentials.create()` opened the native prompt, `register/verify` **201**, `webauthn_credential_registered`, credential listed in the UI with rename/revoke actions. No code change; procedure documented in `GETTING_STARTED.md` ("WebAuthn / Passkeys in Development"). The cert was imported into the current user's Windows root store on this machine (revert: `certutil -user -delstore Root "<SSL_DOMAIN>"`); already-open browsers must be restarted to see it.

**Industrialization (same day, user request):**

- **Dev**: new `task dev:trust-cert` (extracts the cert via a bind-mount — no host mkdir — then `certutil` on Windows, instructions elsewhere; re-run after ssl-init regenerates, ~30 days). Ran green end-to-end.
- **Prod (RPi)**: verified — NOTHING to do. `FRONTEND_URL=https://lia.jeyswork.com` behind the Cloudflare tunnel serves a valid public certificate (`ssl_verify_result:0` on both domains, no `-k`); rpId/origin derive from `FRONTEND_URL`; MFA code not yet deployed there (flags false until post-release smoke). Activation checklist added to GUIDE_DEPLOYMENT ("WebAuthn / Passkeys en production").
- **Third occurrence of the empty-value-inline-comment class found en route**: `DOCKER_HOST=   # comment` in `.env`/.env.example — Task's `dotenv:` passed the comment as the value, poisoning every task-launched docker command (`tcp://127.0.0.1:2375`). New CI guard `test_env_example_inline_comment_guard.py` scans all `.env` examples for the class; it immediately caught **33 more** pre-existing offenders (19 `.env.example` + 14 `.env.prod.example`), all fixed (+10 in the local `.env`), api+web recreated with the cleaned env.
- Docs aligned: GETTING_STARTED (task-based procedure + 3 traps + troubleshooting cross-ref), GUIDE_DEPLOYMENT (prod activation checklist), ADR-143 (operational note).

### Export download 404 (2026-07-23, user field report — FIXED)

"Télécharger l'archive" proposed a `download.txt` and failed ("site non disponible"). API logs: `latest` 200s, executor green, but **no `GET …/download` ever reached the API** — the link's href was `/api/v1/account/export/{id}/download`, **relative to the FRONTEND origin** (`:3000`), which has no such route; the `download` attribute on the dead link produced the `download.txt` name. Fix: new exported helper `apiEndpointUrl(endpoint)` in `api-client` (same base resolution as the client) and the component now renders an **absolute API href** — a top-level navigation that streams the archive to disk (never a blob: archives can reach 2 GiB; the session cookie rides along on same-site top-level GETs, both in dev — same host, different port — and in prod — host-only cookie on the API subdomain). The `download` attribute was dropped: `Content-Disposition: attachment; filename="lia-account-export.zip"` names the file. Pinned by a test that stubs `NEXT_PUBLIC_API_URL` and asserts the API origin in the href. Runtime proof (throwaway account, deleted after + orphan export dirs swept): request → build (executor) → UI click → `account_export_downloaded` + **200**, valid ZIP (32 entries, profile.json + data/*.json + readable/*.md) landed with the right name.

- 2026-07-23 — **Lot 0 DELIVERED** (plan: `plans/2026-07-23-security-lot0-bedrock.md`). (1) Purge extended to `open_loops` + `phone_calls`; two lying count keys fixed (`broadcast_read_receipts`→`user_broadcast_reads`, `channels`→`user_channel_bindings` — caught by the new name↔table self-consistency test). (2) `user_data_map.py`: total classification (47 tables, 75 users columns) + 10-test CI guard + scrub oracle parametrized from the map. (3) Dead `refresh_session` deleted, all 5 false "auto-refresh" claims corrected (incl. the pinned 410 contract test). (4) `_invalidate_all_user_sessions` delegates to the indexed `SessionStore` (SCAN duplicate gone); GDPR-flow tests re-mocked at the store boundary. **Architecture bonus**: `build_purge_statements` is metadata-driven (Table objects, not ORM imports) — the F009 cycles ratchet SHRANK 31→25 (6 users↔domain cycles broken, zero added). Gates: `task lint:backend` clean (Black/Ruff/MyPy 950 files), `task test:backend:unit:fast` **10 978 passed / 0 failed / 32 skipped**, runtime proof: `lia-api-dev` restarted, `/health` = healthy (redis+database).
