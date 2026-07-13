# Design Spec — Agentic Telephony (Outbound Calls)

- **Status:** Draft design spec (pre-implementation), **v5 — post validation/integrability review**. NOT committed to git; awaiting user review.
- **Date:** 2026-07-07 · Revisions: v2 (expert review F1–F16), v3 (per-user connector), v4 (second review N-1…N-16 + no-cost decision), **v5 (integrability review V-1…V-7: draft pattern)**. See §16.
- **Feature flag:** `TELEPHONY_ENABLED`

> Language note: English, to match the rest of `docs/`. Code identifiers verbatim.

---

## 1. Context & Goal

Give LIA the ability to **place an outbound phone call to a person, hold a
goal-directed conversation on the user's behalf, and asynchronously bring the
outcome back into the user's LIA conversation** — without blocking the assistant
while the call is in progress.

The objective is **generic and supplied by the user at request time**. During the
call the agent reasons about the user's availability via a **pre-fetched, minimized
free/busy** window (v1 has no live capability endpoint — §9).

**Hard constraint — user data protection:** read-only during the call; disclosure
minimized (free/busy only, never meeting details — applies to all domains); all
mutations happen **after** the call in a live user turn.

Telephony is **per-user**, modeled as a **connector** in "Préférences → Mes
Connecteurs" (D-7): each user brings their own ElevenLabs API key + phone number.
Because the vendor costs are billed to the **user's own accounts**, LIA does **not**
meter them (D-9).

---

## 2. Locked Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D-1 | Full production feature (not a POC). | User intent. |
| D-2 | **Agentic return = bounded reasoning+synthesis, no tools, no graph turn** → delivered via `NotificationDispatcher`. Mutations happen in the user's next **live** turn. | Safe by construction, deterministic (F1). |
| D-3 | **Number-agnostic** code (`agent_phone_number_id`). **Verified: ElevenLabs sells no numbers** — the user brings one via **Twilio native import** or a **SIP trunk** (Telnyx, Vonage, didlogic, …). | Both terminate at `agent_phone_number_id`. |
| D-4 | **No hard contact allow-list**, **HITL confirm before every call**, agent always **self-identifies**. | Irreversible outward action; the confirm is also the compliance "human intervention" (§9.4). |
| D-5 | **v1 availability = pre-fetch only** (no live endpoint). Live capability gateway → **v2** (§9.10). | Removes real-time latency/tunnel risk + public attack surface. |
| D-6 | **Consent = mandatory disclosure + consent-aware, no blocking.** Recording-consent line tied to D-8. | EU AI Act / TCPA / ElevenLabs Prohibited Use Policy. |
| D-7 | **Telephony is a PER-USER connector `ELEVENLABS_TELEPHONY` (full BYO).** User's own ElevenLabs key + number; LIA auto-provisions a guardrailed agent in their account. Per-user number ⇒ per-user caller-ID. **Activation is a custom multi-step flow** (Hue precedent), not the plain api-key route (N-2). | User requirement; reuses the `Connector` storage machinery. |
| D-8 | **No call recording / audio storage. Persist only the LLM `summary`** (+ minimal typed `structured_data`); retention TTL. Raw transcript used transiently for synthesis, then discarded. | Third-party (callee) data minimization + GDPR (F4). |
| D-9 | **No LIA-side metering of telephony costs.** ElevenLabs/Twilio minutes are billed to the **user's own accounts** — not a LIA-borne cost, so no pricing rows, no per-user cost aggregate, no Cost-tile line, no usage-limit impact. Only the **return-synthesis LLM call** (a real LIA cost) is tracked, via the existing token infra. `PhoneCall.call_seconds` is kept as factual metadata (display/metrics only). | User decision (second review, N-3): "ce n'est pas un coût global porté par LIA". |

---

## 2.1 Verification Log — proven vs deferred

**Verified in-code:**
- Return delivery: `NotificationDispatcher.dispatch()` → `_archive_message` →
  `get_or_create_conversation` + `archive_message` + commit (read end-to-end).
- `is_automated_source` gates only extraction, **not tools** (read) → the return is
  tool-less (F1).
- **1:1 user↔conversation** (`conversation.id == user_id`) — read.
- **Contact → phone**: normalizers expose `phoneNumbers[].value`,
  `semantic_type="phone_number"` — read.
- **Per-user API-key connector storage**: `Connector` (`credentials_encrypted` +
  `connector_metadata` JSONB + `preferences_encrypted`), `get_api_key_credentials`,
  `ConnectorGlobalConfig`, `UserConnectorsSection.tsx` — read.
- **`APIKeyActivationRequest` carries only key/secret/name/type** (read) → telephony
  activation **cannot** reuse the plain `/api-key/activate` route; the custom-flow
  precedent is **Philips Hue** (`HueBridgePairingForm.tsx`, `useHueConnect.ts`,
  dedicated endpoints) (N-2).
- **HITL confirm = DRAFT pattern (V-1, verified)**: `hitl_required=True` only drives
  ReAct's pre-execution interrupt (deliberately `False` on all mutating tools;
  unrendered "silent hang" for draft tools — `test_hitl_required_consistency.py`);
  pipeline `approval_gate` is auto-approved. The rendered/tested path is
  `create_event`-style: tool → `StandardToolOutput(requires_confirmation=True)` →
  `LIAToolNode` → `draft_critique` → `draft_executor`. `DraftType` (16 values,
  "extensible") + `DRAFT_DISPLAY_REGISTRY` + `assert_registry_completeness` (boot,
  ADR-085). → `place_phone_call` adds `DraftType.PHONE_CALL`.
