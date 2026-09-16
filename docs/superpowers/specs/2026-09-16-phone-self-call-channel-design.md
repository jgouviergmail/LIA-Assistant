# The phone as a channel: LIA calls the person, and the call becomes a turn — design

**Date:** 2026-09-16 · **Status:** approved in principle by the owner (chat,
2026-09-16), pending review of this document · **ADR:** ADR-290 (to write in
lot 6) · **Amends:** ADR-127 (D-2, D-4, D-5, D-8 for the owner's own calls),
ADR-174, ADR-263 (a new out-of-turn surface), ADR-276 (the out-of-turn engine
gains an attended mode)

## Need

Today LIA phones a **third party** on the person's behalf: the tool returns a
draft the person confirms, a guardrailed vendor agent pursues a read-only
mandate, and the return comes back as a **notification**. Nothing is learned
from it and nothing is executed: the debrief's tasks and reminders leave as
`?intent=` links the person clicks by hand (ADR-174).

The owner wants the phone to become a **channel of the conversation**, at
parity with the chat and Telegram:

1. when the callee is the person themselves, **no confirmation card** — the
   person who would confirm is the person who picks up;
2. the call is a **conversation with the assistant**: it knows what the chat
   knows, relaunches, asks for precisions, and may look things up;
3. the call's outcome is **treated as a message the person sent**: memory,
   interests, open loops, journal, psyche and recurrence extraction; plans,
   drafts of e-mails, events, tasks and reminders — everything a typed message
   triggers.

Owner decisions taken in the design conversation:

- **Q1 — identity is declared in a settings section**, so the exception rests
  on a fact the person asserted about themselves, never on a name match;
- **Q2 — outbound only**: LIA calls the person; the person never calls LIA;
- **Q3 — the drafts the relayed turn produces are confirmed in the chat** (a
  push tells the person); voice confirmation is a later programme;
- **the same vendor agent serves both mandates** (voice and model settings
  stay in one place);
- **the owner's own call gets the rich context of the chat**, beyond the
  free/busy projection, **and tools where feasible**.

## What exists, verified on the code

| Piece | Fact | Where |
|---|---|---|
| Tool | One tool, `mutation_policy="draft"`: the draft IS the confirmation; the draft executor dials | `agents/telephony/catalogue_manifests.py`, `agents/tools/telephony_tools.py` |
| Gate | `draft` is refused when the turn's source is `scheduled` and nobody carries the question — so « call me every morning » is impossible today | `agents/effects/gate.py` |
| Vendor agent | One agent per connector, third-party prompt baked at activation, lazily re-PATCHed on fingerprint drift; per-call data is `dynamic_variables` only | `telephony/agent_prompt.py`, `telephony/client.py` |
| Vendor API | `conversation_initiation_client_data.conversation_config_override` carries `agent.prompt.prompt`, `agent.first_message`, `agent.language`, `agent.prompt.tool_ids`; the permission lives in `platform_settings.overrides`; webhook tools are workspace objects created through the tools API | ElevenLabs Python SDK types (Context7, 2026-09-16) |
| Return | webhook → encrypted inbox → tool-less synthesis → `mark_completed` exactly once → notification outbox → notification | `telephony/return_synthesis.py`, `telephony/repository.py` |
| Learning | The six post-response extractions run only on a turn whose runtime context says `is_automated_source=False`; a notification never reaches `response_node` | `agents/nodes/post_response_extractions.py` |
| Out-of-turn engine | `stream_instruction` hard-codes `is_automated_source=True`, `auto_approve_plan=True`, passes no memory/journal/psyche flag | `infrastructure/scheduler/out_of_turn_run.py` |
| Identity | `users` has no phone column; the encrypted profile pattern is `home_location_encrypted` (set/clear endpoints, scrubbed at deletion) | `users/models.py`, `users/service.py`, `users/account_deletion_service.py` |
| Transcript | Cut at 4 000 characters before synthesis (`_extract_transcript_text`) — sized for a third-party call | `telephony/return_synthesis.py` |
| HITL | A pending question lives 3 600 s in Redis (`hitl_pending_data_ttl_seconds`) | `core/constants.py` |
| In-app voice | A duplex voice mode already exists (`/voice/ws/audio`); the phone's own value is that LIA can INITIATE, that it needs no app, and that it can be scheduled | `domains/voice/router.py` |

Two pre-existing defects found on the way, fixed inside the programme:

- `agents/effects/direct_client_callers.py` classifies `telephony/availability.py`
  as « reads the deployment's own configuration, never the person's data ». It
  opens the person's **calendar** through `ClientRegistry`, from the draft
  executor, and records no consultation.
- The `telephony_agent` manifest description states « every call is confirmed
  by the user ». After this programme that is false for the owner's own call;
  a manifest states what the code enforces (ADR-284).

## Approach

**One tool per mandate, one agent per connector, one turn per call.**

- A **second tool, `call_me`**, `mutation_policy="reversible"` with a written
  reason. It targets the person's **verified** number by construction, so it
  has no `contact` parameter, needs no draft, passes the gate in a routine and
  in ReAct, and is recorded in the effect register as an action claimed then
  settled. A branch « sometimes I act without a draft » inside a `draft` tool
  would lie to the gate and leave no ledger row.
- The **same vendor agent** serves both mandates through a per-call
  `conversation_config_override` (prompt, first message, tool ids). LIA sends
  the override permission in the agent config it already owns, so the
  fingerprint covers it and the lazy re-sync applies it to existing
  connectors. **For an owner call the sync is mandatory**: a failed PATCH
  refuses the call (`agent_sync_failed`) rather than serving the owner the
  third-party mandate.
- **The identity is a verified number.** The person declares their number in
  a new settings section; LIA calls it once, speaks a code, the person types
  it back. Only a verified number can be called without confirmation, and only
  a verified number receives the rich context. A typo would otherwise send the
  owner's context to a stranger.
- **The call ends in a turn.** The post-call synthesis produces a first-person
  **relay message** (what the person would have typed), which runs through
  `stream_chat_response` as the person's own message: extractions on, drafts
  asked in the chat, archived visible with a phone-origin stamp. Every failure
  or refusal falls back to the existing notification path, with a sentence
  that says why.
- **Live tools come last, behind a flag**: read-only tools attached per call
  through `tool_ids`, calling back a LIA endpoint bounded to one active owner
  call. They answer « what do I have tomorrow? » during the call; mutations
  stay post-call.

Rejected: a second vendor agent (the owner wants one place for voice/model
settings; the override chain covers every difference); recognising the owner
from a same-name contact card (a name is not an identity assertion); the
address-book « me » profile as the number's source (a second authority beside
the verified one, and Apple has no such card); running the relay as an
unattended run (extractions would be skipped by construction); confirming the
relayed drafts by voice (a later programme, Q3).

