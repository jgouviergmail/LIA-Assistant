"""Provider-specific voice catalogues for the TTS configuration UI.

Returned by the admin endpoint ``GET /admin/voice/voices?provider=X``.
Each entry carries a stable ``voice_id`` (sent verbatim to the provider
when synthesising) plus optional metadata (display label, language tag,
gender hint) used by the dropdown to help the admin pick.

For Edge, OpenAI and Gemini the catalogue is hard-coded — these providers
have fixed, well-known voice sets that almost never change. For ElevenLabs
the live API is queried (``GET /v1/voices``) since custom voice IDs are
account-scoped and impossible to predict; where a voice is offered to a person
or checked before LIA speaks with it, that list is read from a cache
(:func:`get_cached_elevenlabs_voices`), which a voice list of any live engine
encodes the same way (:func:`encode_voice_options`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import httpx
import structlog
from redis.exceptions import RedisError

from src.core.constants import (
    ELEVENLABS_VOICES_CACHE_TTL_SECONDS,
    REDIS_KEY_ELEVENLABS_VOICES_PREFIX,
)
from src.domains.voice.vendor_refusal import ELEVENLABS_CODE_PATHS, refusal_from_body
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


@dataclass
class VoiceOption:
    """One voice exposed to the admin UI."""

    voice_id: str
    label: str
    gender: str | None = None  # "male" | "female" | None (neutral / unknown)
    language: str | None = None  # ISO-639-1 hint, when applicable
    extra: dict[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Edge TTS — Microsoft multilingual neural voices.
# Curated subset over the LIA-supported languages (en/fr/de/es/it/zh).
# ----------------------------------------------------------------------

_EDGE_VOICES: tuple[VoiceOption, ...] = (
    # Multilingual (neural, recommended for cross-language assistant).
    VoiceOption("fr-FR-RemyMultilingualNeural", "Rémy (multilingual, FR)", "male", "fr"),
    VoiceOption("fr-FR-VivienneMultilingualNeural", "Vivienne (multilingual, FR)", "female", "fr"),
    # French (FR + Canada).
    VoiceOption("fr-FR-HenriNeural", "Henri", "male", "fr"),
    VoiceOption("fr-FR-DeniseNeural", "Denise", "female", "fr"),
    VoiceOption("fr-CA-AntoineNeural", "Antoine (CA)", "male", "fr"),
    VoiceOption("fr-CA-SylvieNeural", "Sylvie (CA)", "female", "fr"),
    # English.
    VoiceOption("en-US-GuyNeural", "Guy (US)", "male", "en"),
    VoiceOption("en-US-AriaNeural", "Aria (US)", "female", "en"),
    VoiceOption("en-GB-RyanNeural", "Ryan (UK)", "male", "en"),
    VoiceOption("en-GB-SoniaNeural", "Sonia (UK)", "female", "en"),
    # German.
    VoiceOption("de-DE-ConradNeural", "Conrad", "male", "de"),
    VoiceOption("de-DE-KatjaNeural", "Katja", "female", "de"),
    # Spanish.
    VoiceOption("es-ES-AlvaroNeural", "Álvaro", "male", "es"),
    VoiceOption("es-ES-ElviraNeural", "Elvira", "female", "es"),
    # Italian.
    VoiceOption("it-IT-DiegoNeural", "Diego", "male", "it"),
    VoiceOption("it-IT-ElsaNeural", "Elsa", "female", "it"),
    # Chinese (Mandarin).
    VoiceOption("zh-CN-YunxiNeural", "Yunxi", "male", "zh"),
    VoiceOption("zh-CN-XiaoxiaoNeural", "Xiaoxiao", "female", "zh"),
)


# ----------------------------------------------------------------------
# OpenAI TTS — fixed 6 voices for tts-1 / tts-1-hd.
# Gender labels are intentional approximations; OpenAI does not officially
# label voices with gender, but the admin form benefits from the hint.
# ----------------------------------------------------------------------

_OPENAI_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("alloy", "Alloy (neutral)", None),
    VoiceOption("echo", "Echo", "male"),
    VoiceOption("fable", "Fable", "male"),
    VoiceOption("onyx", "Onyx", "male"),
    VoiceOption("nova", "Nova", "female"),
    VoiceOption("shimmer", "Shimmer", "female"),
    VoiceOption("coral", "Coral", "female"),
)


# ----------------------------------------------------------------------
# Gemini TTS — the 30 prebuilt voices, every one multilingual (the model
# detects the language from the text). Genders as Google's own Chirp 3 HD
# voice table states them for the same names (read 2026-09-26); the label
# carries the descriptor Google publishes for each voice.
# ----------------------------------------------------------------------

_GEMINI_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("Achernar", "Achernar (soft)", "female"),
    VoiceOption("Achird", "Achird (friendly)", "male"),
    VoiceOption("Algenib", "Algenib (gravelly)", "male"),
    VoiceOption("Algieba", "Algieba (smooth)", "male"),
    VoiceOption("Alnilam", "Alnilam (firm)", "male"),
    VoiceOption("Aoede", "Aoede (breezy)", "female"),
    VoiceOption("Autonoe", "Autonoe (bright)", "female"),
    VoiceOption("Callirrhoe", "Callirrhoe (easy-going)", "female"),
    VoiceOption("Charon", "Charon (informative)", "male"),
    VoiceOption("Despina", "Despina (smooth)", "female"),
    VoiceOption("Enceladus", "Enceladus (breathy)", "male"),
    VoiceOption("Erinome", "Erinome (clear)", "female"),
    VoiceOption("Fenrir", "Fenrir (excitable)", "male"),
    VoiceOption("Gacrux", "Gacrux (mature)", "female"),
    VoiceOption("Iapetus", "Iapetus (clear)", "male"),
    VoiceOption("Kore", "Kore (firm)", "female"),
    VoiceOption("Laomedeia", "Laomedeia (upbeat)", "female"),
    VoiceOption("Leda", "Leda (youthful)", "female"),
    VoiceOption("Orus", "Orus (firm)", "male"),
    VoiceOption("Puck", "Puck (upbeat)", "male"),
    VoiceOption("Pulcherrima", "Pulcherrima (forward)", "female"),
    VoiceOption("Rasalgethi", "Rasalgethi (informative)", "male"),
    VoiceOption("Sadachbia", "Sadachbia (lively)", "male"),
    VoiceOption("Sadaltager", "Sadaltager (knowledgeable)", "male"),
    VoiceOption("Schedar", "Schedar (even)", "male"),
    VoiceOption("Sulafat", "Sulafat (warm)", "female"),
    VoiceOption("Umbriel", "Umbriel (easy-going)", "male"),
    VoiceOption("Vindemiatrix", "Vindemiatrix (gentle)", "female"),
    VoiceOption("Zephyr", "Zephyr (bright)", "female"),
    VoiceOption("Zubenelgenubi", "Zubenelgenubi (casual)", "male"),
)


def encode_voice_options(voices: Sequence[VoiceOption]) -> str:
    """A voice list as a cache holds it: every field of each option."""
    return json.dumps(
        [
            {
                "voice_id": voice.voice_id,
                "label": voice.label,
                "gender": voice.gender,
                "language": voice.language,
                "extra": voice.extra,
            }
            for voice in voices
        ]
    )


def decode_voice_options(raw: str | bytes) -> list[VoiceOption] | None:
    """A cached voice list, or ``None`` when it cannot be read (it is then no cache)."""
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return None  # an object is no list: read as no voice at all, it would hide every one
        return [
            VoiceOption(
                voice_id=str(item["voice_id"]),
                label=str(item["label"]),
                gender=item.get("gender"),
                language=item.get("language"),
                extra={str(k): str(v) for k, v in (item.get("extra") or {}).items()},
            )
            for item in items
        ]
    except ValueError, TypeError, KeyError, AttributeError:
        return None


async def cached_voice_list(key: str) -> list[VoiceOption] | None:
    """A voice list a cache holds, or ``None``: none held, unreadable, or no cache reachable."""
    try:
        redis = await get_redis_cache()
        cached = await redis.get(key)
    except RedisError, OSError:
        return None
    return decode_voice_options(cached) if cached is not None else None


async def keep_voice_list(
    key: str, voices: Sequence[VoiceOption], ttl_seconds: int, *, catalogue: str
) -> None:
    """Cache a voice list — best effort: a list Redis cannot keep is listed again next time."""
    try:
        redis = await get_redis_cache()
        await redis.set(key, encode_voice_options(voices), ex=ttl_seconds)
    except RedisError, OSError:
        logger.debug("voice_list_cache_write_failed", catalogue=catalogue)


def get_edge_voices() -> list[VoiceOption]:
    return list(_EDGE_VOICES)


def get_openai_voices() -> list[VoiceOption]:
    return list(_OPENAI_VOICES)


def get_gemini_voices() -> list[VoiceOption]:
    return list(_GEMINI_VOICES)


async def get_elevenlabs_voices(
    api_key: str, base_url: str, timeout: float = 15.0
) -> list[VoiceOption]:
    """Live fetch of the ElevenLabs voice catalogue.

    Uses ``GET /v1/voices`` which returns custom + shared voices for the
    authenticated account. The API key needs the ``voices_read`` permission.

    Failures (HTTP error, missing key, malformed payload) raise
    :class:`ElevenLabsVoicesError` so the router can surface a clean
    400/502 response instead of an opaque 500 — by their facts, never the
    vendor's words (ADR-317).
    """
    if not api_key:
        raise ElevenLabsVoicesError("ElevenLabs API key is not configured.")

    url = f"{base_url.rstrip('/')}/voices"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers={"xi-api-key": api_key})
    except httpx.TimeoutException as exc:
        raise ElevenLabsVoicesError(
            "ElevenLabs voices request timed out",
            details={"exception_type": type(exc).__name__},
        ) from exc
    except httpx.HTTPError as exc:
        raise ElevenLabsVoicesError(
            "ElevenLabs voices HTTP error", details={"exception_type": type(exc).__name__}
        ) from exc

    if response.status_code >= 400:
        refusal = refusal_from_body(response, *ELEVENLABS_CODE_PATHS)
        message = (
            "ElevenLabs API key lacks the ``voices_read`` permission "
            "(or is otherwise rejected). Re-issue a key with that scope."
            if refusal.status == 401
            else f"ElevenLabs returned HTTP {refusal.status}"
        )
        raise ElevenLabsVoicesError(message, details=refusal.details())

    try:
        payload = response.json()
        raw_voices = payload.get("voices", [])
    except ValueError as exc:
        raise ElevenLabsVoicesError("ElevenLabs voices response is not valid JSON.") from exc

    voices: list[VoiceOption] = []
    for v in raw_voices:
        voice_id = v.get("voice_id")
        name = v.get("name") or voice_id
        if not voice_id:
            continue
        labels = v.get("labels") or {}
        gender = labels.get("gender") if isinstance(labels, dict) else None
        # Normalise gender to the same vocabulary as Edge/OpenAI catalogues.
        if gender:
            gender_lower = gender.lower()
            gender = (
                "female"
                if "female" in gender_lower
                else ("male" if "male" in gender_lower else None)
            )
        voices.append(
            VoiceOption(
                voice_id=voice_id,
                label=str(name),
                gender=gender,
                language=labels.get("language") if isinstance(labels, dict) else None,
                extra={"category": str(v.get("category", ""))},
            )
        )
    # Stable ordering so the dropdown is predictable across reloads.
    voices.sort(key=lambda x: (x.gender or "z", x.label.lower()))
    return voices


def _elevenlabs_cache_key(api_key: str) -> str:
    # A digest of the account, never the credential.
    return f"{REDIS_KEY_ELEVENLABS_VOICES_PREFIX}{hashlib.sha256(api_key.encode()).hexdigest()}"


async def get_cached_elevenlabs_voices(api_key: str, base_url: str) -> list[VoiceOption]:
    """The account's ElevenLabs voices, from cache when it holds them.

    Read where a voice is offered to a person or checked before LIA speaks with
    it; the administrator's picker reads the vendor live, so a voice added on
    the vendor's portal shows there at once and here within
    ``ELEVENLABS_VOICES_CACHE_TTL_SECONDS``. Best effort: an unreachable cache
    reads the vendor.

    Args:
        api_key: The account's key.
        base_url: The vendor's API root.

    Returns:
        The voices, as :func:`get_elevenlabs_voices` lists them.

    Raises:
        ElevenLabsVoicesError: When the vendor cannot be read and nothing is cached.
    """
    key = _elevenlabs_cache_key(api_key)
    voices = await cached_voice_list(key)
    if voices is not None:
        return voices
    voices = await get_elevenlabs_voices(api_key=api_key, base_url=base_url)
    await keep_voice_list(key, voices, ELEVENLABS_VOICES_CACHE_TTL_SECONDS, catalogue="elevenlabs")
    return voices


async def peek_elevenlabs_voices(api_key: str) -> list[VoiceOption] | None:
    """The account's ElevenLabs voices as the cache holds them — the vendor is never asked.

    Args:
        api_key: The account's key.

    Returns:
        The cached list, or ``None`` when none is cached.
    """
    return await cached_voice_list(_elevenlabs_cache_key(api_key))


class ElevenLabsVoicesError(RuntimeError):
    """The ElevenLabs voices listing failed (its facts in ``details``).

    Attributes:
        details: The status and bounded vendor code of a refusal, or the type of
            a transport failure — never the vendor's words.
    """

    def __init__(self, message: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})