- **`APIKeyConnectorTool` is a poor fit (V-2, verified via `perplexity_tools.py`)**:
  it is single-connector query→format; the tool orchestrates connector-check +
  contacts resolution + draft. Model it on `create_event_tool` instead.
- **No calendar `freebusy` (V-3, verified)**: `google_calendar_client` has no
  free/busy read → `availability.py` reads `list_events` and projects server-side
  to free/busy (holds full events transiently, returns only free/busy).
- **STT cost chokepoint is `ChatRepository.add_stt_usage` on `UserStatistics`**
  (read; Python read-modify-write, not the atomic UPSERT) — recorded for accuracy;
  **not imitated** since D-9 removes telephony cost metering (N-1).
- `ConnectorType` is `native_enum=False` (string column) → **adding the enum value
  needs no DB migration** (N-5).
- `NotificationDispatcher._get_localized_title` lacks a `phone_call` title (F10).

**Verified in vendor docs (fetched — current "ElevenAgents" platform, the 2026
rebrand of Conversational AI 2.0):**
- **Outbound call**: `POST /v1/convai/twilio/outbound-call` — body `agent_id`,
  `agent_phone_number_id`, `to_number`, `conversation_initiation_client_data.
  dynamic_variables`, **`call_recording_enabled` (bool)** and
  `telephony_call_config.ringing_timeout_secs`; response `success`, `message`,
  `conversation_id`, `callSid`. → **D-8 is enforceable per call**
  (`call_recording_enabled=false`).
- **Create agent**: `POST /v1/convai/agents/create` — `conversation_config.agent.
  {prompt{llm,tool_ids}, first_message, language}`, `platform_settings`, `name`.
  → per-user agent auto-provisioning is API-feasible; **language is set at agent
  creation** (per-user agent ⇒ no per-call language override needed; update the
  agent on user language change).
- **Phone numbers**: `GET /v1/convai/phone-numbers` → `phone_number_id`,
  `phone_number`, `provider (twilio|sip_trunk|exotel)`, `assigned_agent` — the
  wizard's number-selection step is API-feasible. Twilio import is UI-based
  (Label + number + Account SID + Auth Token); **ElevenLabs auto-configures the
  Twilio side** and auto-detects Outbound/Inbound capability. Agent *assignment*
  matters only for inbound; outbound passes `agent_id` per call.
- **Post-call webhook**: configured **workspace-wide via the UI**
  (`elevenlabs.io/app/agents/settings`) — **no documented configuration API** →
  the activation wizard's **guided manual step is the path** (N-4a resolved, not
  a fallback). HMAC secret generated at webhook creation; verify via
  `construct_event`. Three types: `post_call_transcription` (used),
  `post_call_audio` (**not enabled** — D-8), `call_initiation_failure` (optional
  fast-failure signal). Per-agent webhook overrides exist for audio toggles.
- Dynamic variables incl. `secret__` (header-only); native voicemail detection;
  ElevenLabs sells **no** numbers (BYO); Prohibited Use Policy (no robocalling
  without human intervention).

**Deferred to implementation (non-blocking, shrunk after the vendor-doc pass):**
- Exact `post_call_transcription` payload field paths + `call_id` echo shape
  (confirm on the first vertical-slice call).
- Max-call-duration + voicemail-detection config field names inside
  `conversation_config`/`platform_settings` (create-agent body details).

**Known v1 limitations (accepted):** pre-fetch availability only for objectives with
a determinable date window (G2); structured extraction relies on the D-2 synthesis.

---

## 3. Scope

**In scope (v1):**
- New bounded context `domains/telephony/` (no LangGraph graft).
- **Per-user `ELEVENLABS_TELEPHONY` connector** with a **custom activation flow**
  (§4.2): key validation, number selection, agent auto-provisioning, webhook setup,
  kill-switch, Mes Connecteurs UI.
- `place_phone_call` tool (inherits `APIKeyConnectorTool`; HITL confirm).
- Availability pre-fetch (minimized free/busy).
- Post-call webhook (per-user HMAC, **foreign-event filtering**) → **D-2 synthesis
  return** + notification.
- Native voicemail detection.
- Observability, i18n (6 languages), tests, docs + ADR.

**Out of scope (v1) — YAGNI:**
- Live read-only capability gateway → **v2** (§9.10).
- Call recording / audio storage (D-8); **telephony cost metering** (D-9).
- Contact allow-list; offline HITL buttons; MCP exposure; inbound calls; >1
  in-flight call per user; capabilities beyond calendar availability; pushed
  call-status updates (v1 shows "call initiated" + the return; SSE status is a
  possible polish).

---

## 4. Architecture Overview

Self-contained domain (`channels/`/`briefing/` pattern). Two async flows:

