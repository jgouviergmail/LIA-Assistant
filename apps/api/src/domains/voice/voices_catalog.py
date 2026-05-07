"""Provider-specific voice catalogues for the TTS configuration UI.

Returned by the admin endpoint ``GET /admin/voice/voices?provider=X``.
Each entry carries a stable ``voice_id`` (sent verbatim to the provider
when synthesising) plus optional metadata (display label, language tag,
gender hint) used by the dropdown to help the admin pick.

For Edge and OpenAI the catalogue is hard-coded — both providers have
fixed, well-known voice sets that almost never change. For ElevenLabs
the live API is queried (``GET /v1/voices``) since custom voice IDs are
account-scoped and impossible to predict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


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


def get_edge_voices() -> list[VoiceOption]:
    return list(_EDGE_VOICES)


def get_openai_voices() -> list[VoiceOption]:
    return list(_OPENAI_VOICES)


async def get_elevenlabs_voices(
    api_key: str, base_url: str, timeout: float = 15.0
) -> list[VoiceOption]:
    """Live fetch of the ElevenLabs voice catalogue.

    Uses ``GET /v1/voices`` which returns custom + shared voices for the
    authenticated account. The API key needs the ``voices_read`` permission.

    Failures (HTTP error, missing key, malformed payload) raise
    :class:`ElevenLabsVoicesError` so the router can surface a clean
    400/502 response instead of an opaque 500.
    """
    if not api_key:
        raise ElevenLabsVoicesError("ElevenLabs API key is not configured.")

    url = f"{base_url.rstrip('/')}/voices"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers={"xi-api-key": api_key})
    except httpx.TimeoutException as exc:
        raise ElevenLabsVoicesError(f"ElevenLabs voices request timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ElevenLabsVoicesError(f"ElevenLabs voices HTTP error: {exc}") from exc

    if response.status_code == 401:
        raise ElevenLabsVoicesError(
            "ElevenLabs API key lacks the ``voices_read`` permission "
            "(or is otherwise rejected). Re-issue a key with that scope."
        )
    if response.status_code >= 400:
        raise ElevenLabsVoicesError(
            f"ElevenLabs returned HTTP {response.status_code}: {response.text[:200]}"
        )

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


class ElevenLabsVoicesError(RuntimeError):
    """Raised when the ElevenLabs voices listing call fails."""