## Backend

### Lot 1 — the person's number, verified

- **`users` columns**: `phone_number_encrypted` (Text, nullable, Fernet like
  `home_location_encrypted`), `phone_number_verified_at` (timestamptz,
  nullable), `phone_rich_context_enabled` (bool, NOT NULL, default true).
  Scrubbed at account deletion beside `home_location_encrypted`. One migration.
- **`telephony/phone_numbers.py`** (new): `normalize_phone`, `same_line`,
  `number_search_variants`, extracted from `agents/tools/telephony_tools.py`
  (which imports them). One implementation of « is this the same line », read
  by the tool, the identity service and the tests.
- **`telephony/identity.py`** (new, `TelephonyIdentityService`):
  `get_identity(user_id)` → masked number, `verified`, `rich_context_enabled`;
  `set_number(user_id, raw)` → E.164 or a typed validation error, resets
  `verified_at`; `clear_number`; `start_verification(user_id)` → guards
  (connector active, number declared, no active call), draws a numeric code
  (`secrets`, `TELEPHONY_VERIFICATION_CODE_LENGTH`), stores it under
  `telephony_verify:{user_id}` (family `USER_RUNTIME`, TTL
  `TELEPHONY_VERIFICATION_CODE_TTL_SECONDS`) with an attempts key, and places
  a `VERIFICATION` call (below) whose mandate is « say the code twice, ask the
  person to type it in the app, end »; `confirm_verification(user_id, code)` →
  constant-time compare, attempts capped
  (`TELEPHONY_VERIFICATION_MAX_ATTEMPTS`), sets `verified_at`, deletes the key.
- **Routes** (`telephony/router.py`, behind the `TELEPHONY` capability):
  `GET /telephony/identity`, `PUT /telephony/identity/number`,
  `DELETE /telephony/identity/number`, `PATCH /telephony/identity`
  (`rich_context_enabled`), `POST /telephony/identity/verify`,
  `POST /telephony/identity/confirm`. Centralised raisers in
  `telephony/errors.py` (the bookmarks precedent: `core/exceptions.py` is
  size-frozen).