```
FLOW A — Initiate (synchronous to the user, non-blocking on the call)
  User (chat): "call Marie: OK restaurant Saturday noon? where?"
    └─ tool place_phone_call  (DRAFT-producing tool, like create_event — V-1)
         ├─ verify caller's ELEVENLABS_TELEPHONY connector active; else guide to activate
         ├─ resolve contact → phone (search_contacts → phoneNumbers; ambiguity → HITL clarify)
         └─ return StandardToolOutput(requires_confirmation=True, draft_type="phone_call",
              _draft_content={callee_name, callee_phone, objective, date_window})
                ↓ LIAToolNode → pending_draft_critique → draft_critique node
         ├─ preview "📞 Appeler Marie au 06.. — Objectif: …"  ── cancel → no row, no call
         │                                                     ── edit → change objective/number
         │                                                     └─ confirm ↓
         └─ draft_executor (PHONE_CALL branch):
              ├─ pre-fetch minimized availability over the objective's date window   [F9]
              ├─ TelephonyService.initiate_call():
              │     • create PhoneCall row (status=dialing) under the unique-active guard  [F12]
              │     • ElevenLabs outbound-call via the user's key/agent/number
              │        (dynamic_variables={call_id, objective, callee_name, user_name,
              │                            availability_summary, recording_disclosure})
              │     • persist elevenlabs_conversation_id
              └─ turn ends non-blocking ("call initiated")

FLOW B — Return (D-2 bounded synthesis — NO agent turn, NO tools)
  Call ends → ElevenLabs POST post_call_transcription (workspace-level webhook)
    └─ POST /telephony/webhook
         ├─ parse UNTRUSTED body only to read the echoed call_id
         ├─ FILTER: unknown call_id / foreign agent → 200, silently ignored,
         │   nothing logged beyond a counter (the user's other agents may post here)  [N-13]
         ├─ resolve call_id → PhoneCall → user → connector → the user's webhook secret
         ├─ HMAC-verify (construct_event, strict timestamp window); 200 fast;
         │   safe_fire_and_forget  [F7, F14]
         ├─ record call_seconds (metadata only — no cost metering, D-9)
         ├─ synthesize_return(): ONE LLM call, NO tools — summary + proposal
         │   (persist summary only — D-8; synthesis tokens tracked by existing infra)
         └─ NotificationDispatcher.dispatch(task_type="phone_call") →
             single archive + FCM + SSE + Telegram
    User replies "yes" → NORMAL LIVE TURN → create_event with its real HITL.
```

### 4.1 Module layout (`apps/api/src/domains/telephony/`)

| File | Responsibility |
|------|----------------|
| `models.py` | `PhoneCall` (§5). |
| `schemas.py` | Pydantic request/response + webhook payload + typed `StructuredCallData` + activation-flow schemas. |
| `repository.py` | `BaseRepository[PhoneCall]`; `get_by_call_id`, active-call guard. |
| `service.py` | `TelephonyService`: `initiate_call()`, `handle_completed_call()`, status transitions. |
| `client.py` | ElevenLabs Agents client (httpx async); key/agent/number from the caller's connector. |
| `connector.py` | **Custom activation flow** (§4.2): validate key → select/import number → auto-create guardrailed agent → webhook setup → create the `Connector` row. Also deactivation cleanup (N-14). |
| `availability.py` | `build_availability_summary(user_id, window)` → minimized free/busy. |
| `return_synthesis.py` | `synthesize_return(...)` → tool-less LLM call (versioned prompt, i18n). |
| `webhook_handler.py` | Foreign-event filter, per-user HMAC verify, synthesis, dispatch. Idempotent. |
| `router.py` | `POST /telephony/webhook`, `GET /telephony/calls`, `POST /telephony/connector/*` (activation steps). Feature-flag guarded. |
| `core/config/telephony.py` | `TelephonySettings` (flag, caps, rate limits, prefetch window, retention TTL, timeouts — no per-user creds). |
| `agents/tools/telephony_tools.py` | `place_phone_call` — **draft-producing tool** modeled on `create_event_tool` (V-2); emits a `PHONE_CALL` draft. |

### 4.2 Per-user connector (`ELEVENLABS_TELEPHONY`)

**Storage** (reuses the `Connector` row — verified):
- `credentials_encrypted` ← **ElevenLabs API key AND the post-call webhook secret**
  (both are secrets → both live in the encrypted payload; the webhook secret is
  **never** stored in `connector_metadata`/JSONB — N-4b).
- `connector_metadata` (JSONB) ← non-secret identifiers only: `agent_id`,
  `agent_phone_number_id`, `caller_number_display`.
- `preferences_encrypted` ← per-user prefs (default language, caller display name).
- Add `ConnectorType.ELEVENLABS_TELEPHONY` (**code-only; `native_enum=False` ⇒ no DB
  migration for the enum** — N-5) + a new functional category `"telephony"` in
  `CONNECTOR_FUNCTIONAL_CATEGORIES` / `CATEGORY_DISPLAY_NAMES` (single member today —
  N-6) + `CONNECTOR_DISPLAY_NAMES` entry.

**Activation flow — custom, multi-step (Hue precedent, N-2).** The plain
`/connectors/api-key/activate` route cannot carry number/agent setup (verified). A
dedicated wizard (`POST /telephony/connector/*` + a `TelephonyConnectorForm` modeled
on `HueBridgePairingForm`):
1. **Validate** the pasted ElevenLabs API key (ping the API; masked-key response).
2. **Number**: list the phone numbers available in the user's ElevenLabs workspace
   (imported from Twilio or SIP — D-3); user picks one → `agent_phone_number_id`.
3. **Agent**: auto-create the **LIA-controlled** guardrailed agent in the user's
   account (fixed prompt + variable slots + voicemail + cost guardrails); store
   `agent_id`.
4. **Webhook** (verified: **UI-only, workspace-wide — no configuration API**): a
   **guided manual step** — the wizard shows LIA's webhook URL, walks the user
   through `elevenlabs.io/app/agents/settings` → create a `post_call_transcription`
   webhook (**never enable `post_call_audio`** — D-8), and captures the generated
   HMAC **secret** into the encrypted credentials (N-4).
