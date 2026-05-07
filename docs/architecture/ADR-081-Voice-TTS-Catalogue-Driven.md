# ADR-081: Voice TTS configuration driven by the LLM catalogue

**Status**: ✅ IMPLEMENTED (2026-05-07)
**Author**: Claude Code (Opus 4.7)
**Related**: ADR-078 (LLM Catalogue DB-Source-of-Truth), ADR-080 (Remote Voice STT and pricing-unit extension), ADR-063 (Cross-Worker Cache Invalidation)

## Context

The voice synthesis stack predates ADR-078. Until v1.20.x the active TTS
provider was selected by a binary admin switch (`system_settings.voice_tts_mode
∈ {standard, hd}`) backed by **fourteen** environment variables that
hard-coded the providers, models, voice IDs and tuning per mode:

```
VOICE_TTS_DEFAULT_MODE=standard
VOICE_TTS_STANDARD_PROVIDER=edge
VOICE_TTS_STANDARD_VOICE_MALE=fr-FR-RemyMultilingualNeural
VOICE_TTS_STANDARD_VOICE_FEMALE=fr-FR-VivienneMultilingualNeural
VOICE_TTS_STANDARD_RATE=+10%
VOICE_TTS_STANDARD_PITCH=+0Hz
VOICE_TTS_STANDARD_VOLUME=+0%
VOICE_TTS_HD_PROVIDER=openai
VOICE_TTS_HD_PROVIDER_CONFIG={}
VOICE_TTS_HD_VOICE_MALE=echo
VOICE_TTS_HD_VOICE_FEMALE=coral
VOICE_TTS_HD_MODEL=tts-1-1106
VOICE_TTS_HD_SPEED=1.1
VOICE_TTS_HD_RESPONSE_FORMAT=mp3
```

Three problems compounded over time:

1. **Three TTS providers with three distinct tuning surfaces.** Edge expects
   SSML `rate`/`pitch`/`volume` strings (`"+10%"` / `"+0Hz"`); OpenAI takes a
   numeric `speed` (0.25–4.0) and a `response_format` (mp3/opus/…);
   ElevenLabs takes an `output_format` (mp3_44100_128 / pcm_16000 / …) plus
   a `voice_settings` object (stability / similarity_boost / style /
   use_speaker_boost). Forcing all three through a flat `standard|hd` env-
   driven schema either drops fields or pollutes the schema with mode-
   specific keys. The `provider_config` JSON column on
   `llm_config_overrides` already exists for exactly this purpose for
   chat models — it should be used here too.
2. **Voice IDs are model-specific, not mode-specific.** Switching from
   OpenAI's `tts-1-hd` to ElevenLabs's `eleven_turbo_v2_5` invalidates the
   `VOICE_TTS_HD_VOICE_MALE` value (`echo` is an OpenAI voice; ElevenLabs
   needs a 22-char voice_id). The mode abstraction hides that the voice
   choice depends on the **model**, not on a quality tier.
3. **Pricing was decoupled from the model registry.** Costs for
   `tts-1`/`tts-1-hd`/`eleven_*` lived only in code or scattered constants,
   meaning admins could not see, audit, or alter per-character rates from
   the same admin view that controls chat-model pricing (ADR-078). Once
   ADR-080 extended `llm_model_pricing` with `pricing_unit`, all three
   surfaces became eligible for the catalogue.

A "TTS-only mini-admin" was considered — a parallel CRUD just for voice
parameters. Rejected: it duplicates the LLM-config pattern that ADR-078
established as the single source of truth for any (provider, model)
selection. A second route considered was keeping `voice_tts_mode` and only
adding ElevenLabs as a third HD slot. Rejected: it does not fix
problem 1 (still no per-provider tuning surface) and stretches the
`standard|hd` binary into a fiction.

## Decision

### 1. Promote TTS to a first-class LLM type

A new entry `voice_tts` is registered in `LLM_TYPES_REGISTRY`
(`apps/api/src/domains/llm_config/constants.py`) with `required_kind=tts`.
The category is `specialized`. Its `LLM_DEFAULTS` carries Edge as the
default provider, model `edge-tts`, and a JSON-encoded `provider_config`
holding the canonical Edge French voice pair plus neutral SSML tuning:

```python
"voice_tts": LLMAgentConfig(
    provider="edge",
    model="edge-tts",
    provider_config=(
        '{'
        '"voice_male": "fr-FR-RemyMultilingualNeural",'
        '"voice_female": "fr-FR-VivienneMultilingualNeural",'
        '"rate": "+10%","pitch": "+0Hz","volume": "+0%"'
        '}'
    ),
    temperature=0.0, top_p=1.0,
    frequency_penalty=0.0, presence_penalty=0.0,
    max_tokens=1000,
    timeout_seconds=60.0,
)
```

