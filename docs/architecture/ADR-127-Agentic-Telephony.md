# ADR-127: Agentic Telephony — Per-User Connector, Read-Only Capability Model, No Cost Metering

**Status**: ✅ IMPLEMENTED (2026-07-13, à blanc — vendor E2E gated on the P2.0 spike)
**Author**: Claude Code (Opus 4.8)
**Related**: [ADR-070] ReAct Execution Mode (draft/HITL flow reused), [ADR-085](ADR-085-Draft-Display-Registry.md) (boot-time completeness assert pattern reused for the new draft type), [ADR-117] Background Chat Runs (fire-and-forget + own-session background task precedent), spec `docs/superpowers/specs/2026-07-07-telephony-agentic-calls-design.md` (v5, decisions D-1…D-9), technical doc `docs/technical/TELEPHONY.md`.

## Context

Users want LIA to **place an outbound phone call on their behalf**, hold a
goal-directed conversation with a third party (e.g. check a friend's
availability), and get an **asynchronous summary + optional follow-up** back in
the chat — without blocking the assistant during the call. The vendor is
ElevenLabs Agents (ElevenAgents), which dials via Twilio/SIP and posts a
signed webhook after the call.

Three properties made this non-trivial and shaped the design:

1. **Third-party data protection.** The agent talks to someone who never
   consented to LIA. During the call it must be **read-only** and may share
   **free/busy availability only** — never meeting titles, attendees, locations,
   or any other personal detail. This has to be a *capability* guarantee, not a
   prompt request.
2. **Per-user ownership.** Telephony is BYO: each user brings their own
   ElevenLabs API key + imported number. It must be modeled like every other
   entry in *Préférences → Mes Connecteurs*, not a global server credential.
3. **Cost.** Vendor call minutes are billed to the user's own accounts — LIA
   must **not** meter them.

## Decision

Ship telephony as a **per-user connector** feeding the existing draft/HITL and
proactive-notification machinery, with the following load-bearing decisions
(spec D-1…D-9):

- **D-7 — Per-user connector (full BYO).** `ConnectorType.ELEVENLABS_TELEPHONY`
  reuses `ConnectorService.activate_api_key_connector`: the API key **and** the
  post-call webhook HMAC secret live encrypted in `credentials_encrypted`
  (`api_key` / `api_secret`); only non-secret ids (`agent_id`,
  `agent_phone_number_id`, caller display) go in `connector_metadata` (JSONB).
  Activation provisions a LIA-controlled, guardrailed agent in the user's
  workspace.
- **Defense by capability, not by prompt.** Availability is a **pre-fetched,
  minimized free/busy projection** (`availability.py`): the calendar is read
  with `fields=["start","end"]` and projected to busy time ranges only — meeting
  details are never even fetched. The projection is injected as the
  `{{availability_summary}}` dynamic variable; the agent physically cannot leak
  what it was never given. There is no live gateway (explicitly out of scope for
  v1).
- **D-4 / V-1 — Draft-based HITL.** `DraftType.PHONE_CALL` flows through the
  existing `draft_critique` → `draft_executor` path (like create_event /
  cancel_reminder): the user reviews callee + objective and confirms before LIA
  dials. `hitl_required=False` on the manifest (draft tools must not set the
  ReAct pre-execution interrupt — it is unrendered and hangs). A boot-time
  completeness assert (ADR-085 pattern) refuses to start if the new type lacks a
  display config / preview renderer.
- **D-2 — Tool-less bounded synthesis return.** The post-call webhook triggers a
  single **tool-less** LLM call (`telephony_synthesis` LLM type + versioned
  prompt, structured output) producing a factual `summary` + a first-person
  `proposal_text`, delivered via `NotificationDispatcher`. The agent has no
  domain tools on the return path.
- **D-8 — No recording, transcript never persisted.** `call_recording_enabled=false`
  at the vendor API. Only the `summary` + a minimized typed `StructuredCallData`
  (agreed / proposed_datetime / location / notes) are stored; the raw transcript
  is used for synthesis then discarded. A daily retention reaper clears
  `summary`/`structured_data` past their TTL.
- **D-9 — No LIA-side cost metering.** Vendor minutes are the user's own cost;
  `call_seconds` is stored as factual metadata, never converted to money. (The
  LIA-side synthesis LLM call *is* tracked like every other proactive call — see
  Consequences.)
- **§6.4 — Webhook security (per-user HMAC).** The webhook is unauthenticated
  and the HMAC secret is per-connector, so the order is deliberate:
  foreign-filter (`call_id` → `PhoneCall` → connector) **before** verifying the
  signature. Unknown/foreign/malformed → 200 + `telephony_webhook_ignored_total`
  (no PII logged); a **known** call with a forged signature → 4xx.

## Consequences

- **Crash-safe reconciliation (transaction scoping).** `initiate_call` commits
  the `dialing` row **before** dialing and never holds a DB transaction across
  the two external HTTP calls (calendar pre-fetch + vendor dial). The `call_id`
  is sent to the vendor as a dynamic variable, so the row must exist before the
  call is placed — otherwise a crash after dialing would orphan the call and its
  return would be lost. One-active-call-per-user is enforced by a partial unique
  index (F12); exactly-once webhook processing is an atomic conditional UPDATE.
- **Observability.** Prometheus metrics `telephony_calls_total{status}`,
  `telephony_call_duration_seconds`, `telephony_webhook_ignored_total{reason}`.
  The synthesis LLM spend **is** tracked via `track_proactive_tokens`
  (consistent with briefing/heartbeat) — D-9's "no metering" applies to vendor
  minutes, not to LIA's own LLM cost. Logs carry IDs/counts only; no name,
  phone, summary or collected value at INFO/WARNING.
- **i18n.** All telephony backend strings live in `core/i18n_telephony.py`
  (6 languages); frontend keys under `settings.connectors.telephony.*`.
- **Spike owed (P2.0).** Written à blanc against the documented ElevenLabs API.
  The exact request/response shapes — webhook signature header, post-call payload
  field paths, the create-agent prompt/data-collection config path — are marked
  `spike:` in the code and must be confirmed against a real ElevenLabs + Twilio
  account before go-live. All external-payload reads are defensive (a shape
  drift degrades gracefully, never crashes).

## Alternatives considered

- **Live availability gateway** (agent calls back into LIA mid-call): rejected
  for v1 — a live inbound surface during an untrusted call is a much larger
  attack surface than a pre-fetched, minimized snapshot.
- **Global telephony credential**: rejected — telephony is inherently per-user
  (own number, own billing), and a shared key would break the connector model
  and cost attribution.
- **Sharing availability as full events**: rejected — free/busy is the minimum
  that satisfies the use case without exposing meeting details to a third party.