5. Create the `Connector` row (via `ConnectorService`), status `ACTIVE`.

**Deactivation / deletion (N-14):** best-effort delete of the LIA-created agent in
the user's account (ignore failures — it is the user's workspace); any in-flight
`PhoneCall` is left to the stale reaper (`failed`). Global kill-switch via
`ConnectorGlobalConfig` like every connector.

**Retrieval:** `get_api_key_credentials(user_id, ELEVENLABS_TELEPHONY)` +
`connector_metadata` — called explicitly by `draft_executor`/`TelephonyService` at
call time and by the webhook handler. The tool only *checks* the connector is active
when building the draft; the API key is needed at call time, not at draft time (V-2).

---

## 5. Data Model — `PhoneCall`

SQLAlchemy 2.0, `UUIDMixin`+`TimestampMixin`; registered in the 3 places + migration.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | `UUID` FK CASCADE, indexed | Owner. Return archives into this user's single conversation (verified 1:1). |
| `callee_display` | `str` | Display name (not the number). |
| `callee_phone` | `str` (encrypted) | PII — encrypted, never at INFO. |
| `objective` | `str` | The per-call goal. |
| `objective_window_start/_end` | `DateTime(tz)`, nullable | Pre-fetch window (null ⇒ open-ended, no pre-fetch). |
| `status` | `str` enum | `dialing → in_progress → completed | no_answer | voicemail | failed | cancelled`. **Two-object lifecycle (V-7):** a `PHONE_CALL` *draft* (DraftStatus PENDING→CONFIRMED) precedes the row; the `PhoneCall` row is created at `dialing` **when `draft_executor` runs on confirm**. Cancel/edit-then-cancel ⇒ draft CANCELLED, no `PhoneCall` row (F13). |
| `elevenlabs_conversation_id` | `str`, nullable, unique(partial) | Reconciliation fallback. |
| `call_seconds` | `Numeric(12,2)`, nullable | Duration from the webhook — **factual metadata only, never costed** (D-9). |
| `summary` | `str`, nullable | From synthesis. **No raw transcript/audio stored** (D-8). |
| `structured_data` | `JSONB`, default `{}` | Typed on ingest (`StructuredCallData`); new-dict reassignment only. |
| `outcome` | `str` enum, nullable | `objective_met | partial | declined | unreachable`. |
| `error` | `str`, nullable | Classified (no traceback). |
| `initiated_at/completed_at` | `DateTime(tz)`, nullable | UTC-aware. |
| `expires_at` | `DateTime(tz)` | Retention TTL (D-8); reaper purges `summary`/`structured_data`. |

**Concurrency (F12):** unique partial index on `user_id` `WHERE status IN
('dialing','in_progress')` — one active call per user, atomic.

---

## 6. External Contracts — ElevenLabs Agents

### 6.1 The agent (per-user, LIA-created — §4.2)
One **LIA-controlled** agent per user account, provisioned at activation via
`POST /v1/convai/agents/create` (verified): fixed guardrail system prompt +
dynamic-variable slots (`{{user_name}}`, `{{callee_name}}`, `{{objective}}`,
`{{availability_summary}}`, `{{recording_disclosure}}`), localized disclosure
first message, `language` = the user's language, **voicemail detection**, max
duration + auto-hangup on silence. Guardrails immutable; only variables vary per
call.

**Config-drift protection:** the agent lives in the *user's* workspace, so the
user could hand-edit it. Since the guardrails protect the user's own data, drift
is self-harm, not a cross-user risk — still, LIA **re-asserts the guardrail
config (idempotent update) before each call**, making drift a non-issue at the
cost of one cheap API call.

### 6.2 Outbound call initiation (schema verified)
`POST /v1/convai/twilio/outbound-call` with the **caller's** `agent_id`,
`agent_phone_number_id`, `to_number`; `conversation_initiation_client_data.
dynamic_variables` carrying our **`call_id`** (primary reconciliation key — F7),
`objective`, `callee_name`, `user_name`, `availability_summary`,
`recording_disclosure`; **`call_recording_enabled=false`** (D-8 enforced at the
API level); `telephony_call_config.ringing_timeout_secs` from settings. Response:
`success`, `conversation_id` (→ `elevenlabs_conversation_id`), `callSid`. The
call **language** is fixed at agent creation (per-user agent, F8b); LIA updates
the agent when the user's language changes. Pre-fetch + initiation run only after
HITL approval (F9).

### 6.3 Availability pre-fetch
Busy intervals over the objective's window via the calendar connector — **verified
(V-3): no `freebusy` read exists, so `availability.py` reads `list_events` and
projects server-side to free/busy** (holds full events transiently, returns only
free/busy) — injected as `{{availability_summary}}`.
Window-bounded ⇒ inherent minimization. `date_window` is **agent-supplied and
required when the objective implies a deadline** (no silent no-op — F8a); open-ended
objectives get no in-call availability (G2), times reconciled post-call.

