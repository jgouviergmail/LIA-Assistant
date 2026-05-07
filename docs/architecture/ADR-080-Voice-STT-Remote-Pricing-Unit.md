# ADR-080: Remote Voice STT (ElevenLabs Scribe) and pricing-unit extension

**Status**: ✅ IMPLEMENTED (2026-05-07)
**Author**: Claude Code (Opus 4.7)
**Related**: ADR-078 (LLM Catalogue DB-Source-of-Truth), ADR-039 (Cost Optimization & Token Management), ADR-063 (Cross-Worker Cache Invalidation)

## Context

The voice mode shipped as a 100 % local POC: a wake-word KWS in the browser
(Sherpa-onnx Whisper WASM) + a server-side WebSocket that forwarded audio
to a local Sherpa-onnx Whisper-small model. It was free, offline, and
architecturally simple, but its transcription quality was visibly inferior
to commercial providers. The ask from the operator was to **add an
opt-in remote STT** without dropping the local fallback, and to **bill the
user for the remote calls** with a precision compatible with refacturation.

Two non-trivial constraints collided:

1. **Pricing model mismatch.** The existing pricing infrastructure
   (`llm_model_pricing`, `pricing_cache`, ADR-078) prices everything per
   1 million tokens. ElevenLabs Scribe is billed **per audio hour**
   ($0.22/h for v1/v2). Storing $0.22/h via a fictional 1 M-tokens
   convention works mathematically but corrupts the admin view (the
   "Tarification LLM" form would show "$0.22 / 1M tokens" for an STT
   model, which is meaningless and triggers wrong assumptions during
   refacturation audit).
2. **Cost attribution to user-side messages.** Existing costs are stored
   on `message_token_summary` keyed by the assistant `run_id`. STT
   happens **before** any assistant run — the cost belongs to the user
   bubble and must reach the dashboard, the usage-limit check, and the
   per-conversation totals.

A separate STT pricing system (parallel cache, parallel admin form) was
considered and rejected: it would duplicate the catalogue pattern just
established by ADR-078. A "fictional tokens" convention was also
considered and rejected for the audit reason above.

## Decision

### 1. Extend `llm_model_pricing` with a `pricing_unit` ENUM

A native PostgreSQL ENUM `pricing_unit_enum` is added with three values:

- `per_1m_tokens` (default — preserves the entire chat/text catalogue
  unchanged after the migration);
- `per_audio_minute`;
- `per_audio_hour`.

The three price columns are **renamed** to drop their token-bound
suffix:

- `input_price_per_1m_tokens` → `input_unit_price`
- `output_price_per_1m_tokens` → `output_unit_price`
- `cached_input_price_per_1m_tokens` → `cached_input_unit_price`

The semantic of these columns now depends on `pricing_unit`. ElevenLabs
Scribe is seeded with `pricing_unit=per_audio_hour`,
`input_unit_price=0.22`, mirroring the official tariff verbatim — auditable
without any conversion intermediary.

The pricing cache (`infrastructure/cache/pricing_cache.py`) gains a
dedicated sync-safe helper:

```python
get_cached_cost_audio_usd_eur(model: str, duration_seconds: float) -> tuple[float, float]
```

A guard short-circuits the existing `get_cached_cost_usd_eur` (token-based)
when the model's `pricing_unit` is not `per_1m_tokens`, and vice-versa. No
silent miscomputation is possible.

### 2. New `voice_transcription` LLM type and `elevenlabs` provider

`elevenlabs` joins `LLMProviderEnum` and `LLM_PROVIDERS`. A new LLM type
`voice_transcription` is added to `LLM_TYPES_REGISTRY` / `LLM_DEFAULTS`
with `required_kind=audio` so the Configuration LLM admin filters its
model selector to audio-priced rows. The default override points to
`elevenlabs/scribe_v2`.

### 3. Backend STT routing (factory + protocol)

A small abstraction layer is introduced in `domains/voice/stt/`:

- `SttServiceProtocol.transcribe_pcm_int16_async(bytes, sample_rate, language) -> STTResult`
- `SherpaSttService` (existing local backend) implements the protocol via
  a thin adapter; its existing `(list[float]) -> str` API is preserved
  for the Telegram channel.
- `ElevenLabsSttService` POSTs the raw PCM Int16 LE 16 kHz buffer to
  `POST /v1/speech-to-text` with `file_format=pcm_s16le_16` (no WAV
  wrap — confirmed verbatim by the ElevenLabs documentation).
- `get_stt_service_for_mode(mode)` selects the backend based on the
  per-user `voice_stt_mode` preference (`local` | `remote`).

### 4. Per-user `voice_stt_mode` + ticket propagation

A new `users.voice_stt_mode` column carries the user preference. The
WebSocket auth ticket (`/voice/ticket`) embeds the value at issue time;
the `/ws/audio` handler reads it from the consumed ticket and resolves
the right backend on each "END" signal — no extra DB lookup per
transcription.

### 5. Per-message cost attribution

Five nullable columns are added to `conversation_messages` (
`stt_provider`, `stt_audio_duration_seconds`, `stt_cost_usd`,
`stt_cost_eur`, `stt_usd_to_eur_rate`). The frontend captures the cost
metadata returned by the WS in the `TranscriptionResult`, stores it in a
local pending state, and forwards it with the next chat send. The chat
endpoint propagates the values through `archive_message`, which persists
them on the user `conversation_messages` row only when `role='user'` and
`stt_provider` is set.

