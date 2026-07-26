# Voice / Text-to-Speech (TTS)

> **Technical Documentation** - Voice Synthesis Domain
>
> **Version**: 4.0
> **Date**: 2026-05-07
> **Updated**: TTS now lives on the LLM catalogue (ADR-081) — `voice_tts` LLM type, three providers (Edge / OpenAI / ElevenLabs), voice + tuning in `provider_config` JSONB.
>
> Related: [ADR-081](../architecture/ADR-081-Voice-TTS-Catalogue-Driven.md) | [ADR-078](../architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md) | [ARCHITECTURE.md](../ARCHITECTURE.md) | [SMART_SERVICES.md](./SMART_SERVICES.md)

---

## Overview

The Voice domain provides a multi-provider TTS abstraction. As of v1.20.x
(ADR-081), the active provider/model/voice/tuning is selected through the
**Configuration LLM** admin (LLM type `voice_tts`) — the same path used
for chat models since ADR-078 — and stored on
`llm_config_overrides.voice_tts`. Voice IDs and per-provider tuning live
in the row's `provider_config` JSONB blob.

### Key Features

- **LLM-catalogue-driven**: provider, model, voice IDs, and provider-
  specific tuning come from a single override row (`llm_config_overrides
  .voice_tts`) merged with `LLM_DEFAULTS`.
- **Three providers from day 1**: Edge (free), OpenAI (`tts-1` /
  `tts-1-hd`), ElevenLabs (`eleven_multilingual_v2` / `eleven_turbo_v2_5`
  / `eleven_flash_v2_5`).
- **Per-provider tuning surfaces**:
  - Edge: SSML `rate` / `pitch` / `volume` strings;
  - OpenAI: `speed` (0.25–4.0) + `response_format` (mp3/opus/…);
  - ElevenLabs: `output_format` + `voice_settings` (stability /
    similarity_boost / style / use_speaker_boost).
- **Dynamic voice picker**: `GET /admin/voice/voices?provider=X` returns
  curated lists for Edge/OpenAI and a live `GET /v1/voices` for
  ElevenLabs (account-scoped).
- **Per-user opt-in**: voice synthesis enabled per user via the
  `users.voice_mode_enabled` flag — orthogonal to the admin's TTS
  provider choice.
- **Graceful fallback**: when a paid provider is selected but its API
  key is missing, the factory transparently falls back to Edge (logged
  warning) so the response surface keeps producing audio.

### Pricing surface

All TTS rows use the unified `per_1m_tokens` pricing axis (characters
tracked as tokens — math is identical, label is generic enough). Seeded
catalogue:

| Provider | Model | Input price |
|---|---|---|
| edge | edge-tts | $0.00 (free) |
| openai | tts-1 | $15.00 / 1M chars |
| openai | tts-1-hd | $30.00 / 1M chars |
| elevenlabs | eleven_multilingual_v2 | $100.00 / 1M chars |
| elevenlabs | eleven_turbo_v2_5 | $50.00 / 1M chars |
| elevenlabs | eleven_flash_v2_5 | $50.00 / 1M chars |