### 6.4 Post-call webhook (workspace-level — hardened)
Type `post_call_transcription`. **The webhook is configured at the ElevenLabs
workspace level**, so LIA may receive events from the user's **other, non-LIA
agents** (N-13). Handler contract, in order:
1. Parse the untrusted body **only** to extract the echoed `call_id`.
2. **Filter:** no `call_id` / unknown `call_id` / `agent_id` ≠ connector's →
   return 200, increment a `telephony_webhook_ignored_total` counter, **log no
   content** (foreign events are the user's private data).
3. Resolve `call_id → PhoneCall → user → connector → webhook secret` (from the
   **encrypted** credentials — N-4b).
4. HMAC-verify via `construct_event` (strict timestamp tolerance) + endpoint
   rate-limit (F14). Only then trust the payload.
5. 200 immediately; process via `safe_fire_and_forget` (own DB session). Reconcile
   by `call_id`; idempotent on terminal status. Persist `summary` only (D-8);
   record `call_seconds` (no costing — D-9).

### 6.5 Voicemail
Native system tool (leave localized message or hang up) → `status=voicemail`,
`outcome=unreachable`.

---

## 7. The Tool — `place_phone_call` (DRAFT pattern, like `create_event`)

**Corrected in v5 (V-1):** the confirm is **not** `hitl_required=True` (that flag
only drives ReAct's pre-execution interrupt and is deliberately `False` on every
mutating tool — for draft tools it is "redundant AND currently unrendered (silent
hang)", enforced by `test_hitl_required_consistency.py`; and pipeline
`approval_gate` is auto-approved). LIA's canonical "confirm/preview/edit before an
irreversible action" is the **draft pattern** (`create_event` produces a draft →
`draft_critique` → `draft_executor`). `place_phone_call` follows it exactly.

- **Model on `create_event_tool`** (a draft-producing tool, `operation="create_draft"`),
  **not** `APIKeyConnectorTool` (V-2: that base is single-connector query→format;
  this tool orchestrates the telephony connector check + contacts resolution).
- **Params:** `contact`, `objective`, `date_window` (required when the objective
  implies a deadline — F8a), optional `context`.
- **Behavior:** verify the caller's `ELEVENLABS_TELEPHONY` connector is active
  (else guidance to activate it) → resolve `contact → phone` (`search_contacts` →
  `phoneNumbers`; ambiguity → existing HITL clarification; prefer mobile) → return
  `StandardToolOutput(requires_confirmation=True)` with `_draft_content =
  {callee_name, callee_phone, objective, date_window}` and `draft_type="phone_call"`.
- **HITL flow (verified mechanism):** `LIAToolNode` detects `requires_confirmation`
  → `pending_draft_critique` → `draft_critique` node renders the preview from
  `DRAFT_DISPLAY_REGISTRY[PHONE_CALL]` ("📞 Appeler Marie au 06.. — Objectif : …")
  → user **confirms / edits / cancels**. Edit (change objective or number) and
  cancel come **for free** from the draft machinery (`DraftStatus` PENDING→MODIFIED→
  CONFIRMED / CANCELLED). Cancel ⇒ no `PhoneCall` row, no call (F13). The draft
  preview showing the **resolved number** is what makes this correct (the number is
  known before the confirm — impossible with `hitl_required`).
- **Execution on confirm:** `draft_executor` runs the `PHONE_CALL` branch →
  pre-fetch availability (F9) → `TelephonyService.initiate_call()` (creates the
  `PhoneCall` row at `dialing` under the unique-active guard F12) → the call is
  initiated; the turn ends non-blocking.
- **New registrations required (draft pattern):** `DraftType.PHONE_CALL` in
  `drafts/models.py`; a `DRAFT_DISPLAY_REGISTRY[PHONE_CALL]` entry
  (`assert_registry_completeness` refuses to boot without it — ADR-085) + `noun`/
  `verb_past` + preview-label i18n keys ×6 (call/appel, placed/passé); the
  `PHONE_CALL` execution branch in `draft_executor`.
- **Policy:** `@track_tool_metrics` + `@rate_limit`; registry + catalogue + manifest
  (`data_classification="SENSITIVE"`, **`hitl_required=False`** — the draft flow
  gates it, per the calendar-manifest invariant); `ToolErrorModel`/`ToolErrorCode`
  on failure.

---

## 8. Asynchronous Return — D-2 bounded synthesis (NO agent turn, NO tools)

`synthesize_return(...)`: a **single, tool-less LLM call** (versioned prompt, i18n)
that reasons over `transcript`+summary, decides whether an action is warranted, and
composes the user-facing proposal. It cannot mutate (no tools) and cannot trigger a
phantom HITL (F1). Its tokens are tracked by the **existing token infra** — the only
LIA-borne cost of a call (D-9). Persist `summary` + typed `structured_data` (D-8).
Deliver once via `NotificationDispatcher.dispatch(content=proposal,
task_type="phone_call", target_id=call_id)` — single archive + FCM + SSE + Telegram
(F2). The mutation is the user's **next live turn**.

---

## 9. Security & Data-Protection Model

**Defense by capability, not by prompt.**

- **9.1 Bounded blast radius:** in-call, only the minimized free/busy window; the
  return has no tools.
- **9.2 Read-only** in-call and at return; mutations only in live user turns.
- **9.3 Minimization:** free/busy only, window-bounded, generic projection.
- **9.4 Consent / vendor policy (D-6):** per-call HITL confirm = the "human
  intervention"; mandatory self-identification; recording line tied to D-8;
  anti-bulk (1 in-flight/user + rate limit); each user on **their own** ElevenLabs
  account (D-7). ADR scopes to personal, per-call-authorized calls.
- **9.5 Anti-injection:** fixed guardrail prompt + variable slots; secrets (v2) via
  `secret__` header-only vars.
