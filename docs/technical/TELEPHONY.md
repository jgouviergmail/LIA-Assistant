# Agentic Telephony — Technical Reference

Per-user, agentic **outbound calls**: LIA phones a third party on the user's
behalf, pursues a stated objective (read-only), and reports back asynchronously
in the chat. Vendor: **ElevenLabs Agents** (dials via Twilio/SIP).

- Architecture decision: [ADR-127](../architecture/ADR-127-Agentic-Telephony.md)
- Feature flag: `TELEPHONY_ENABLED` (default off). Per-user connector
  `ELEVENLABS_TELEPHONY` in *Préférences → Mes Connecteurs*.
- Status: implemented à blanc; vendor E2E gated on the P2.0 spike (see below).

## Architecture

```mermaid
flowchart TD
    U[User: "call Marie, ask if she's free Tuesday"] --> Tool[place_phone_call tool]
    Tool -->|connector active? resolve contact→phone| Draft[PHONE_CALL draft]
    Draft --> Critique[draft_critique — HITL confirm]
    Critique -->|confirm| Exec[execute_phone_call_draft]
    Exec --> Svc[TelephonyService.initiate_call]
    Svc -->|read-only, fields=start/end| Avail[availability.py — free/busy only]
    Svc -->|commit dialing row BEFORE dialing| DB[(phone_calls)]
    Svc -->|dynamic_variables incl. call_id| EL[ElevenLabs outbound-call]
    EL -. post-call webhook (HMAC) .-> WH[POST /telephony/webhook]
    WH -->|foreign-filter → per-user HMAC verify| Recon[authenticate_and_reconcile]
    Recon -->|fire-and-forget| PCC[process_completed_call]
    PCC -->|tool-less LLM synthesis| Synth[summary + proposal]
    Synth -->|mark_completed exactly-once| DB
    Synth --> Notif[NotificationDispatcher → chat + push]
```

**Key modules** (`src/domains/telephony/`):

| File | Role |
|---|---|
| `connector.py` | Activation wizard backend (validate key → provision guardrailed agent → store encrypted connector); `get_active` capability guard. |
| `client.py` | Thin async ElevenLabs Agents client (`xi-api-key`); `call_recording_enabled=false`; injectable transport for tests. |
| `agent_prompt.py` | Fixed guardrail system prompt + per-call dynamic vars + the `data_collection` schema (contract with the webhook extractor). |
| `availability.py` | Free/busy projection — **busy ranges only**, never titles/attendees/locations. |
| `service.py` | `initiate_call`: guard → one-active pre-check → availability → **commit dialing row → dial → persist conversation id**. |
| `webhook_handler.py` | Foreign-filter → resolve → agent match → per-user HMAC verify (Stripe-style `t=,v0=`). |
| `return_synthesis.py` | Tool-less synthesis (structured output) + `process_completed_call` (exactly-once, minimized persistence, token tracking, **arms + delivers the durable return outbox**). |
| `repository.py` | `PhoneCall` data access: F12 active-guard, `mark_completed` (atomic conditional UPDATE **+ PENDING outbox arm + SYNTHESIZED inbox close + transcript purge**), `mark_notification_delivered` / `fetch_recoverable_notifications` / `record_notification_failure`, **`persist_return_inbox` / `fetch_recoverable_returns` / `expire_stale_returns` (T1-A inbox)**, reaper queries. |
| `reapers.py` | Stale-call recovery (interval) + **return-notification recovery (interval, T1)** + **pre-synthesis return recovery (interval, T1-A)** + retention purge (daily). |
| Tool | `agents/tools/telephony_tools.py::place_phone_call` (draft-producing) + `execute_phone_call_draft`. |
| i18n | `core/i18n_telephony.py` (all backend strings, 6 languages). |

## Security invariants (do not weaken)

1. **Read-only, minimized by capability.** The agent only ever receives a
   free/busy snapshot (`fields=["start","end"]` → busy ranges). Meeting details
   are never fetched, so they cannot leak — regardless of what the callee asks.