Admins can edit prices through the same Tarification LLM Texte form used
for chat models.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VOICE DOMAIN (v4)                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    SERVICE LAYER                                    │ │
│  │                                                                      │ │
│  │   VoiceCommentService                                               │ │
│  │   ├── stream_voice_comment()    # Main streaming method             │ │
│  │   ├── generate_voice_comment()  # LLM comment generation            │ │
│  │   └── _get_voice_for_language() # Voice selection logic             │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                            │                                             │
│                            ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    FACTORY LAYER                                    │ │
│  │                                                                      │ │
│  │   factory.py — driven by LLMConfigOverrideCache.voice_tts           │ │
│  │   ├── get_tts_client()         # Returns TTSClient for the active   │ │
│  │   │                              override (Edge/OpenAI/ElevenLabs)  │ │
│  │   ├── get_tts_config()         # Returns parsed TTSConfig           │ │
│  │   └── get_tts_client_sync(cfg) # Sync variant for non-async sites   │ │
│  │                                                                      │ │
│  │   TTSConfig(dataclass)                                              │ │
│  │   ├── provider: "edge" | "openai" | "elevenlabs" | "gemini"         │ │
│  │   ├── model: str                                                    │ │
│  │   ├── voice_male, voice_female (parsed from provider_config)        │ │
│  │   ├── rate, pitch, volume (Edge only)                               │ │
│  │   ├── speed, response_format (OpenAI only)                          │ │
│  │   ├── output_format, voice_settings (ElevenLabs only)               │ │
│  │   ├── is_paid: bool         (modern flag)                           │ │
│  │   └── mode: "standard"|"hd" (back-compat alias = "hd" if is_paid)   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                            │                                             │
│                            ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    PROTOCOL LAYER (NEW)                             │ │
│  │                                                                      │ │
│  │   protocol.py - TTSClient (runtime-checkable Protocol)              │ │
│  │   ├── synthesize(text, voice_name, **kwargs) → bytes               │ │
│  │   ├── synthesize_base64(...) → str                                  │ │
│  │   ├── close() → None                                                │ │
│  │   └── Properties: provider_name, audio_format                       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                            │                                             │
│            ┌───────────────┴───────────────┐                             │
│            ▼                               ▼                             │
│  ┌──────────────────────┐     ┌──────────────────────────┐              │
│  │  STANDARD MODE       │     │  HD MODE                  │              │
│  │                      │     │                           │              │
│  │  EdgeTTSClient       │     │  OpenAITTSClient          │              │
│  │  ├── edge-tts lib    │     │  ├── openai.audio.speech  │              │
│  │  ├── MP3 output      │     │  ├── tts-1 / tts-1-hd     │              │
│  │  └── GRATUIT         │     │  └── $15-30/1M chars      │              │
│  │                      │     │                           │              │
│  │  Voices:             │     │  Voices:                  │              │
│  │  - fr-FR-HenriNeural │     │  - alloy, echo, fable     │              │
│  │  - fr-FR-DeniseNeural│     │  - onyx, nova, shimmer    │              │
│  └──────────────────────┘     └──────────────────────────┘              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Admin Control: Configuration LLM

The TTS provider/model/voice is controlled through the **Configuration
LLM** admin form (LLM type `voice_tts`). The override row is persisted to
`llm_config_overrides.voice_tts` and broadcast across workers via the
ADR-063 Pub/Sub channel — no env var, no system_settings table involved.

### Endpoints

```bash
# Read current TTS config (effective = defaults merged with override)
GET /api/v1/admin/llm-config/types/voice_tts
Authorization: Bearer <admin_token>

# Response:
{
  "llm_type": "voice_tts",
  "info": { "required_kind": "tts", ... },
  "effective": {
    "provider": "elevenlabs",
    "model": "eleven_turbo_v2_5",
    "provider_config": "{\"voice_male\":\"echo_id\",\"voice_female\":\"nova_id\",\"output_format\":\"mp3_44100_128\",\"voice_settings\":{...}}",
    ...
  },
  "is_overridden": true
}

# Update (full-replace semantics; null clears the override of that field)
PUT /api/v1/admin/llm-config/types/voice_tts
Authorization: Bearer <admin_token>
{
  "provider": "elevenlabs",
  "model": "eleven_turbo_v2_5",
  "provider_config": "{\"voice_male\":\"<elevenlabs_voice_id>\",...}"
}

# Reset to code defaults
POST /api/v1/admin/llm-config/types/voice_tts/reset

# Voice picker — populated dynamically by the admin form when the
# admin selects a TTS provider. Edge/OpenAI return curated lists,
# ElevenLabs returns a live GET /v1/voices for the configured account.
GET /api/v1/admin/voice/voices?provider=elevenlabs
Authorization: Bearer <admin_token>

# Response:
{
  "provider": "elevenlabs",
  "voices": [
    { "voice_id": "21m00Tcm4TlvDq8ikWAM", "label": "Rachel",
      "gender": "female", "language": "en" },
    ...
  ],
  "source": "live"
}
```

### Cross-worker propagation