- **9.6 Third-party (callee) data (F4/D-8):** no audio/raw transcript stored;
  summary + minimal typed data; retention TTL + reaper.
- **9.7 Sub-processor egress (F5):** minimized free/busy goes to the user's own
  ElevenLabs LLM (their account/DPA) — deliberate, minimized, sanctioned level.
- **9.8 Secrets & PII:** ElevenLabs key **and webhook secret** in
  `credentials_encrypted` (never JSONB — N-4b); `callee_phone` encrypted; no PII at
  INFO; foreign webhook events never logged (N-13).
- **9.9 Webhook hardening (F14/N-13):** foreign-event filter → per-user HMAC →
  strict timestamp window → rate-limit; fast 200 + background work.
- **9.10 v2 — live capability gateway (documented, NOT built):** `phone_exposable`
  manifest flag + boot assert (fail-closed); purpose-built minimal capabilities;
  per-call `secret__` capability token; args clamped to the window; probe
  rate-limit; audit; explicit infra decision (real-time endpoint vs RPi5/tunnel).

---

## 10. Costs (D-9 — deliberately not metered)

- **Vendor costs (ElevenLabs minutes, Twilio/SIP telephony) are the user's own** —
  billed to their accounts, invisible to LIA's cost model. No pricing-seed rows, no
  `UserStatistics` columns, no Cost-tile line, no usage-limit impact.
- **Indicative magnitude** (for docs/ADR only; secondary sources): ElevenLabs Agents
  ~$0.08/min + Twilio FR-origin ~$0.05/min ⇒ a 3-min call ≈ **~$0.40**, paid by the
  user to the vendors directly.
