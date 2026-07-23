# Security Program — Lot 1: WebAuthn Passkeys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline execution mandated — no subagents). Master doc: `docs/superpowers/specs/2026-07-23-security-account-program.md` (facts F1–F29, arbitrations A1/A8 decided).

**Goal:** Passkey enrollment (multiple, named), passkey login (conditional UI + explicit button, discoverable credentials), credential management (list/rename/revoke) — flag-gated by `MFA_ENABLED` (default false).

**Architecture:** New `webauthn_credentials` table + `WebAuthnService` orchestrating py_webauthn 2.8.0 ceremonies; challenges single-use in Redis (5 min TTL); sessions created through the existing BFF helper with a v2 payload carrying `auth_methods`. Frontend: `useWebAuthn` hook (no new JS dep — manual base64url helpers), login integration, Security settings section.

**Tech Stack:** py_webauthn 2.8.0 (pinned; 3.x needs cryptography>=49), FastAPI, SQLAlchemy 2.x, Redis, React 19 + `navigator.credentials`.

## Global Constraints

- `MFA_ENABLED=false` default everywhere; router wired conditionally (F23 pattern).
- BFF invariant: no secret client-side; session cookie via `create_authenticated_session_with_cookie` only.
- Legacy Redis sessions MUST keep validating (v2 fields defaulted in `from_dict`; round-trip test).
- New table ⇒ user_data_map classification (USER_PURGED + EXCLUDED "key material") + purge entry — the Lot 0 guard goes red until done (built-in TDD).
- All new thresholds in `core/constants.py` + Settings fields (`.env.example`, `.env.prod.example`).
- i18n ×6 strict parity; a11y (dialogs, names, focus); no PII at INFO (user ids + counters only).

## Verified API surface (introspected 2026-07-23, do not re-derive)

- `generate_registration_options(*, rp_id, rp_name, user_name, user_id: bytes|None, challenge: bytes|None, timeout, attestation, authenticator_selection: AuthenticatorSelectionCriteria|None, exclude_credentials: list[PublicKeyCredentialDescriptor]|None, ...) -> PublicKeyCredentialCreationOptions`
- `verify_registration_response(*, credential: str|dict, expected_challenge: bytes, expected_rp_id: str, expected_origin: str|list, require_user_verification: bool=False) -> VerifiedRegistration(credential_id: bytes, credential_public_key: bytes, sign_count: int, aaguid: str, credential_device_type, credential_backed_up, user_verified, fmt, ...)`
- `generate_authentication_options(*, rp_id, challenge=None, timeout, allow_credentials=None, user_verification=PREFERRED) -> PublicKeyCredentialRequestOptions`
- `verify_authentication_response(*, credential, expected_challenge, expected_rp_id, expected_origin, credential_public_key: bytes, credential_current_sign_count: int, require_user_verification=False) -> VerifiedAuthentication(credential_id, new_sign_count, credential_device_type, credential_backed_up, user_verified)`
- Helpers: `options_to_json(options) -> str`, `base64url_to_bytes(str) -> bytes`; structs: `AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED)`, `PublicKeyCredentialDescriptor(id: bytes)`.

## Design decisions (locked)

- **Storage**: `credential_id` and `public_key` stored as base64url TEXT (unique index on credential_id); `transports` JSONB list; `sign_count` BigInteger; `aaguid` String(36); `device_type` String(32); `backed_up` Boolean; `label` String(64) nullable; `last_used_at` nullable. Table follows the `health_metric_tokens` display conventions (F9).
- **Sign-count policy**: reject when stored > 0 and new <= stored (clone signal, WARN log + metric); accept new == 0 == stored (synced passkeys legitimately report 0); always persist `new_sign_count` on success.
- **Challenges**: Redis db session; keys `webauthn:reg:{user_id}` (enrollment, one pending per user) and `webauthn:auth:{challenge_id}` (anonymous login, `challenge_id = uuid4`), TTL `settings.webauthn_challenge_ttl_seconds` (default 300), consumed with GETDEL (single-use).
- **RP config**: `webauthn_rp_id` setting, empty ⇒ derived `urlparse(settings.frontend_url).hostname`; `webauthn_expected_origin` empty ⇒ `settings.frontend_url`. Dev = localhost (valid secure context), prod = frontend subdomain (F21).
- **Login session**: `auth_methods=["passkey"]` in session payload v2; password login writes `["password"]`, Google OAuth `["oauth_google"]`. `from_dict` defaults missing field to `[]` (legacy sessions stay valid).
- **Registration requires** `resident_key=REQUIRED` + `user_verification=REQUIRED` (A1: discoverable + conditional UI); authentication verify enforces `require_user_verification=True` (passkey = strong single factor).
- **Cap**: `mfa_max_passkeys_per_user` setting (default 10, constant `MFA_MAX_PASSKEYS_PER_USER_DEFAULT`).
- **Rate limits**: per-IP via existing `create_auth_rate_limiter` on anonymous endpoints (`webauthn_auth`, 10/min); per-user sliding window on enrollment endpoints (new `create_user_rate_limiter` factory, same Redis limiter, key `auth:{action}:user:{user_id}`).
- **Errors**: centralized raisers only; ceremony failures → `raise_invalid_credentials` (anonymous path — no credential enumeration) / `raise_invalid_input` (enrollment path); no raw lib exceptions to clients.
- **Metrics**: `webauthn_ceremonies_total{ceremony=register|authenticate, status=success|failure}` (+ registry entry per house pattern).
- **Lot 3 forward-compat note**: DELETE/rename endpoints ship with plain auth in Lot 1; step-up dependency added in Lot 3 (documented TODO in the program doc, not in code).