In parallel, the `/ws/audio` handler updates `user_statistics` aggregates
(`total_stt_*`, `cycle_stt_*`) the moment a remote transcription
succeeds, so the dashboard "Cost" tile and the `usage_limits`
per-cycle check see the spend immediately even if the user never sends
the message.

### 6. Usage limits

The remote-STT branch performs a `UsageLimitService.check_user_allowed`
**before** the ElevenLabs call. A blocked user closes the WebSocket with
close code 4029 and zero spend at the provider. STT cost adds up into
the existing `cycle_cost_eur` / `total_cost_eur` columns — no new
dedicated limit columns.

### 7. Decoupled UI (push-to-talk independent of wake word)

The `voice_stt_mode` switch is exposed in `VoiceModeSettings`
**independent of** the wake-word toggle (`voice_mode_enabled`). Push-to-talk
(long-press send button) and wake-word (hands-free) both consume the
same backend selected here.

## Consequences

**Positive**

- Refacturation auditable: $0.22/h is stored as $0.22/h, not as a
  derived per-1M-tokens rate.
- Pattern reuse: same admin form, same cache, same provider-key store —
  no duplicate STT system to maintain.
- Extensible: the same `pricing_unit` accommodates Whisper API (OpenAI),
  Deepgram, AssemblyAI, etc. without further schema changes.
- Independent of the wake word: a user can opt into ElevenLabs for
  push-to-talk only, without enabling the hands-free mode.

**Negative**

- The renamed price columns force a coordinated rename of ~40 backend
  call sites and ~5 frontend files. One-time cost; no API contract leak
  outside the admin Tarification surface.
- Audio leaves the LIA server perimeter when a user picks `remote`.
  Mitigated via an explicit privacy notice in
  `VoiceModeSettings` and per-message persistence so the operator can
  audit volumes after the fact.
- `voice_transcription` reuses the LLM config / provider-key
  infrastructure even though Scribe is not a chat model. Acceptable
  because the catalogue (`llm_models`) already supports `kind=audio` and
  the Configuration LLM admin already filters by `required_kind`.

## Implementation pointers

**Migrations** (3, in order)
- `2026_05_07_0001-pricing_columns_rename_unit.py` — renames the three
  price columns, adds `pricing_unit_enum`, adds `'elevenlabs'` to
  `llm_provider_enum` (rename/create/alter-column/drop dance with a
  dynamic pg_attribute lookup for every dependent table).
- `2026_05_07_0002-stt_columns_messages.py` — five nullable STT columns
  on `conversation_messages` + partial index on `stt_provider`.
- `2026_05_07_0003-stt_aggregates_user_pref.py` — STT aggregates on
  `user_statistics` + `voice_stt_mode` on `users`.

**Backend**
- `domains/voice/stt/{protocol,exceptions,sherpa_stt,elevenlabs_stt,factory}.py`
- `domains/voice/router.py` (`/ws/audio` routing + check_user_allowed)
- `domains/voice/ticket_store.py` (extended ticket payload)
- `infrastructure/cache/pricing_cache.py` (audio variant + token guard)
- `domains/llm/{models,schemas,service,router,pricing_service}.py` (column rename + pricing_unit)
- `domains/llm_config/constants.py` (`voice_transcription` type, ElevenLabs default)
- `domains/conversations/{models,repository,service,schemas,router}.py` (STT columns + pass-through)
- `domains/agents/api/{schemas,service,router}.py` (ChatRequest STT fields propagation)
- `domains/chat/{models,repository,service}.py` (UserStatistics STT aggregates + `add_stt_usage` / `record_remote_stt`)
- `domains/google_api/export_service.py` + `router.py` + `user_export_router.py` (CSV exports)

**Frontend**
- `components/settings/VoiceModeSettings.tsx` (decoupled local/remote switch)
- `components/settings/AdminLLMPricingSection.tsx` (pricing_unit select, dynamic labels)
- `components/settings/ConsumptionExportSection.tsx` (stt-usage card)
- `components/chat/ChatMessage.tsx` (STT badge on user bubble)
- `components/chat/ChatInput.tsx` (pendingSttMeta state, propagation to send)
- `hooks/{useVoiceInput,useVoiceMode,useChat,useConversation}.ts`
- `lib/voice-input-service.ts` (TranscriptionResult + meta callback)
- `locales/{en,fr,de,es,it,zh}/translation.json`

**Tests**
- `tests/unit/infrastructure/test_pricing_cache_audio.py`
- `tests/unit/domains/voice/test_stt_factory.py`
- `tests/unit/domains/voice/test_elevenlabs_stt.py`

## What this ADR does NOT change

- The wake-word KWS remains English-only (`whisper-tiny.en` bundled in
  WASM). Multilingual wake word will require a separate WASM rebuild and
  is out of scope here. The `voice_stt_mode='remote'` switch only
  affects the **post-wake-word transcription** (and push-to-talk).
- Scribe v2 Realtime ($0.39/h, ~150 ms latency) is intentionally not
  seeded — it lives on a different endpoint and the MVP buffers audio
  end-to-end before sending.
- Dynamic per-language pricing is not modelled. ElevenLabs charges the
  same per-hour rate regardless of language; if a future provider
  charges differently, a per-language pricing row remains an additive
  change (one new pricing row per language).