### 2. Add the missing providers and TTS catalogue entries

`LLMProviderEnum` (Postgres ENUM `llm_provider_enum`) gains `edge`
alongside the existing `elevenlabs`. Six TTS rows are seeded into
`llm_models` + `llm_model_pricing`:

| Provider | Model | Pricing unit | Input price |
|---|---|---|---|
| edge | edge-tts | per_1m_tokens | $0.00 (free) |
| openai | tts-1 | per_1m_tokens | $15.00 |
| openai | tts-1-hd | per_1m_tokens | $30.00 |
| elevenlabs | eleven_multilingual_v2 | per_1m_tokens | $100.00 |
| elevenlabs | eleven_turbo_v2_5 | per_1m_tokens | $50.00 |
| elevenlabs | eleven_flash_v2_5 | per_1m_tokens | $50.00 |

Note: TTS is billed **per character** by all three commercial providers.
We expose this in the unified `per_1m_tokens` axis (chars tracked as
tokens) rather than minting a `per_1m_chars` unit — pricing math is
identical, the cost tracker already takes a token count, and the unit
label on the admin form is generic enough that "$/1M chars or tokens"
fits without ambiguity. Edge stays at $0 so its row is informational —
it surfaces the model in the picker without skewing cost reports.

### 3. JSONB `provider_config` carries the voice + tuning

The factory `apps/api/src/domains/voice/factory.py` reads the active
`voice_tts` override from `LLMConfigOverrideCache` (merged with
`LLM_DEFAULTS`) and parses `provider_config` into a typed `TTSConfig`:

```text
provider_config = {
  "voice_male":      "echo",          # mandatory for edge / openai / elevenlabs
  "voice_female":    "nova",          # mandatory
  "rate":            "+10%",          # edge only (SSML)
  "pitch":           "+0Hz",          # edge only
  "volume":          "+0%",           # edge only
  "speed":           1.1,             # openai only (0.25..4.0)
  "response_format": "mp3",           # openai only
  "output_format":   "mp3_44100_128", # elevenlabs only
  "voice_settings":  {                # elevenlabs only
    "stability":         0.5,
    "similarity_boost":  0.75,
    "style":             0.0,
    "use_speaker_boost": true
  }
}
```

Only the keys that match the active provider need be present. Switching
provider in the admin UI **resets** the JSONB so a stale Edge `voice_id`
cannot leak into an OpenAI/ElevenLabs override and crash at synthesis.

### 4. Admin UI — voice picker dynamic per provider

A new admin endpoint `GET /admin/voice/voices?provider={edge,openai,elevenlabs}`
returns the voice catalogue:

- **Edge / OpenAI**: curated static list (their voice catalogues are
  stable and well-documented).
- **ElevenLabs**: live `GET /v1/voices` against the configured account
  (custom + shared voices are account-scoped and impossible to predict).
  Requires `voices_read` scope on the API key. A 502 is surfaced when
  the upstream call fails so the UI shows a precise toast.

The Configuration LLM dialog (`AdminLLMConfigSection.tsx`) detects
`required_kind === 'tts'` and renders an inline block with:

- two voice-picker selects (`voice_male` / `voice_female`) filtered by
  the API's `gender` field;
- per-provider tuning inputs (Edge: rate/pitch/volume text inputs;
  OpenAI: speed slider + response_format select; ElevenLabs:
  output_format select + stability/similarity_boost/style sliders +
  use_speaker_boost toggle);
- a green "live catalogue" badge when the voice list comes from a live
  ElevenLabs call.

The admin saves once; the dialog serialises the parsed JSON to a
canonical (sorted-keys) string before sending — a key permutation does
not raise a false-positive "modified" badge.

### 5. Retire `system_settings.voice_tts_mode`

The whole `voice_tts_mode` chain is deleted: the row in `system_settings`
is dropped by migration `2026_05_07_0004-add_edge_provider_drop_voice_tts_mode.py`,
the `VOICE_TTS_MODE` enum value is removed from `SystemSettingKey`, the
admin endpoints `/admin/system-settings/voice-mode` (GET/PUT) and the
matching service methods, schemas, Redis cache (`VoiceTTSModeCache`),
the front-end `AdminVoiceSettingsSection.tsx`, and all 14 `VOICE_TTS_*`
env vars are removed. The removal takes its full benefit only when
combined with the catalogue migration (steps 1–3).

## Consequences