2. **Per-user HMAC, foreign-filter first.** The webhook secret is per-connector;
   resolve `call_id → PhoneCall → connector` **before** verifying the signature.
   Unknown/foreign/malformed → 200 + ignored counter; known-call + forged
   signature → 4xx. No PII on any webhook log path.
3. **Secrets encrypted, never in JSONB.** API key + webhook secret live in
   `credentials_encrypted`; only non-secret ids in `connector_metadata`. The
   callee phone is encrypted at rest (`callee_phone`); the calls API
   (`GET /telephony/calls`) omits it entirely.
4. **No recording, transcript never persisted (D-8).** Only `summary` +
   minimized `StructuredCallData` survive; the transcript feeds synthesis then
   is discarded. The retention reaper clears content past its TTL.
5. **No PII at INFO/WARNING.** Logs carry IDs/counts/status only — never names,
   phones, summaries, or collected values (a `ValidationError` message is logged
   by type, not value, to avoid leaking a collected detail).

## Data model — `phone_calls`

One row per placed call. `status` (dialing → in_progress → completed/no_answer/
voicemail/failed/cancelled), `outcome` (objective_met/partial/declined/
unreachable), `call_seconds` (factual, never money — D-9), `summary` +
`structured_data` (purged after `expires_at`). Return-outbox columns (T1):
`notification_status` (pending/delivered/failed), `notification_payload`
(minimal `{content, title}` to re-dispatch without re-synthesizing),
`notification_attempts`. Three partial indexes: one-active-call-per-user (F12,
unique), the ElevenLabs conversation id (unique), and PENDING notifications by
completion time (the reaper's scan).

## Return durability (T1)

The return notification (summary + proposal) delivered to the user after a call
completes is a **transactional outbox**, so a hard crash cannot lose it:

1. `mark_completed` writes the terminal call state **and** `notification_status =
   PENDING` + `notification_payload` in ONE atomic conditional UPDATE. The return
   is a committed durable record *before* it is dispatched.
2. `process_completed_call` dispatches, then flips PENDING → DELIVERED **only after
   the dispatcher succeeds**. A dispatch error is swallowed (not re-raised — the
   old retry loop could never re-dispatch, since `mark_completed` is already
   terminal) and the row is left PENDING.
3. `telephony_notification_reaper` (interval, single-instance under leader election
   + `max_instances=1` = the lease) re-dispatches PENDING rows from their payload
   once past a grace window (so it never races the live dispatch of a
   just-completed call), bounded by `TELEPHONY_NOTIFICATION_MAX_ATTEMPTS` before a
   row is retired to FAILED.

### Pre-synthesis inbox (T1 approach A)

The outbox above only protects the window *after* synthesis. The webhook itself
is delivered by the vendor exactly once, so a crash *during* synthesis (before
`mark_completed`) previously lost the return. The pre-synthesis inbox closes that
window:

1. The webhook handler persists `return_status = RECEIVED` + the **Fernet-encrypted**
   raw payload (`return_webhook_encrypted`) + `return_received_at` and COMMITS
   **before responding 200**, so the transcript needed to (re)synthesize survives a
   crash — encrypted at rest (D-8 relaxation validated by the product owner).
2. `mark_completed` flips `RECEIVED → SYNTHESIZED` and **purges the encrypted
   transcript** in the same atomic transition, so it only rests on disk for the
   synthesis window.
3. `telephony_return_reaper` (interval, single-instance) re-runs the idempotent
   `process_completed_call` for `RECEIVED` rows past `TELEPHONY_RETURN_GRACE_SECONDS`
   (never racing the live synthesis), decrypting the persisted payload; a row still
   stranded past `TELEPHONY_RETURN_MAX_AGE_MINUTES` is retired to FAILED and its
   transcript purged.
4. The stale-call reaper explicitly **excludes `RECEIVED` rows** (the return reaper
   owns them), so it can never fail a recoverable call out from under recovery.

Crash matrix: *before `mark_completed`* → the encrypted `RECEIVED` inbox is
committed; the return reaper re-synthesizes from it after the grace window (incl.
after a restart), or gives up + purges past max-age; *after commit, before/mid
dispatch* → PENDING, the notification reaper recovers it on the next tick. A
duplicated webhook loses the `mark_completed` race (exactly-once) and never
reverts a SYNTHESIZED row back to RECEIVED. Worst case is a rare duplicate
notification on a mid-dispatch crash — deliberately preferred over a lost return.

## Configuration

All knobs are deployment-wide (`TelephonySettings`, `.env`); per-user secrets
live in the connector. Notable: `TELEPHONY_PREFETCH_WINDOW_DAYS`,
`TELEPHONY_MAX_CALL_DURATION_SECONDS`, `TELEPHONY_CALL_RETENTION_DAYS`,
`TELEPHONY_STALE_CALL_TIMEOUT_MINUTES`, `TELEPHONY_RATE_LIMIT_PER_HOUR`,
`TELEPHONY_WEBHOOK_TOLERANCE_SECONDS`, `TELEPHONY_STALE_REAPER_INTERVAL_MINUTES`,
and the return-outbox knobs `TELEPHONY_NOTIFICATION_GRACE_SECONDS`,
`TELEPHONY_NOTIFICATION_REAPER_INTERVAL_MINUTES`, `TELEPHONY_NOTIFICATION_MAX_ATTEMPTS`,
plus the pre-synthesis inbox knobs (T1 approach A) `TELEPHONY_RETURN_GRACE_SECONDS`,
`TELEPHONY_RETURN_MAX_AGE_MINUTES`, `TELEPHONY_RETURN_REAPER_INTERVAL_MINUTES`.

## Observability

Prometheus (`metrics_telephony.py`): `telephony_calls_total{status}`,
`telephony_call_duration_seconds` (histogram), `telephony_webhook_ignored_total{reason}`,
`telephony_notification_recovered_total{result}` (delivered/failed/skipped — the T1
reaper's recovery outcomes; a non-zero `failed` means returns exhausted their retries).
The synthesis LLM spend is tracked via `track_proactive_tokens` (task type
`phone_call`) — visible in the user's consumption export alongside briefing /
heartbeat. **Dashboards note**: add a Grafana panel row for the three counters
(calls by status, p50/p95 duration, ignored-webhook reasons) next to the
briefing/heartbeat proactive panels.

## Setup runbook (per user, spec §17)

1. Create an ElevenLabs account and generate an **API key** (workspace settings).
2. **Import a phone number** into the ElevenLabs workspace (Twilio import or SIP
   trunk — ElevenLabs sells no numbers). This is the number LIA calls *from*.
3. In LIA: *Préférences → Mes Connecteurs → Téléphonie* → paste the API key →
   validate → pick the number.
4. In the ElevenLabs workspace, create a **post-call (`post_call_transcription`)
   webhook** pointing at the URL LIA shows you
   (`<public-host>/api/v1/telephony/webhook`), and copy its **signing secret**.
5. Paste the secret in LIA and activate. LIA provisions a guardrailed agent in
   your workspace and the connector goes active.
6. Calls are billed on **your own** ElevenLabs/telephony accounts (D-9).

## Spike owed (P2.0 — before go-live)

Confirm against a real ElevenLabs + Twilio account (all marked `spike:` in code):

- create-agent body: exact prompt-text key + **data-collection config path**
  (assumed `platform_settings.data_collection`) — the identifiers
  (`agreed`/`proposed_datetime`/`location`/`notes`) are the contract with
  `return_synthesis._extract_structured` and are unit-test-guarded.
- webhook: exact signature header name (`ElevenLabs-Signature`) + post-call
  payload field paths (`call_id` in `dynamic_variables`, `agent_id`,
  `transcript_summary`, `data_collection_results`, `call_duration_secs`).
- voicemail-detection / max-duration config placement.