- **Key family**: `telephony_verify` and `telephony_verify_attempts` declared
  `USER_RUNTIME` in `infrastructure/cache/key_families.py`; constants in
  `core/constants.py`.

### Lot 2 — one agent, two mandates

- **`phone_calls.call_kind`**: `CallKind {THIRD_PARTY, SELF, VERIFICATION}`,
  `Enum(native_enum=False)` (the NAME is stored), NOT NULL, server default
  `THIRD_PARTY`. One migration; the replay check compares comments, so the
  column comment mirrors the migration exactly.
- **`telephony/mandates.py`** (new): one `CallMandate` per kind — prompt file,
  first-message table, data-collection expectations, maximum duration
  (`TELEPHONY_SELF_CALL_MAX_DURATION_SECONDS`, default 900), whether the rich
  context is injected, whether tools may be attached. Boot completeness assert
  over `CallKind` (ADR-085).
- **Prompts** (`agents/prompts/v1/`, loaded path-only through
  `telephony/prompts/loader.py` as today): `telephony_self_call_system_prompt.txt`
  (identity check at pickup before anything else; the person's assistant, warm,
  in the account's tone; collects requests, relaunches, asks one precision at a
  time, echoes critical data, requires absolute dates; **never promises a live
  action** unless a tool is attached — « I take care of it right after our
  call, you will see it in the chat »; shares nothing until the owner is
  confirmed; ends politely when the person is not the owner) and
  `telephony_verification_prompt.txt` (the code, twice, digit by digit in words;
  nothing else). Both carry `{{...}}` markers only (never `.format`), and the
  placeholder guard learns the two files and their producer.
- **Agent config**: `_agent_config_body` sends `platform_settings.overrides`
  allowing `agent.prompt.prompt`, `agent.first_message`, `agent.language` and
  `agent.prompt.tool_ids`; the fingerprint includes it, so every existing
  connector is re-synced at its next call. `initiate_outbound_call` gains
  `conversation_config_override: dict | None`.
- **`TelephonyService.initiate_call(kind=...)`**: the `SELF` and
  `VERIFICATION` kinds require a declared number (`SELF`: verified), build the
  override from the mandate, make the sync **mandatory** (a failed PATCH →
  `InitiateCallResult(status="agent_sync_failed")`, a new non-placed status
  with its phrase in the six languages), skip the availability pre-fetch for
  `VERIFICATION`, and pass the mandate's maximum duration.
- **Webhook**: unchanged authentication (same agent id). `process_completed_call`
  dispatches on `call_kind`: `THIRD_PARTY` → today's path; `VERIFICATION` →
  `mark_completed` with no synthesis, no notification; `SELF` → lot 4.
- **Consultation recording**: a `ConsultationSurface("phone_call", prefix
  "phone_call:", source "user")` in `domains/shared/consultation_surfaces.py`,
  with the availability read as its first section (`availability` → `event`)
  recorded from `initiate_call`; `CONSULTATION_RECORDERS["phone_call"]` points
  at `telephony/service.py`; the wrong `NOT_A_CAPABILITY_READ` entry for
  `availability.py` is replaced by the truthful one (it opens the calendar; the
  service records it).

### Lot 3 — the `call_me` tool

- **Manifest** (`agents/telephony/catalogue_manifests.py`): name `call_me`,
  agent `telephony_agent`, `mutation_policy="reversible"`,
  `mutation_policy_reason="The callee is the account holder themselves, on a number they verified: the person who would confirm is the person who picks up, and hanging up undoes it."`,
  parameters `objective` (required, `max_length` 500, absolute dates) and
  `date_window` (optional, unused by the owner mandate but kept for parity),
  `hitl_required=False`, `data_classification="SENSITIVE"`,
  `semantic_keywords` disjoint from the third-party tool (« call me », « phone
  me to go over », « ring me »). The agent manifest description drops « every
  call is confirmed » and states the two mandates.
- **Tool** (`agents/tools/telephony_tools.py` stays under its cap; the owner
  path lives in `agents/tools/telephony_self_tools.py`): guards (connector
  active, capability, verified number) → `initiate_call(kind=SELF)` → the
  async-safe phrase « I'm calling you now » or the localized non-placed phrase
  through the shared `_STATUS_TO_PHRASE` (extended with `agent_sync_failed`,
  `number_not_verified`). Rate-limited by the same hourly setting.