```
Admin Request
     │
     ▼
PUT /admin/llm-config/types/voice_tts
     │
     ├── Update llm_config_overrides.voice_tts (PostgreSQL)
     ├── Create AdminAuditLog entry
     └── LLMConfigOverrideCache.invalidate_and_reload()
                    │
                    ├── Reload from DB
                    └── Publish "llm_config_overrides" on Redis Pub/Sub
                                    │
                                    ▼
                       Other API workers receive the message
                                    │
                                    ▼
                       Each worker reloads its in-memory cache
                                    │
                                    ▼
                       Next get_tts_client() call sees the new override
```

The factory reads `LLMConfigOverrideCache.get_override("voice_tts")`
synchronously at synthesis time — no Redis hit on the hot path, no
Postgres query.

---

## Configuration

### Environment Variables

The 14 legacy `VOICE_TTS_*` env vars (Standard/HD modes) were retired by
ADR-081. Per-provider tuning now lives in the admin UI's
`provider_config` JSONB. The remaining voice-related env vars cover the
voice-comment LLM, the Sherpa local STT pipeline, and the WebSocket
transport defaults — see [.env.example](../../.env.example) section
"VOICE — TTS / STT" for the live list.

```bash
# .env — TTS provider/model/voice/tuning are NOT here anymore.
# Configure them under "Configuration LLM → Voice Synthesis (TTS)".

# Voice Comment LLM (still env-driven)
VOICE_LLM_PROVIDER=openai
VOICE_LLM_MODEL=gpt-4.1-nano
VOICE_LLM_TEMPERATURE=0.7
VOICE_LLM_MAX_TOKENS=500
VOICE_MAX_SENTENCES=3

# Voice context
VOICE_CONTEXT_MAX_CHARS=2000
VOICE_PARALLEL_TIMEOUT_SECONDS=15.0
VOICE_CHAT_MODE_MAX_SENTENCES=3
```

### `provider_config` JSONB shape

Documented authoritatively on `apps/api/src/domains/voice/factory.py`.
Only keys relevant to the active provider need be present; others are
ignored:

```json
{
  "voice_male": "fr-FR-RemyMultilingualNeural",
  "voice_female": "fr-FR-VivienneMultilingualNeural",
  "rate": "+10%",            // edge only (SSML)
  "pitch": "+0Hz",           // edge only
  "volume": "+0%",           // edge only
  "speed": 1.1,              // openai only (0.25..4.0)
  "response_format": "mp3",  // openai only
  "output_format": "mp3_44100_128",  // elevenlabs only
  "voice_settings": {                // elevenlabs only
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": true
  }
}
```

---

## Usage

### Factory Pattern

```python
from src.domains.voice.factory import get_tts_client, get_tts_config

# Get the current TTSConfig parsed from the active override
cfg = await get_tts_config()
# cfg.provider = "elevenlabs"
# cfg.model = "eleven_turbo_v2_5"
# cfg.voice_male = "<elevenlabs_voice_id>"
# cfg.voice_female = "<elevenlabs_voice_id>"
# cfg.voice_settings = {"stability": 0.5, ...}
# cfg.is_paid = True            # use this for new code
# cfg.mode = "hd"               # back-compat alias for legacy call sites

# Get the matching client (Edge / OpenAI / ElevenLabs)
client = await get_tts_client()
audio = await client.synthesize("Bonjour !", voice_name=cfg.voice_female)

# Synchronous variant — for callers that already hold a config
from src.domains.voice.factory import get_tts_client_sync
client = get_tts_client_sync(cfg)
```

When the active override targets a paid provider whose API key is missing,
the factory transparently falls back to Edge with neutral SSML tuning
(see `_fallback_edge_config()`). The fallback emits a structured warning
log (`openai_tts_missing_api_key_falling_back_to_edge` /
`elevenlabs_tts_missing_api_key_falling_back_to_edge`) so operators can
diagnose the missing-key state without losing audio output.

### TTSClient Protocol

