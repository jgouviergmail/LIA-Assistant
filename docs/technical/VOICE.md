# Voice / Text-to-Speech (TTS)

> **Technical Documentation** - Voice Synthesis Domain
>
> **Version**: 3.1
> **Date**: 2026-01-22
> **Updated**: Architecture Factory Pattern avec Standard/HD modes + Admin System Settings
>
> Related: [ARCHITECTURE.md](../ARCHITECTURE.md) | [SMART_SERVICES.md](./SMART_SERVICES.md)

---

## Overview

Le domaine Voice fournit une intégration multi-provider TTS avec deux modes contrôlés par l'admin :

- **Standard Mode** : Edge TTS (Microsoft Neural voices - GRATUIT)
- **HD Mode** : OpenAI/Gemini TTS (Premium quality - PAYANT)

### Key Features

- **Factory Pattern** : Abstraction provider via TTSClient protocol
- **Admin-Controlled** : Mode TTS contrôlé via System Settings (superuser only)
- **Multi-Provider** : Edge TTS (gratuit) + OpenAI TTS (premium)
- **Per-User Preference** : Voice enabled/disabled par utilisateur
- **Streaming** : Génération audio par chunks pour faible latence
- **Graceful Degradation** : Fallback vers Standard si HD non disponible

### Modes TTS

| Mode | Provider | Coût | Qualité | Contrôle |
|------|----------|------|---------|----------|
| **standard** | Edge TTS | Gratuit | Haute (Neural) | Admin via System Settings |
| **hd** | OpenAI TTS | $15-30/1M chars | Premium | Admin via System Settings |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VOICE DOMAIN (v3)                                │
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
│  │                    FACTORY LAYER (NEW)                              │ │
│  │                                                                      │ │
│  │   factory.py                                                        │ │
│  │   ├── get_tts_client()         # Returns TTSClient based on mode   │ │
│  │   ├── get_tts_config()         # Returns TTSConfig for mode        │ │
│  │   ├── get_voice_mode()         # Reads mode from cache/DB          │ │
│  │   └── get_available_modes()    # Lists available modes for admin   │ │
│  │                                                                      │ │
│  │   TTSConfig(dataclass)                                              │ │
│  │   ├── mode: "standard" | "hd"                                       │ │
│  │   ├── provider: "edge" | "openai" | "gemini"                        │ │
│  │   ├── voice_male, voice_female                                      │ │
│  │   ├── rate, pitch, volume (Standard)                                │ │
│  │   └── model, speed, response_format (HD)                            │ │
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

## Admin Control: System Settings

Le mode TTS est contrôlé par l'administrateur via le domaine System Settings.

### Endpoints

```bash
# GET mode actuel
GET /api/v1/admin/system-settings/voice-mode
Authorization: Bearer <admin_token>

# Response:
{
  "mode": "standard",
  "updated_by": null,
  "updated_at": null,
  "is_default": true
}

# Changer le mode (superuser only)
PUT /api/v1/admin/system-settings/voice-mode
Authorization: Bearer <admin_token>
{
  "mode": "hd",
  "change_reason": "Premium quality enabled for all users"
}

# Response:
{
  "mode": "hd",
  "updated_by": "550e8400-e29b-41d4-a716-446655440000",
  "updated_at": "2026-01-16T10:30:00Z",
  "is_default": false
}
```

### Architecture Cache

```
Admin Request
     │
     ▼
SystemSettingsService.set_voice_tts_mode()
     │
     ├── Update PostgreSQL (SystemSetting table)
     ├── Create AdminAuditLog entry
     └── invalidate_voice_tts_mode_cache()
                    │
                    ▼
             Redis DELETE
                    │
                    ▼
          Next request:
          get_voice_tts_mode()
                    │
                    ├── Redis Cache miss
                    │         ↓
                    ├── PostgreSQL query
                    │         ↓
                    └── Redis Cache set (5min TTL)
```

---

## Configuration

### Environment Variables

```bash
# .env

# ===== VOICE FEATURE =====
VOICE_TTS_ENABLED=true
VOICE_TTS_DEFAULT_MODE=standard      # "standard" | "hd"

# ===== STANDARD MODE (Edge TTS - GRATUIT) =====
VOICE_TTS_STANDARD_PROVIDER=edge
VOICE_TTS_STANDARD_VOICE_MALE=fr-FR-HenriNeural
VOICE_TTS_STANDARD_VOICE_FEMALE=fr-FR-DeniseNeural
VOICE_TTS_STANDARD_RATE=+10%        # Speaking rate: "+10%", "-5%", "+0%"
VOICE_TTS_STANDARD_PITCH=+0Hz       # Pitch: "+5Hz", "-10Hz", "+0Hz"
VOICE_TTS_STANDARD_VOLUME=+0%       # Volume: "+10%", "-5%", "+0%"

# ===== HD MODE (OpenAI TTS - PAYANT) =====
VOICE_TTS_HD_PROVIDER=openai         # "openai" | "gemini"
VOICE_TTS_HD_MODEL=tts-1             # tts-1 ($15/1M) ou tts-1-hd ($30/1M)
VOICE_TTS_HD_VOICE_MALE=onyx
VOICE_TTS_HD_VOICE_FEMALE=nova
VOICE_TTS_HD_SPEED=1.0               # 0.25 to 4.0
VOICE_TTS_HD_RESPONSE_FORMAT=mp3     # mp3, opus, aac, flac, wav, pcm

# ===== VOICE COMMENT LLM =====
VOICE_LLM_PROVIDER=openai
VOICE_LLM_MODEL=gpt-4.1-nano
VOICE_LLM_TEMPERATURE=0.7
VOICE_LLM_MAX_TOKENS=500
VOICE_MAX_SENTENCES=6

# ===== VOICE CONTEXT =====
VOICE_CONTEXT_MAX_CHARS=2000
VOICE_PARALLEL_TIMEOUT_SECONDS=10.0
```

