# Live mode, wave 4 — a third provider (ElevenLabs) and a DIRECT session

**Date**: 2026-09-19 · **Status**: arbitrated with the owner (« faire simple, factoriser,
générique »), in execution · **Amends**: the wave-2 design (`2026-09-19-live-wave2-design.md`),
ADR-299, ADR-300, ADR-290 (the phone's read-only tools become a VOICE seam)

## 1. Intent

Two things, one rule: nothing the phone already knows is written a second time.

1. **ElevenLabs Conversational AI joins as a third live provider.** The person selects an
   AGENT of their own ElevenLabs account; everything the agent *sounds like* stays on the
   portal (ADR-290's doctrine, owner decision); LIA sends only the prompt (a per-conversation
   override) and attaches its own tools to the agent by fingerprint, the way the phone does.
2. **A DIRECT session** (« Session live directe (<brand>) », third entry of the header's voice
   menu): the voice model holds LIA's READ-ONLY tools itself — the phone's derived set (ADR-290
   lot 8), voice-projected — and never delegates to the chat. No mutation, no delegation, no
   HITL: the phone's own line, in the browser. **Amended 2026-09-19 (evening, owner
   request)**: a direct session RECORDS NOTHING of the exchange — no `live_turn` row, no
   learning pass, a card without counts — and its banner says so; see B5.

## 2. Arbitrated decisions

| # | Decision |
|---|---|
| B1 | **The owner's premises, corrected in writing** (kept in the ADR): a direct session gains latency (no graph run per lookup) and NOTHING else — Gemini re-bills the WHOLE context every turn, so tool declarations and tool results in the live context COST more, not less; transcription is ~0.1 % of a turn's cost; HITL, mutations, extractions and registers all come free with delegation. Hence: direct = read-only, extractions by the existing end-of-session learning pass. |
| B2 | **One tool door for every live wire**: `POST /live/sessions/{id}/tools` (the account's session cookie, the record's run id). The browser receives the provider's function call (Gemini `toolCall`, ElevenLabs `client_tool_call`), posts it, hands the text back (`toolResponse`, `client_tool_result`). The server side is the phone's `run_live_tool`, generalised to a `VoiceToolHost` (surface, run id, spend node) — the phone stays on `phone_call`, the direct session on `live_session`. No webhook, no derived token: the session cookie is the auth, as for the delegation. |
| B3 | **The tool set is the phone's rule** (`derive_live_tool_specs`: search / explicit `read`, not `system`, a voice domain, speakable required parameters) plus the native `recall_memories`; the person's own switches (`users.phone_disabled_domains`) apply to their voice sessions too — one preference for « what my voice may read », relabelled. |
| B4 | **The direct mandate is the phone's owner mandate**, rendered for the browser: the same prompt file family (`telephony/prompts`), the same context block under a token budget (`self_call_context.build_owner_context`), the personality, the inner state, the read-only rules and « I cannot act in this mode — say it in the chat or a delegated session ». |
| B5 | **Extractions — NONE, by construction** (amended 2026-09-19 evening, owner request: « un petit bandeau … pour indiquer à l'utilisateur que les informations échangées ne sont pas enregistrées par LIA (mémoire, centres d'intérêts, etc.) »). The first simplification kept the archived `live_turn` rows and the end-of-session learning pass; the sentence the owner asked for was false under it, and doubly so: the rows sat in the thread, and the next written turn injects them into the graph state whose extractors read them. A banner states what the code enforces (ADR-284), so: `archive_turn` refuses a direct record (409 `direct_not_archived`), the browser never posts a turn, `schedule_live_learning` is skipped on `mode == "direct"`, the card's body counts no exchange (`summary_body_direct`), the captions live in the banner alone. The registers (ADR-263) still record the session and the capabilities read — never a word said. The relay turn (`self_call_relay.synthesize_relay`) stays REJECTED. ADR-300 amendment 15. |
| B6 | **Capabilities, never provider ids**: `LiveModelCapabilities.direct_tools` — true on Gemini (function declarations) and ElevenLabs (client tools), false on GPT-Live (the native wire carries no tool schema) — hides the direct entry where it cannot run. `LiveSessionStart.mode` (`delegated` \| `direct`) is a column of the session RECORD, chosen at `POST /live/sessions {mode}`. |
| B7 | **ElevenLabs wire, measured on the official SDK 1.25.0** (a key with `sk_` is needed on dev to measure it live — the dev connector holds a key ID): signed URL (`GET /convai/conversation/get-signed-url?agent_id=`), subprotocol `convai`, first frame `conversation_initiation_client_data` with `conversation_config_override.agent.prompt.prompt`, first answer `conversation_initiation_metadata` (`conversation_id`, `agent_output_audio_format` e.g. `pcm_16000`, `user_input_audio_format`), audio `audio.audio_event.audio_base_64` (+ `event_id`), input `{user_audio_chunk}` base64 PCM 16 k, `interruption.interruption_event.event_id` (drop audio ≤ it), `user_transcript.user_transcription_event.user_transcript`, `agent_response.agent_response_event.agent_response` (whole sentences), `ping`→`pong{event_id}`, `client_tool_call{tool_name, tool_call_id, parameters}`→`client_tool_result{tool_call_id, result, is_error}`, `contextual_update{text}` (a late answer), `context_usage` (to read for the meter). `connection = "token"` (the credential IS the signed URL), `delegation_wire = "tool"` (`send_to_lia` as a CLIENT tool), `audio.ownership = "pcm"`. |
| B8 | **The agent is the person's; LIA touches only what is LIA's**: at activation and on every save, the chosen agent is synced by fingerprint — the override permission for `prompt` (+ `first_message`), and the CLIENT tools LIA needs (`send_to_lia`; the derived read-only set for direct sessions). The form says so before the activation. No model, voice, language, VAD or duration is ever written. |
| B9 | **Pricing**: ElevenLabs bills the minute; one tariff row per PROVIDER (`elevenlabs-convai`, `per_audio_minute`) serves every agent — `LiveProvider.tariff_name(model)` maps an agent id to it, so `pricing.py` keeps its one rule. The ElevenLabs LLM cost is the agent's own (portal), outside LIA's meter and said so in the settings. |
| B10 | **Voices**: none listed (portal) — `LiveVoicesResponse` empty with a `portal` provenance, the settings hide the voice select and the sample when the provider declares `portal_voice`; the durations, the budget and the reflexes the provider decides itself follow the existing capability flags. |