- **LIA-borne cost = the return-synthesis LLM call** — tracked by the existing
  token-tracking infra (counts toward the user's LIA usage totals/limits normally).
- The connector UI states plainly: *"Calls are billed by ElevenLabs/your telephony
  provider on your own accounts."* (6 languages).
- `PhoneCall.call_seconds` + a Prometheus duration histogram remain for
  observability — never converted to money.

**Provisioning (per-user; each brings their own):** Twilio native import (least
friction) or a SIP trunk (Telnyx/didlogic — instant numbers, often cheaper). Code
stays agnostic behind `agent_phone_number_id` (D-3).

---

## 11. Integration Points (CLAUDE.md runtime checklist)

1. **Config**: `TelephonySettings` in the MRO; `TELEPHONY_ENABLED`; `.env*` updated.
2. **Constants** centralized; parameterizable via settings.
3. **Models**: `PhoneCall` registered in the 3 places — `alembic/env.py`,
   `registry.py::import_all_models`, `startup/registries.py::import_domain_models`
   (ADR-123, V-6); Alembic migration (single head) incl. the unique partial index.
   (`ConnectorType` addition is **code-only**, no migration — N-5.)
4. **Router**: `/telephony/webhook`, `/telephony/calls`, `/telephony/connector/*`
   behind `telephony_enabled`.
5. **Startup**: stale-call reaper + retention reaper registered in
   `startup/schedulers.py::init_scheduler` (V-6, not raw `main.py`), flag-guarded.
   The `DRAFT_DISPLAY_REGISTRY` completeness assert already runs at boot.
6. **Prompts**: `synthesize_return` in versioned `prompts/v1/` + its name in the
   `PromptName` Literal (V-4); agent prompt strings + LIA i18n (no inline French).
7. **LangGraph + drafts**: tool registered + catalogue + manifest
   (`hitl_required=False`); **`DraftType.PHONE_CALL` + `DRAFT_DISPLAY_REGISTRY` entry
   + `draft_executor` branch** (V-1) with draft noun/verb/label i18n ×6; a new
   **`telephony_synthesis` LLM type** in `core/config/agents.py` (V-4).
8. **Frontend**: telephony connector card + **multi-step activation wizard**
   (`TelephonyConnectorForm`, Hue precedent) in `UserConnectorsSection`;
   `ConnectorIcon` + `constants/connectors.ts`; `useTelephony` hook + call history.
9. **i18n (6 languages)**: HITL confirm, disclosure, voicemail message, `phone_call`
   notification title (F10), synthesis scaffolding, connector wizard strings,
   billing notice — full parity.
10. **Observability**: metrics — calls by status, duration histogram,
    `telephony_webhook_ignored_total` (N-13), synthesis tokens; errors with context.
11. **Exceptions**: custom + `ToolErrorCode`.
12. **Dependencies**: ElevenLabs SDK + httpx (present). Host/container parity.
13. **Docs + ADR**: "Agentic telephony + per-user connector + read-only capability
    model"; cross-refs (`ADR_INDEX.md`, `docs/INDEX.md`); technical doc; G2
    limitation + BYO billing noted for users.

---

## 12. Failure Modes & Handling

| Mode | Handling |
|------|----------|
| No telephony connector / inactive | Tool returns guidance to activate it in Mes Connecteurs (base-class behavior). |
| User rejects HITL confirm | No row, no call (F13). |
| No answer / voicemail | Native detection; `no_answer`/`voicemail`; return informs the user. |
| Ambiguous outcome | Synthesis states it; no or clarifying proposal. |
| API error at initiation | Classified `ToolErrorCode`; row rolled back. |
| Webhook never arrives / duplicate | Stale reaper → `failed`; idempotent on `call_id`. |
| Foreign workspace event (user's other agents) | Filtered: 200 + counter, nothing logged (N-13). |
| Reconciliation timing | Echoed `call_id` created before the call can complete (F7). |
| Second concurrent call | Fails atomically (unique-active index, F12). |
| Connector deleted mid-call | Best-effort agent cleanup; in-flight call → stale reaper (N-14). |
| Tunnel down at return | Webhook retryable/delay-tolerant → acceptable. |
| Cost runaway | Max duration cap + auto-hangup on silence (user's own billing anyway — D-9). |
| Retention | `expires_at` reaper purges summary/structured_data (D-8). |

---

## 13. Testing

- `structured_data` msgpack/JSONB round-trip (F15); `StructuredCallData` validation.
- Webhook: **foreign-event filter** (unknown `call_id`/`agent_id` → 200, ignored,
  no content logged) (N-13); per-user HMAC (valid, wrong secret, invalid signature,
  replay/expired) (F14); reconciliation by `call_id` incl. webhook-early race (F7);
  idempotency.
- **Minimization**: `availability.py` output = free/busy only.
- **Return safety (F1)**: `synthesize_return` has no tools; delivered even when the
  LLM "wants" to act. **Single archive** (F2).
- **Connector**: custom activation flow (validate → number → agent → webhook secret
  into encrypted credentials — N-4b); `get_api_key_credentials` round-trip; tool
  fails gracefully without connector; deactivation cleanup (N-14); global
  kill-switch.
- **No cost metering (D-9)**: completing a call adds **nothing** to
  `UserStatistics` cost columns; synthesis tokens ARE tracked.
- **Draft flow (V-1)**: tool emits `requires_confirmation`; `draft_critique` preview
  shows the **resolved number**; confirm → `draft_executor` creates the row + places
  the call; edit changes objective/number; cancel ⇒ no row/no call;
  `DRAFT_DISPLAY_REGISTRY[PHONE_CALL]` present (boot assert).
- HITL cancel path (F16); concurrency (F12); call language (F8b); retention (D-8);
  i18n parity (incl. `phone_call` title + draft noun/verb); feature-flag off →
  routes/tool absent.

---

## 14. Open Items to Confirm at Implementation (non-blocking)

- Exact ElevenLabs outbound-call endpoint + webhook field paths + `call_id` echo.
- **Create/configure-agent API** and **workspace-webhook configuration API** (else:
  guided manual step in the activation wizard) (N-4a).
- Listing the workspace's imported phone numbers via API (activation step 2).
- `max_call_duration` field; `conversation_config_override.language` support.
- (v2) Webhook-tool `response_timeout` for the live gateway.

---

## 15. Definition of Done (v1)

- Each user activates telephony in **Mes Connecteurs** via the multi-step wizard
  (own ElevenLabs key + number; LIA auto-creates the guardrailed agent; webhook
  secret captured into encrypted credentials).
- A user asks LIA to call a contact with an arbitrary objective; HITL confirm;
  reject ⇒ nothing; approve ⇒ call placed from **their** number, assistant returns
  immediately.
- The agent self-identifies (user's language), pursues the objective, answers
  availability within the pre-fetched window without revealing details.
- On call end: foreign events filtered; per-user **HMAC-verified** webhook →
  **tool-less synthesis** → summary + optional proposal delivered **once** into the
  user's conversation (+ push/SSE); confirming creates the event via the normal
  live HITL.
- **No telephony cost metering** (D-9); synthesis tokens tracked normally; duration
  metrics emitted.
- Voicemail/no-answer/reject/duplicate/race/foreign-event handled; 6-language
  parity; tests green; behind `TELEPHONY_ENABLED`; ADR + docs.
- Security invariants: read-only in-call, no tools at return, free/busy-only, no
  audio/raw-transcript stored, no PII at INFO, secrets only in encrypted
  credentials, per-user HMAC + replay-protected + filtered webhook, atomic
  concurrency guard.

---

## 16. Revision Log

**v5 — validation review / integrability (this revision):**

| Finding | Sev. | Resolution | Where |
|---------|------|------------|-------|
| **V-1** HITL mechanism wrong: `hitl_required=True` is ReAct-only + unrendered for draft tools ("silent hang"); pipeline `approval_gate` auto-approved | 🟠 | Adopt the **draft pattern** (`DraftType.PHONE_CALL` + `DRAFT_DISPLAY_REGISTRY` + `draft_critique` + `draft_executor`) like `create_event`. Fixes resolved-number-in-preview; adds edit/cancel free. | §2.1, §4, §5, §7, §11, §13 |
| **V-2** `APIKeyConnectorTool` poor fit (single-connector query→format) | 🟠 | Model the tool on `create_event_tool` (draft producer), not the API-key base. | §2.1, §7 |
| **V-3** No calendar `freebusy` (verified) | 🟡 | `availability.py` uses `list_events` + server-side projection (holds events transiently, returns only free/busy). | §2.1, §6.3, §14 |
| **V-4** Synthesis LLM type + `PromptName` not wired | 🟡 | New `telephony_synthesis` type in `core/config/agents.py` + `PromptName` entry. | §11 |
| **V-6** Model/scheduler registration named loosely | 🟡 | Corrected to `startup/registries.py::import_domain_models` + `startup/schedulers.py::init_scheduler` (ADR-123). | §11 |
| **V-7** Draft-vs-PhoneCall two-object lifecycle | 🟡 | Clarified: draft (PENDING→CONFIRMED) precedes the row (created by executor). | §5, §7 |

**v4 — second expert review:**

| Finding | Sev. | Resolution | Where |
|---------|------|------------|-------|
| **N-1** D-9 cited the wrong cost chokepoint (`create_or_update_token_summary`; real precedent is `add_stt_usage` on `UserStatistics`, non-atomic) | 🟠 | Moot for costing (see N-3) but corrected in the verification log for accuracy. | §2.1 |
| **N-2** Plain `/api-key/activate` cannot carry number/agent setup (schema verified) | 🟠 | **Custom multi-step activation wizard** (Philips Hue precedent) with dedicated `/telephony/connector/*` endpoints. | D-7, §4.1, §4.2, §11.8 |
| **N-3** BYO vendor cost vs LIA usage limits — product decision | 🟠 | **User decision: no LIA-side metering at all** (D-9 rewritten): no pricing rows, no aggregate columns, no Cost-tile line; only synthesis tokens tracked; `call_seconds` kept as metadata. | D-9, §3, §5, §10, §13, §15 |
| **N-4** Workspace-level webhook config + secret stored in JSONB | 🟠 | (a) create-agent **and** workspace-webhook APIs elevated to explicit §14 items with a guided-manual fallback; (b) webhook secret moved into `credentials_encrypted` — never JSONB. | §2.1, §4.2, §6.4, §9.8, §14 |
| **N-13** Workspace webhook receives the user's other agents' events | 🟠 | **Foreign-event filter** before anything else: 200 + counter, nothing logged; then per-user HMAC. | §4 Flow B, §6.4, §9.9, §12, §13 |
| **N-5** `ConnectorType` is `native_enum=False` → no migration for the enum | 🟡 | Stated; §11.3 corrected. | §2.1, §4.2, §11.3 |
| **N-6** Functional category | 🟡 | New `"telephony"` category + display name. | §4.2 |
| **N-7** Tool should inherit `APIKeyConnectorTool` | 🟡 | Adopted (credentials/error handling from the base). | §4 Flow A, §7 |
| **N-8** HITL confirm mechanism unspecified | 🟡 | Manifest-driven tool-level destructive-confirm (pipeline + ReAct); `HitlMessages` template ×6. | §7, §11.7 |
| **N-14** Connector lifecycle (agent cleanup, in-flight calls) | 🟡 | Best-effort agent deletion; stale reaper handles in-flight. | §4.2, §12 |
| **N-16** Test gaps | 🟡 | Foreign-event filter, activation flow, no-cost assertion added. | §13 |

**v3:** R-1 per-user connector (full BYO; replaces single-tenant D-7); R-2 cost
tracking on the audio pattern (**superseded by v4 D-9**).

**v2 — first expert review F1–F16:** F1 tool-less return; F2 single archive; F3
resolved natively by per-user numbers; F4 → D-8; F5 named egress; F6 eliminated;
F7 `call_id` reconciliation; F8 date-window/language; F9 pre-fetch after confirm;
F10 `phone_call` title; F11 → superseded by D-9; F12 unique-active index; F13
lifecycle; F14 webhook hardening; F15 typed JSONB; F16 tests.

---

## 17. Appendix — ElevenLabs/Twilio Setup Runbook (per user)

Verified against the current **ElevenAgents** platform (2026). This is the basis
for the user-facing activation guide (6 languages) and the wizard's guided steps.

**A. Accounts**
1. ElevenLabs account with a **paid plan** (Starter or above recommended — Agents
   minutes are bundled per plan; Free ≈ 15 min, testing only).
2. Twilio account (or a SIP provider — Telnyx/didlogic; then provider="sip_trunk").

**B. Twilio — get a number**
3. Twilio Console → Phone Numbers → **Buy a Number** (France, Voice capability,
   ~1 €/month). ⚠ **FR regulatory bundle**: French numbers require an approved
   identity/address bundle before activation (hours to days) — the single
   slowest step; start it first.
4. Copy the **Account SID** and **Auth Token** (Console dashboard).

**C. ElevenLabs — import the number (UI)**
5. ElevenAgents dashboard → **Phone Numbers** tab → import from Twilio: Label,
   phone number (E.164), Account SID, Auth Token. ElevenLabs **auto-configures
   the Twilio side** and detects Outbound/Inbound capability. No agent
   assignment needed for outbound-only use.

**D. ElevenLabs — API key**
6. Create an API key (scoped to Agents features where available). This is the
   key pasted into the LIA connector wizard.

**E. ElevenLabs — post-call webhook (UI-only, workspace-wide)**
7. `elevenlabs.io/app/agents/settings` → create a **post_call_transcription**
   webhook pointing to `https://<lia-host>/api/v1/telephony/webhook`.
   **Do not enable** the audio webhook (D-8). Copy the generated **HMAC secret**.

**F. LIA — connector wizard (automated from here)**
8. Mes Connecteurs → Téléphonie: paste the API key (validated) → pick the number
   (listed via `GET /v1/convai/phone-numbers`) → LIA auto-creates the guardrailed
   agent (`POST /v1/convai/agents/create`: user language, disclosure first
   message, voicemail detection, duration caps) → paste the webhook secret →
   connector ACTIVE.
9. **Do not hand-edit the LIA agent** in the ElevenLabs dashboard (LIA re-asserts
   its config before each call anyway — §6.1).

**G. Validate**
10. Ask LIA to call your own mobile with a trivial objective; verify the HITL
    confirm, the disclosure first message, and the post-call summary in the
    conversation.
