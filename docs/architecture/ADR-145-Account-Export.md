# ADR-145: Full-Account Export — GDPR Portability (D3)

**Status**: ✅ IMPLEMENTED (2026-07-23)
**Date**: 2026-07-23
**Deciders**: jgouvier + Claude (security program, arbitrations A5/A6 decided 2026-07-23)
**Technical Story**: `docs/superpowers/specs/2026-07-23-security-account-program.md` — no account export existed (only consumption CSVs); the ADR-067 purge map (extended by Lot 0's total classification) is the data inventory.

---

## Decision

- **Durable jobs, not one-shot scheduling (A6)** — `account_export_jobs` table consumed by an interval executor (60 s, leader-elected, flag `ACCOUNT_EXPORT_ENABLED`) with `FOR UPDATE SKIP LOCKED` + atomic status transitions; one build at a time (RPi-class), one non-terminal job per user (partial unique index); RUNNING rows older than 30 min are failed `crashed` (restart-safe); the same tick sweeps expired archives (24 h retention, file deleted + row EXPIRED).
- **Metadata-driven builder — exclusions by construction** — the exportable set derives from `user_data_map.ExportPolicy.FULL`; EXCLUDED tables (connectors, MCP servers, FCM tokens, hm_ hashes, WebAuthn material, TOTP secrets, backup codes) can never reach an archive, asserted by `test_export_completeness.py` (every FULL table must be scopeable: owner column, override, or parent route — a new table fails CI until classified AND scopeable). Redaction (`return_webhook_encrypted`) and **decryption** (`callee_phone` via Fernet — portability means readable data, best-effort `[undecryptable]` fallback) are explicit, column-verified specs.
- **Archive** — `profile.json` (users columns minus SCRUBBED), `data/{table}.json` per table (stable schemas), `readable/{conversations,journal,memories}.md` (dual-format promise), `files/attachments` + `files/rag_documents` copied `ZIP_STORED` (A5 — derived chunks/vectors excluded); built via `asyncio.to_thread` into a temp file, size-capped (2 GiB, `export_too_large`), atomic rename into `{exports_storage_path}/{user_id}/{job_id}.zip`.
- **API** — request (**step-up required** — the archive holds decrypted personal data; 400 when one is active), latest-status, authenticated ownership-scoped download (404 on unknown/not-done/expired; `download_count` audit counter, never content in logs). FCM "your export is ready" push, localized ×6.
- **Lifecycle closure** — `account_export_jobs` classified USER_PURGED/EXCLUDED + purge entry; archives live under the user's exports dir (purged with the account's file cleanup).

## Deferred (tracked)

- **The builder materializes every table in memory before writing.** Fine for typical accounts; a years-long `conversation_messages` history could pressure RAM on RPi-class hardware (the 2 GiB cap is only measured AFTER the build). The follow-up is batched/keyset iteration streaming rows straight into the ZIP — naturally the same work as period scoping below.
- **Scope selection is NOT implemented.** The `account_export_jobs.scope` JSONB column is reserved (shape documented in its comment) but always NULL: the request endpoint takes no scope payload, the builder always exports the full account, and the frontend offers no pickers. An `export_too_large` failure currently has no self-service mitigation (copy says "contact support or reduce stored files"). Wiring scope (per-domain subset + `created_at` period for conversations) is the follow-up that also becomes the `export_too_large` escape hatch.

## Consequences

- Migration `b9d5f7a32c84`; `AccountExportSettings` config module in the Settings MRO; `.env` section [83].
- Frontend `AccountExportSettings` in the Security group (step-up guarded request, status badge, download link, self-hides on 404 when the flag is off).
- Rejected: per-domain hand-written exporters (the generic metadata-driven fetch + the completeness guard beats 25 bespoke functions and cannot drift); APScheduler `run_date` one-shots (lost on restart — the exact "features die invisibly" class).