```python
# apps/api/src/domains/voice/protocol.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class TTSClient(Protocol):
    """Protocol for TTS clients (duck typing interface)."""

    async def synthesize(
        self,
        text: str,
        voice_name: str,
        **kwargs,
    ) -> bytes:
        """Synthesize text to audio bytes."""
        ...

    async def synthesize_base64(
        self,
        text: str,
        voice_name: str,
        **kwargs,
    ) -> str:
        """Synthesize text to base64-encoded audio."""
        ...

    async def close(self) -> None:
        """Clean up resources."""
        ...

    @property
    def provider_name(self) -> str:
        """TTS provider name (edge, openai, gemini)."""
        ...

    @property
    def audio_format(self) -> str:
        """Audio MIME type (audio/mpeg, audio/wav)."""
        ...
```

### Edge TTS Client (Standard)

```python
from src.domains.voice.client import EdgeTTSClient

# Initialize
client = EdgeTTSClient(
    rate="+10%",
    pitch="+0Hz",
    volume="+0%",
)

# Synthesize
audio_bytes = await client.synthesize(
    text="Bonjour, comment puis-je vous aider ?",
    voice_name="fr-FR-DeniseNeural",
)

# Properties
client.provider_name  # "edge"
client.audio_format   # "audio/mpeg"
```

### OpenAI TTS Client (HD)

```python
from src.domains.voice.openai_tts_client import OpenAITTSClient

# Initialize
client = OpenAITTSClient(
    model="tts-1",
    speed=1.0,
    response_format="mp3",
)

# Synthesize
audio_bytes = await client.synthesize(
    text="Hello, how can I help you today?",
    voice_name="nova",
)

# Properties
client.provider_name  # "openai"
client.audio_format   # "audio/mpeg"
```

### Voice Comment Service

```python
from src.domains.voice.service import VoiceCommentService

service = VoiceCommentService(lia_gender="female")

# Stream voice comment as audio chunks (uses sentence streaming under
# the hood — first audio lands as soon as the LLM emits a complete
# sentence rather than at the end of the full ainvoke).
async for chunk in service.stream_voice_comment(
    context_summary="L'utilisateur a demandé ses emails...",
    personality_instruction="Tu es enthousiaste.",
    user_language="fr",
):
    # chunk is VoiceAudioChunk
    yield chunk
```

### Progressive sentence streaming (ADR-082)

Both code paths above (chat-mode `stream_direct_tts` via
`start_progressive_chat_stream`, and agent-mode `stream_voice_comment`)
are pipelined at the sentence level by ``ProgressiveSentenceStreamer``
([apps/api/src/domains/voice/sentence_streamer.py](../../apps/api/src/domains/voice/sentence_streamer.py)).

```
LLM stream tokens ──► streamer.feed("Bonjour, com")
                       ↓                                   no terminator → buffer
LLM stream tokens ──► streamer.feed("ment ça va ? Au")
                       ↓                                   "? " → dispatch sentence #0
                       ├── asyncio.create_task(synth)  ── ▶ TTS provider call (parallel)
LLM stream tokens ──► streamer.feed("jourd'hui je vais bien.")
                       ↓                                   "." at end → still buffered
LLM closes  ────────► streamer.close_input()
                       ↓                                   trailing buffer → dispatch #1
                       ▼
   in-order delivery via _pending: dict[int, VoiceAudioChunk] + _drain_lock
                       ▼
              audio_chunks() async iterator
                       ▼
            agents SSE main loop emits VoiceAudioChunk
```

A delimiter dispatches only when a **whitespace follows it inside the buffer**
(ADR-154). Two reasons, and they are the same one: a dot glued to the next
character belongs to a token (`3.5`, `12.99`, `1.2.3`, `exemple.fr`), and a dot
sitting at the end of the buffer may simply be one whose next character has not
streamed in yet. `close_input()` flushes whatever never got its space, which is
also the path for an LLM that stops without punctuation.

Four guarantees:

| Invariant | Mechanism |
|---|---|
| A number, a price or a URL is never split across two audio chunks | `[délims]+(?=\s)` — the boundary needs a following whitespace |
| In-order delivery (sentence #1 before #2 even when #2's TTS is faster) | `_pending` map + `_next_emit_idx` counter under `_drain_lock` |
| One sentence failure does NOT block the rest | `_failed: set[int]` skipped during drain |
| End-of-stream sentinel pushed exactly once | `_sentinel_pushed: bool` idempotence flag |

The boundary rule is shared with the one-shot path
(`VoiceCommentService._extract_sentences`) and both are pinned to the same case
table by `tests/unit/domains/voice/test_sentence_boundaries.py`, which also
feeds the text one character at a time — the only way to reproduce a buffer that
ends on a dot.

The resulting **Time-To-First-Audio (TTFA)**:

| Scenario | Legacy v4.0 | v4.1 (sentence streaming) |
|---|---|---|
| Chat mode, response 5 s, 5 sentences | ~5.5 s | **~0.8–1.2 s** |
| Agent mode, voice LLM 2 s, 3 sentences | ~3.5 s | **~1–1.5 s** |
| Agent mode, registry tardif (5 s) | ~6 s | **~3 s** |

### Plain-text input guarantee

The TTS engine must only ever receive **speakable plain text** — never HTML
or CSS. Two complementary mechanisms enforce this:

1. **At the source (response node).** The rich HTML response directive is
   injected only for tool/data turns (router `route_to == "planner"`). A
   conversational turn — whose reply is streamed verbatim to TTS via the
   progressive chat path — is kept in Markdown, so no tags reach the sentence
   streamer. The display mode (`cards` / `html` / `markdown`) is only relevant
   when the turn carries structured data; a plain chat reply is rendered
   identically by the frontend (`ReactMarkdown` + `rehypeRaw`) in every mode.
   See `_should_inject_html_directive`
   ([response_node.py](../../apps/api/src/domains/agents/nodes/response_node.py)).
2. **Defense in depth (agents SSE loop).** The synchronous TTS entry points
   (`stream_direct_tts` and the `stream_voice_comment` fallbacks) pass their
   text through `_sanitize_text_for_tts`
   ([voice_stream_helpers.py](../../apps/api/src/domains/agents/services/streaming/voice_stream_helpers.py)),
   which strips HTML via `html_to_text` **only when markup is actually present** — so
   reference turns or post-LLM data cards are never spoken as tags, while plain
   prose containing bare angle brackets (`x < 5 and y > 3`) is left untouched.

   `html_to_text` drops `<head>`/`<style>`/`<script>` **with their content, closing tag
   or not** (`_BLOCK_ELEMENT_RE` in
   [base.py](../../apps/api/src/domains/agents/display/components/base.py)). The optional
   closing tag matters here as much as on notification surfaces: TTS input can arrive
   truncated, and requiring a complete pair meant a severed `<style>` lost its marker to
   tag-stripping while its body survived — the engine would have read a CSS rule aloud.
   The same stripper backs both surfaces, so a fix on one side is a fix on both; that
   shared path is also why an unrelated icon-ligature bug made the voice say "event"
   before a sentence.

Cleanup contract: every SSE generator exit path (HITL `GraphInterrupt`,
top-level `except`, normal end) MUST tear down the voice pipeline via the
`VoiceStreamCoordinator` (ADR-122 — `cleanup_chat_pipeline()` /
`cleanup()`, backed by `_cleanup_chat_voice_pipeline` in
[voice_stream_helpers.py](../../apps/api/src/domains/agents/services/streaming/voice_stream_helpers.py))
to cancel the drain task, the streamer's pending TTS tasks, and the
underlying voice service (closes the persistent httpx client). The helper
is idempotent and safe to call when voice was never spun up.

### Per-message TTS cost attribution (ADR-081)

Symmetric with STT (cf. [ADR-080](../architecture/ADR-080-Voice-STT-Remote-Pricing-Unit.md)):

```sql
-- conversation_messages — paid TTS only (Edge stays NULL)
tts_provider           VARCHAR(50)
tts_model              VARCHAR(100)
tts_characters         INTEGER
tts_cost_usd           NUMERIC(10,6)
tts_cost_eur           NUMERIC(10,6)
tts_usd_to_eur_rate    NUMERIC(10,6)

-- user_statistics — lifetime + cycle aggregates
total_tts_characters   NUMERIC(12,0) NOT NULL DEFAULT 0
total_tts_cost_eur     NUMERIC(12,6) NOT NULL DEFAULT 0
cycle_tts_characters   NUMERIC(12,0) NOT NULL DEFAULT 0
cycle_tts_cost_eur     NUMERIC(12,6) NOT NULL DEFAULT 0
```

The TTS cost is included in `cycle_cost_eur` / `total_cost_eur` so the
dashboard "Cost" tile and `user_usage_limits` checks naturally cover it.

UI: a discreet badge `🔊 N chars` is rendered before the grand total on
the assistant bubble (mirror of the STT `🎤 X.Xs` badge on the user
bubble). Hidden for Edge synth and historical messages (where the column
is NULL).

CSV exports: `consumption-summary` includes `total_tts_characters`,
`total_tts_cost_eur`. New dedicated `tts-usage` export (admin + user)
returns one row per assistant message with `tts_provider IS NOT NULL`.

#### Backfill double-pass

The TTS finalisation runs AFTER `archive_message` (the assistant row is
created with `tts_*` columns NULL because parallel-mode voice may still
be synthesising at archive time). Two pass-through points:

1. **First pass** — between background-task wait and `cleanup_run_records`,
   `temp_tracker.get_tts_usage_for_archive()` returns the records
   committed by the parallel voice path (PATH 1) and `update_message_tts`
   writes them on `conversation_messages.tts_*`. Captures a snapshot
   `tts_snapshot_for_done` so the SSE `done` chunk metadata can carry
   `tts_provider`/`tts_model`/`tts_characters`/`tts_cost_eur` to the
   live frontend without waiting for a reload.
2. **Second pass** — after the `voice_needs_finalization` block (which
   covers PATH 2A direct_tts / PATH 2B sync voice_comment), `_run_tts_records`
   has been re-populated by `tracker.commit()`. A second backfill picks
   up any records produced by the sync fallback path that wasn't yet
   captured.

---

## Voice Types

### Standard Mode Voices (Edge TTS)

| Language | Female Voice | Male Voice | Quality |
|----------|-------------|------------|---------|
| French (fr-FR) | DeniseNeural | HenriNeural | Neural |
| French (fr-FR) | VivienneMultilingualNeural | RemyMultilingualNeural | **Multilingual** |
| English (en-US) | AriaNeural | GuyNeural | Neural |
| German (de-DE) | KatjaNeural | ConradNeural | Neural |
| Spanish (es-ES) | ElviraNeural | AlvaroNeural | Neural |

### HD Mode Voices (OpenAI)

| Voice | Characteristics | Best For |
|-------|-----------------|----------|
| **alloy** | Neutral, balanced | General use |
| **echo** | Warm, friendly | Conversational |
| **fable** | Expressive, story-like | Narratives |
| **onyx** | Deep, authoritative | Professional |
| **nova** | Warm, engaging | Female persona |
| **shimmer** | Clear, optimistic | Explanations |

---

## Cost Comparison

| Mode | Provider | Cost per 1M chars | Cost per 1K requests* |
|------|----------|-------------------|----------------------|
| **standard** | Edge TTS | **$0.00** | **$0.00** |
| **hd** | OpenAI tts-1 | $15.00 | ~$0.75 |
| **hd** | OpenAI tts-1-hd | $30.00 | ~$1.50 |

\* Assuming 50 chars average per request

---

## Metrics

### Prometheus Metrics

```python
# Voice TTS requests
voice_tts_requests_total{provider="edge|openai|elevenlabs", model="..."}

# Voice TTS latency
voice_tts_latency_seconds{provider="edge|openai|elevenlabs"}

# Voice TTS errors
voice_tts_errors_total{provider="edge|openai|elevenlabs", error_type="..."}
```

The `voice_tts_mode_cache_total  # N'EXISTE PAS ; metriques TTS reelles : voice_tts_requests_total, voice_tts_errors_total, voice_tts_latency_seconds` Prometheus counter was retired with
ADR-081 (no more `voice_tts_mode` system setting). Cache invalidation
for the new override surface is observed through the existing
`llm_config_cache_loaded` log event and the ADR-063 Pub/Sub channel.

---

## Error Handling

### Graceful Degradation

```python
# factory.py — paid provider with missing API key falls back to Edge
def _instantiate_client(cfg: TTSConfig) -> TTSClient:
    if cfg.provider == "openai":
        if not LLMConfigOverrideCache.get_api_key("openai"):
            logger.warning("openai_tts_missing_api_key_falling_back_to_edge")
            return _instantiate_client(_fallback_edge_config())
        return OpenAITTSClient(...)

    if cfg.provider == "elevenlabs":
        if not LLMConfigOverrideCache.get_api_key("elevenlabs"):
            logger.warning("elevenlabs_tts_missing_api_key_falling_back_to_edge")
            return _instantiate_client(_fallback_edge_config())
        return ElevenLabsTTSClient(...)

    if cfg.provider == "edge":
        return EdgeTTSClient(...)

    # Unknown / not-yet-implemented provider (e.g. gemini): Edge fallback
    logger.error("tts_factory_unknown_provider", provider=cfg.provider)
    return _instantiate_client(_fallback_edge_config())
```

### Error Recovery

```python
try:
    audio = await client.synthesize(text, voice_name=voice)
except Exception as e:
    logger.error("tts_synthesis_error", error=str(e))
    # Graceful degradation - continue without voice
    return None
```

---

## Files Structure

```
apps/api/src/domains/voice/
├── __init__.py                # Module exports
├── protocol.py                # TTSClient protocol definition
├── factory.py                 # TTS client factory (LLMConfigOverrideCache-driven)
├── client.py                  # EdgeTTSClient
├── openai_tts_client.py       # OpenAITTSClient
├── elevenlabs_tts_client.py   # ElevenLabsTTSClient (ADR-081)
├── voices_catalog.py          # Edge / OpenAI static lists + ElevenLabs live API
├── admin_router.py            # GET /admin/voice/voices
└── service.py                 # VoiceCommentService
```

---

## Migration History

| Date | Version | Change |
|------|---------|--------|
| 2025-12-24 | 1.0 | Initial implementation avec Google Cloud TTS |
| 2025-12-29 | 2.0 | Migration vers Edge TTS - Gratuit |
| 2026-01-15 | 3.0 | Factory Pattern + Standard/HD modes + Admin System Settings |
| 2026-05-07 | 4.0 | TTS migrated to LLM catalogue (ADR-081) — three providers (Edge / OpenAI / ElevenLabs), `voice_tts` LLM type, voice + tuning in `provider_config` JSONB, `system_settings.voice_tts_mode` retired |
| 2026-05-07 | 4.1 | **Progressive sentence streaming (ADR-082)** — TTFA divided by ~5× (chat mode) / ~2× (agent mode) via `ProgressiveSentenceStreamer` (LLM `astream` → in-order TTS dispatch). Per-message TTS cost attribution (5 cols on `conversation_messages`, 4 aggregates on `user_statistics`, badge `🔊 N chars`). Persistent httpx client on `ElevenLabsTTSClient`. |

---

## Related Documentation

- [ADR-082](../architecture/ADR-082-Progressive-Sentence-Streaming.md) - Progressive sentence streaming (low-latency TTS)
- [ADR-081](../architecture/ADR-081-Voice-TTS-Catalogue-Driven.md) - Voice TTS catalogue-driven architecture
- [ADR-080](../architecture/ADR-080-Voice-STT-Remote-Pricing-Unit.md) - Voice STT remote (ElevenLabs Scribe) + pricing-unit
- [ADR-078](../architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md) - LLM catalogue source of truth
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [AUTHENTICATION.md](./AUTHENTICATION.md) - Admin permissions

---

**VOICE.md** - Version 4.1 - 2026-05-07

*Voice TTS catalogue-driven (ADR-081) + progressive sentence streaming (ADR-082) + per-message cost attribution.*