- **Third-party tool** given the verified number: returns a technical-English
  failure (« this is the user's own verified number; use call_me »), so the
  planner replans; a `@connector_tool` never dials.
- **Routine and ReAct**: a routine « call me every morning at 8 » is a plan
  whose tool passes the gate (`reversible` is LEDGERED, never refused
  unattended); a characterization test proves it end to end on the routine
  executor.

### Lot 4 — the relay: the call becomes a turn

- **`telephony/self_call_context.py`** (new): assembles the `{{user_context}}`
  dynamic variable at dial time, deterministic, bounded by
  `TELEPHONY_SELF_CONTEXT_MAX_TOKENS` (default 2 500), in the person's language
  and timezone, sections in priority order and each cut at item boundaries with
  the cut stated: personality instruction
  (`PersonalityService.get_prompt_instruction_for_user`), psychological
  profile (`build_psychological_profile` with the objective as query), today's
  and tomorrow's agenda with titles (the owner's own data: full detail is
  allowed, unlike the third-party projection), pending reminders
  (`ReminderService.list_pending_for_user`), open loops, workboard tickets
  waiting for the person (`WorkboardRepository.list_board`), the last N visible
  exchanges of the conversation (the reader declares `VISIBLE_ONLY` in
  `conversations/message_readers.py`). Every section opened is recorded on the
  `phone_call` surface; a cache hit records nothing; a failed source records
  `failed`. Skipped entirely when `phone_rich_context_enabled` is false: the
  mandate then gets the free/busy projection only.
- **`telephony/self_call_relay.py`** (new): `synthesize_relay` through
  `get_structured_output_with_retry` (LLM type `telephony_synthesis` reused;
  prompt `telephony_self_call_relay_prompt.txt`; schema `SelfCallRelay`:
  `owner_confirmed: bool`, `relay_message: str` — first person, the person's
  requests and facts as they would have typed them, absolute dates, nothing
  invented, empty when nothing is to relay — and `summary: str`, third person,
  persisted). The transcript is projected under
  `TELEPHONY_RELAY_TRANSCRIPT_MAX_TOKENS` (default 6 000) at turn boundaries
  with the cut stated, replacing the 4 000-character cut for this kind. Spend
  through `track_proactive_tokens(task_type="phone_call", source="user")`;
  `LLM_SPEND_ROADS` declares the module `ACCOUNTED`.