## 3. What is measured before it is trusted

- ElevenLabs: the listing and the signed URL on a real key; the override accepted on an
  agent with the permission; a client tool call round trip and its latency; `context_usage`'s
  payload; the audio formats the agent declares. **Blocked on dev until an `sk_` key is set**
  (both dev keys are key IDs — `api_key_id_used_as_api_key`).
- Gemini direct: a real session with the derived declarations in the setup — the per-turn
  prompt size (the cost the owner's premise gets wrong), a lookup round trip, the learning
  pass at the end reading the archived rows.

## 4. Lots

**Status 2026-09-19 (evening): N, O, P, Q, R delivered, not committed.** N/O proved on dev
against a real Gemini session (a throwaway account: 55 declarations, the model calling
`get_events_tool` itself, the door in 0.23 s, the treatment row on `live_session`, the
refusals in words; the first proof found `LiveSessionRecord.mode` LOST on read — fixed, the
round-trip pinned over every field); the premise measured: 10 983 prompt tokens on the first
turn against 1 227 delegated. P/Q then MEASURED on the owner's own agent the same evening: `source_info` closes 1008
after the metadata (removed; the probe now waits past the metadata), array items need a
description (422), a refused creation cancels its siblings (`TaskGroup`); the initiation
with the prompt override stays open, the permission PATCH holds.

| Lot | Deliverable |
|---|---|
| N | `VoiceToolHost`: `run_live_tool` generalised (surface, run id, spend node, metric label); `live_session` consultation surface declared; `POST /live/sessions/{id}/tools` (record owner, `mode = direct`, the derived set, bounded); `LiveSessionRecord.mode`; the direct mandate (phone prompts + context + rules); `direct_tools` capability; start publishes `mode` and the tool declarations. |
| O | Frontend direct mode: the third menu entry (hidden without `direct_tools`), `liveStore.mode`, the controller's tool path (Gemini `toolCall` → API → `toolResponse`; no bridge, no chat binding), the banner unchanged, the closing card as today; six locales; vitest + Playwright. |
| P | ElevenLabs backend: `ConnectorType.ELEVENLABS_LIVE`, `providers/elevenlabs_live.py` (listing = agents, signed URL, agent sync by fingerprint reusing `telephony/client.py`, probe = signed URL + handshake), tariff row + seed + migration guard, i18n. |
| Q | ElevenLabs frontend: `transports/elevenlabs-ws.ts`, provider row, connector form (agent instead of model, no voice), CSP host, e2e on `routeWebSocket`. |
| R | Docs (LIVE_MODE, ADR-300 amendment, CONNECTORS, mobile guides), memory, gates. |