## Tasks

### Task 1 ✅ — Model + migration + data-map classification
Files: `src/domains/auth/models.py` (new), `alembic/versions/2026_07_23_*-add_webauthn_credentials.py` (down_revision=c9f1a2b8d374), `infrastructure/database/registry.py`, `infrastructure/startup/registries.py`, `src/domains/users/user_data_map.py` (+ purge entry in `account_deletion_service.build_purge_statements`).
TDD: Lot 0 guard goes red on the unclassified table → classify (USER_PURGED + EXCLUDED) + purge entry → green. `task db:migrate:replay-check`.

### Task 2 ✅ — Config + constants + .env
Files: `core/config/mfa.py` (new: `mfa_enabled`, `webauthn_rp_id/rp_name/expected_origin`, `webauthn_challenge_ttl_seconds`, `mfa_max_passkeys_per_user`), `core/config/__init__.py` (MRO), `core/constants.py`, `.env.example`, `.env.prod.example`.
TDD: settings-composition test (existing pattern) + defaults test.

### Task 3 ✅ — Session payload v2
Files: `infrastructure/cache/session_store.py` (UserSession.auth_methods + to_dict/from_dict + create_session param), `core/session_helpers.py` (pass-through param), `tests/unit/test_session_store.py` (round-trip v1→v2 + legacy defaults).

### Task 4 ✅ — Repository + service
Files: `src/domains/auth/webauthn_repository.py`, `src/domains/auth/webauthn_service.py`, tests `tests/unit/domains/auth/test_webauthn_service.py`.
Coverage: options generation (derived rp_id, exclude_credentials, resident key required), enrollment verify (happy, expired/missing challenge, duplicate credential_id, cap reached, label validation), login verify (happy → returns user + updates sign_count/last_used_at, unknown credential, sign-count regression reject, inactive user reject, challenge single-use), list/rename/delete ownership. py_webauthn verify_* functions monkeypatched at the service boundary (the lib is FIDO-conformance-tested; our logic is orchestration).

### Task 5 ✅ — Router + rate limiting + wiring + metrics
Files: `src/domains/auth/webauthn_router.py`, `src/domains/auth/schemas.py` (request/response models), `src/domains/auth/dependencies.py` (`create_user_rate_limiter`), `api/v1/routes.py` (flag-gated include), observability metrics module + registry.
Endpoints: POST `/auth/webauthn/register/options`, POST `/auth/webauthn/register/verify`, GET `/auth/webauthn/credentials`, PATCH `/auth/webauthn/credentials/{credential_id}`, DELETE `/auth/webauthn/credentials/{credential_id}`, POST `/auth/webauthn/authenticate/options` (anon), POST `/auth/webauthn/authenticate/verify` (anon, sets BFF cookie).
TDD: router tests via httpx AsyncClient app fixture if existing pattern; otherwise dependency-level tests + contract test for error codes.

### Task 6 ✅ — Frontend
Files: `src/lib/webauthn.ts` (base64url helpers + ceremony wrappers, feature detection incl. `isConditionalMediationAvailable`), `src/hooks/useWebAuthn.ts` (useApiMutation-based), `src/lib/api-config.ts` (endpoints), login page (`app/[lng]/(auth)/login/page.tsx`) passkey button + conditional UI, `src/components/settings/SecuritySettings.tsx` (list/add/rename/revoke dialogs), settings page wiring, `locales/{6}/translation.json`.
Tests: vitest for helpers (round-trip encode/decode), hook (mocked api), SecuritySettings (roles/names/keyboard, mocked hook). Gates: tsc clean, coverage, a11y/hooks/cc ratchets.

### Task 7 ✅ — E2E + runtime proof + docs
Playwright spec with CDP virtual authenticator (hermetic, mocked API), Docker containers rebuilt/restarted (deps in container!), `/health` + manual ceremony smoke via dev stack, ADR (next free number — check `docs/architecture/ADR_INDEX.md`), program doc tracker/session log.

### Self-review gate (every task)
`task lint` + targeted pytest → full `task test:backend:unit:fast` at lot end; systemic-rules checklist; no new cycles (F009 ratchet must stay ≤ 25).