- **The relay runner** (`telephony/relay_runner.py`, new, driven from the
  webhook's background task like the synthesis): reads the person's
  preferences through `resolve_run_context` (extended with `memory_enabled`,
  `journals_enabled`, `psyche_enabled`, `execution_mode`), probes
  `conversation_has_pending_hitl`, takes `active_run_lease` with bounded
  retries (`TELEPHONY_RELAY_BUSY_RETRIES` × `TELEPHONY_RELAY_BUSY_DELAY_SECONDS`),
  then `stream_instruction(StreamRequest(..., spoken_by_person=True,
  origin=RunOrigin(kind="phone_call", ticket_id=<call id>, run_id=..., hidden=False)))`.
- **`StreamRequest.spoken_by_person`** (new, default False): `_one_attempt`
  then passes `is_automated_source=False`, `auto_approve_plan=False`, the
  three preference flags and the person's chat `execution_mode`. Unattended
  callers are untouched.
- **`RunOrigin.hidden`** (new, default True): `with_hidden_stamp` becomes
  `with_origin_stamp`, writing `FIELD_HIDDEN` only when the origin is hidden;
  a phone-origin row carries `{"phone_call": {"ticket_id", "run_id"}}` and
  stays VISIBLE — the three rows of the turn (the relayed message, the answer,
  the question LIA asked instead) all carry it.
- **Outcomes** (`RunOutcome`): `SUCCESS` → the answer is in the chat;
  `WAITING` → the drafts are in the chat, a push says how many
  (`NotificationDispatcher(archive_enabled=False)`); `QUOTA_BLOCKED`,
  `FAILED`, pending question, busy thread, `owner_confirmed=False`, empty
  relay, voicemail or no answer → the **existing notification path** with the
  debrief-era summary and one localized sentence naming the reason. Every
  outcome counts `telephony_relay_total{outcome}`.
- **Outbox**: `mark_completed` arms the row with `notification_status =
  RELAYING` (new member; partial index on `completed_at WHERE
  notification_status = 'RELAYING'`) and the fallback payload; the relay
  runner flips it to `DELIVERED` on success and to `PENDING` on any fallback
  (the notification reaper then delivers it); a `RELAYING` row older than
  `TELEPHONY_RELAY_MAX_AGE_MINUTES` (a crash mid-relay) is flipped to
  `PENDING` by the notification reaper — a rare duplicate is preferred over a
  lost return, the T1 doctrine.

### Lot 7 — live read-only tools (flagged, after a spike)

- **Vendor side**: at activation and on fingerprint drift, LIA creates one
  workspace tool per allow-listed capability (`type: webhook`, POST
  `<public host>/api/v1/telephony/tools/<name>`, header carrying a workspace
  secret bound to the connector's `api_secret`, body parameters: `call_id`
  bound to the dynamic variable, plus the LLM-provided arguments,
  `response_timeout_secs` = `TELEPHONY_LIVE_TOOL_TIMEOUT_SECONDS`), stores the
  ids in `connector_metadata.live_tool_ids`, and attaches them per owner call
  through the `tool_ids` override. Deleted with the agent at deactivation.
- **LIA side**: `POST /telephony/tools/{name}` — resolve `call_id` → a `SELF`
  row that is active and younger than the mandate's maximum duration →
  connector → constant-time secret check → per-call rate limit → the tool must
  be in `LIVE_TOOL_ALLOWLIST` (a code constant, boot-guarded: every member
  declares `mutation_policy="read"`, and is offered only when its capability is
  on) → run `tool.coroutine(**args)` under a `LiaRuntimeContext` for the
  person, inside `treatment_recorder(run_id=<call run>)` and a
  `TrackingContext` so a digest's spend reaches the ledger → project the result
  under `TELEPHONY_LIVE_TOOL_RESULT_MAX_TOKENS` as plain text. No PII on any
  log path; `telephony_live_tool_calls_total{tool,outcome}` and a duration
  histogram, both drawn on the telephony dashboard row.
- **Flag**: `TELEPHONY_LIVE_TOOLS_ENABLED`, default false, in every `.env`
  including the four demo files. The owner prompt says « you may look this up »
  only when tools are attached (a prompt promises what the turn can run).
- Security invariant 7 in `docs/technical/TELEPHONY.md`: a public endpoint that
  answers only for an active owner call, with the connector's own secret, in
  read-only, behind a flag.

## Frontend

- **Settings section `telephony-identity`** (« Téléphonie · Mon identité »),
  declared in `lib/settings-sections.ts` and `settings-section-registry.tsx`
  next to `telephony-calls`, feature-gated like it, so ADR-277's shortcut
  vocabulary follows: the number (masked, `inputmode="tel"`,
  `autocomplete="tel"`, one error line, E.164 hint from
  `TELEPHONY_DEFAULT_COUNTRY_CODE`), the verification state with « Vérifier
  par un appel » and the code field, the « Contexte enrichi au téléphone »
  switch (36×20 px touch target rule). Hook `useTelephonyIdentity` on
  `useApiQuery` / `useApiMutation`.
- **Chat**: a user bubble whose metadata carries `phone_call` wears a phone
  badge with a translated accessible name (« Dit par téléphone »); the answer
  and the HITL cards are the ordinary ones.
- **Calls list** (`TelephonyCallsSection`): the kind (« Toi », « Vérification »)
  and the relay outcome beside the status; `TelephonyCallSummary` gains
  `call_kind` and `relay_outcome`, never the number.
- **`ActiveCallBanner`**: « LIA t'appelle » for an owner call.
- Six languages, strict key parity, no new layout.

## Costs, quotas, registers

| Poste | Per owner call of five minutes |
|---|---|
| Context pack | no model call; one embedding query for the profile |
| Relay synthesis | ~3 000 tokens in, ~600 out |
| Relay turn | that of a typed message of 200 to 300 words |
| Vendor minutes and vendor LLM | the person's own accounts (D-9, unchanged) |

- The relay turn is a request-path turn: both ceilings apply, a refusal
  arrives as the stream's own error chunk and becomes a fallback.
- Registers: one **effect** row per owner call (claimed before the dial,
  settled from `InitiateCallResult`); one **decision** row per relayed turn,
  source `user`; **consultations** for the context pack and the availability
  read on the `phone_call` surface, and for every tool the turn or a live
  tool runs, through the gate.
- Privacy: the prompt override carries the context pack to the vendor and its
  model provider for the length of the call; the transcript is not recorded
  and rests encrypted only for the synthesis window (D-8 unchanged); the relay
  message is a chat message and lives like one. ADR-290 states this as a
  conscious extension, conditioned on the verified number and the switch.

## Configuration (every knob in `core/config/telephony.py`, `.env.example`, `.env.prod.example`, the four demo files)

`TELEPHONY_SELF_CALL_MAX_DURATION_SECONDS` 900 ·
`TELEPHONY_SELF_CONTEXT_MAX_TOKENS` 2500 ·
`TELEPHONY_RELAY_TRANSCRIPT_MAX_TOKENS` 6000 ·
`TELEPHONY_RELAY_TIMEOUT_SECONDS` 240 · `TELEPHONY_RELAY_BUSY_RETRIES` 3 ·
`TELEPHONY_RELAY_BUSY_DELAY_SECONDS` 30 · `TELEPHONY_RELAY_MAX_AGE_MINUTES` 15 ·
`TELEPHONY_VERIFICATION_CODE_LENGTH` 4 · `TELEPHONY_VERIFICATION_CODE_TTL_SECONDS`
600 · `TELEPHONY_VERIFICATION_MAX_ATTEMPTS` 5 · `TELEPHONY_LIVE_TOOLS_ENABLED`
false · `TELEPHONY_LIVE_TOOL_TIMEOUT_SECONDS` 20 ·
`TELEPHONY_LIVE_TOOL_RESULT_MAX_TOKENS` 800. Defaults in `core/constants.py`;
tests read them from `settings`.

## Edge cases (each a test)

- Number declared, not verified → `call_me` refuses with the settings path.
- Verification: wrong code ×N → locked until TTL; code expired; a second
  `verify` while a call is active → `already_active`; number changed → verified
  reset.
- Owner call: no answer, voicemail, someone else picks up
  (`owner_confirmed=False`), the person says « nothing, forget it » (empty
  relay), hang-up in the first seconds (empty transcript), a ten-minute
  monologue (projection cut stated), the vendor refuses the override
  (`agent_sync_failed`, nothing dialed).
- Relay: pending question on the thread; thread busy for longer than the
  retries; quota refused; provider failure; crash mid-relay (reaper flips to
  PENDING); duplicated webhook (exactly-once unchanged); the relay produces
  three drafts (ADR-288 sequence, one push); the person answers a draft after
  the 3 600 s TTL (stale card, the existing behaviour).
- Third-party path: byte-for-byte unchanged (characterization before lot 2).
- Live tools (lot 7): unknown tool, mutation tool, expired call, wrong secret,
  a capability switched off mid-call, a tool slower than the vendor timeout.

## Tests

- **Unit**: identity service, phone helpers, mandates completeness, override
  body, mandatory sync, `call_me` outcomes, gate behaviour per policy and
  source, context pack budget and recording, relay schema and projection,
  relay runner outcomes, outbox transitions, archive stamp, webhook dispatch on
  kind, frontend hooks and components, i18n parity, every existing guard
  (mutation-policy completeness, `hitl_required` consistency, spend roads,
  readers, key families, metric coverage, file size, complexity, placeholders).
- **Integration (PostgreSQL)**: the two migrations and their replay; `call_kind`
  and `RELAYING` transitions with two workers; the scrub at deletion.
- **Characterization**: the third-party return path; the routine executor
  reaching `call_me`.
- **E2E hermetic**: the identity section; a conversation showing a phone-origin
  bubble then a confirmable draft card.
- **Docker dev simulations** (before delivery, measured): a replayed webhook
  with a real five-minute transcript; a real owner call; a real verification
  call; a pending question then a webhook; quota exhausted then a webhook; a
  crash injected mid-relay then a reaper pass.

## Lots

0. **Vendor spike** on the owner's account (no product code): the override
   permission field and its PATCH; an override with dynamic variables inside
   the prompt; the post-call payload of a five-minute owner call; a webhook
   tool with a dynamic-variable parameter and a workspace secret; `tool_ids`
   attached per call.
1. The number, verified (backend + settings section).
2. One agent, two mandates (+ the two pre-existing defects).
3. The `call_me` tool (+ routine characterization).
4. The relay (+ engine extensions, outbox, stamp, metrics, dashboard).
5. Frontend surfaces beyond the section (chat badge, calls list, banner).
6. Documentation and gates: ADR-290, TELEPHONY.md, ADR-127 amendment note,
   CLAUDE.md pointer, how/why guides ×6, `.env` ×6, `task lint`,
   `test:backend:unit:fast`, `test:frontend`, `db:migrate:replay-check`,
   `ci:fast`.
7. Live read-only tools (flagged), after lot 0's answers.

Lot 1 starts without lot 0; lots 2, 4 and 7 read its answers.