### Settings Class

```python
# apps/api/src/core/config/voice.py

VoiceTTSMode = Literal["standard", "hd"]

class VoiceSettings(BaseSettings):
    """Voice/TTS configuration with Standard/HD modes."""

    # Feature flag
    voice_tts_enabled: bool = True
    voice_tts_default_mode: VoiceTTSMode = "standard"

    # Standard mode (Edge TTS - FREE)
    voice_tts_standard_provider: str = "edge"
    voice_tts_standard_voice_male: str = "fr-FR-HenriNeural"
    voice_tts_standard_voice_female: str = "fr-FR-DeniseNeural"
    voice_tts_standard_rate: str = "+10%"
    voice_tts_standard_pitch: str = "+0Hz"
    voice_tts_standard_volume: str = "+0%"

    # HD mode (OpenAI/Gemini - PAID)
    voice_tts_hd_provider: str = "openai"
    voice_tts_hd_model: str = "tts-1"
    voice_tts_hd_voice_male: str = "onyx"
    voice_tts_hd_voice_female: str = "nova"
    voice_tts_hd_speed: float = 1.0
    voice_tts_hd_response_format: str = "mp3"

    # Voice Comment LLM
    voice_llm_provider: str = "openai"
    voice_llm_model: str = "gpt-4.1-nano"
    voice_llm_temperature: float = 0.7
    voice_llm_max_tokens: int = 500
    voice_max_sentences: int = 6
```

---

## Usage

### Factory Pattern

```python
from src.domains.voice.factory import get_tts_client, get_tts_config, get_voice_mode

# Get current mode from cache/DB
mode = await get_voice_mode()  # "standard" | "hd"

# Get client based on current admin mode
client = await get_tts_client()
audio = await client.synthesize("Bonjour!", voice_name="nova")

# Force specific mode (for testing)
client = await get_tts_client(mode="hd")

# Get configuration for UI
config = await get_tts_config()
# config.mode = "hd"
# config.provider = "openai"
# config.voice_male = "onyx"
# config.voice_female = "nova"
```

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

# Stream voice comment as audio chunks
async for chunk in service.stream_voice_comment(
    context_summary="L'utilisateur a demandé ses emails...",
    personality_instruction="Tu es enthousiaste.",
    user_language="fr",
):
    # chunk is VoiceAudioChunk
    yield chunk
```

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
voice_tts_requests_total{provider="edge|openai", status="success|error"}

# Voice TTS latency
voice_tts_latency_seconds{provider="edge|openai"}

# Voice TTS errors
voice_tts_errors_total{provider="edge|openai", error_type="..."}

# Voice mode cache
voice_tts_mode_cache_total{result="hit|miss|error"}
```

---

## Error Handling

### Graceful Degradation

```python
# factory.py - HD mode fallback to Standard
async def _create_hd_client() -> TTSClient:
    provider = settings.voice_tts_hd_provider

    if provider == "openai":
        if not settings.openai_api_key:
            logger.warning("openai_tts_no_api_key", message="Falling back to Standard")
            return _create_standard_client()

        return OpenAITTSClient(...)

    # Unknown provider: fallback
    return _create_standard_client()
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
├── __init__.py           # Module exports
├── protocol.py           # TTSClient protocol definition
├── factory.py            # TTS client factory (Standard/HD)
├── client.py             # EdgeTTSClient (Standard mode)
├── openai_tts_client.py  # OpenAITTSClient (HD mode)
└── service.py            # VoiceCommentService
```

---

## Migration History

| Date | Version | Change |
|------|---------|--------|
| 2025-12-24 | 1.0 | Initial implementation avec Google Cloud TTS |
| 2025-12-29 | 2.0 | Migration vers Edge TTS - Gratuit |
| 2026-01-15 | 3.0 | **Factory Pattern + Standard/HD modes + Admin System Settings** |

---

## Related Documentation

- [SMART_SERVICES.md](./SMART_SERVICES.md) - SystemSettingsService
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [AUTHENTICATION.md](./AUTHENTICATION.md) - Admin permissions

---

**VOICE.md** - Version 3.0 - Janvier 2026

*Voice TTS System with Factory Pattern and Admin-Controlled Standard/HD Modes*