**Positive**
- Single source of truth for any (TTS provider, model, voice) tuple:
  the `llm_config_overrides.voice_tts` row, mirroring the chat-model
  pattern from ADR-078.
- The admin can swap providers/models at runtime without redeploying:
  the override + provider_config update through the existing
  PUT `/admin/llm-config/types/voice_tts` endpoint, the
  `LLMConfigOverrideCache` invalidates cross-worker via the
  ADR-063 Pub/Sub channel.
- TTS pricing surfaces in the same admin view as chat pricing, with
  the same audit trail (`AdminAuditLog`) — a year-end refacturation
  pulls character counts directly from `llm_model_pricing`.
- Each provider's tuning surface is fully exposed (Edge SSML strings,
  OpenAI speed/format, ElevenLabs voice_settings) via JSONB without
  inflating the column count.
- Three providers from day one (Edge / OpenAI / ElevenLabs); adding a
  fourth (e.g. Gemini TTS once the streaming endpoint lands publicly)
  is a 3-step delta: provider enum + model seed + client implementation.

**Negative / accepted trade-offs**
- The 14 `VOICE_TTS_*` env vars disappear; any operator running with a
  custom env override loses their setting on upgrade and must re-do it
  through the Configuration LLM admin. The seed defaults (`Edge`,
  Rémy / Vivienne, +10 % rate) match the previous standard-mode
  defaults so the experience is unchanged out of the box.
- TTS is priced through the `per_1m_tokens` axis even though commercial
  providers bill per character. Our cost tracker already passes
  character-count-as-tokens, so the math is correct — but an admin
  reading "tts-1: $15 per 1 M tokens" must internalise that "tokens"
  here means "characters". A second `pricing_unit` value (`per_1m_chars`)
  was considered overkill: it would only surface a cosmetic label
  difference in the admin form for zero behavioural change. If the
  admin signal becomes confusing in practice, switching is a one-row
  migration.
- The admin form can save a `provider_config` JSON whose shape mismatches
  the selected provider (e.g. an `output_format` field with an
  `edge` provider). The factory tolerates this — irrelevant keys are
  silently ignored. We considered server-side validation (per-provider
  JSON schema) but the cost of maintaining three schemas in sync with
  three vendor SDKs outweighs the benefit; instead, the admin UI clears
  `provider_config` on provider switch.
- The legacy `mode == "hd"` gate (still consumed by a handful of
  downstream call sites — `voice_comment_node`, the streaming response
  node, etc.) survives as a back-compat alias on the new `TTSConfig`
  dataclass: `mode` is computed from `is_paid` (`"hd"` if the provider
  is not Edge, `"standard"` otherwise). The alias will be retired once
  every call site has migrated to checking `is_paid` explicitly.

## Migration

`apps/api/alembic/versions/2026_05_07_0004-add_edge_provider_drop_voice_tts_mode.py`:

1. Adds `'edge'` to the `llm_provider_enum` Postgres ENUM via the
   rename-create-alter-drop loop pattern (the same pattern already
   used in the v1.19 multi-provider migration). All dependent columns
   (including `image_generation_pricing.provider`) are migrated through
   a dynamic `pg_attribute` loop so adding a new value never breaks
   downstream tables.
2. `DELETE FROM system_settings WHERE key = 'voice_tts_mode'` so the
   stale row does not linger past the ENUM cleanup.

`infrastructure/database/seeds/llm_pricing_seed.sql` ships the six TTS
rows with their pricing. `task db:seed:sql` is additive (idempotent
INSERTs guarded by ON CONFLICT) — re-applying the seed on an existing
DB only adds the missing rows, preserving any admin-edited prices.

## Verification

- ✅ Backend smoke test: `from src.domains.voice.factory import get_tts_client_sync` resolves and the fallback Edge config is constructed cleanly.
- ✅ Backend public surface: `SystemSettingKey` no longer carries `VOICE_TTS_MODE`; `settings.voice_tts_default_mode` is gone.
- ✅ Admin endpoint: `GET /admin/voice/voices?provider=elevenlabs` returns the live account catalogue with `source=live`; `?provider=edge` and `?provider=openai` return curated static lists with `source=static`.
- ✅ Admin UI: switching the `voice_tts` LLM type's provider in the Configuration LLM dialog clears `provider_config`, repopulates the voice picker from the new provider's voices endpoint, and saves a canonical (sorted-keys) JSON to `llm_config_overrides`.
- ✅ Frontend typecheck: `pnpm tsc --noEmit` clean (the only pre-existing error is unrelated to this refactor).
- ✅ i18n parity: 6 locales aligned (`missing=0, extra=0` against `en`).
