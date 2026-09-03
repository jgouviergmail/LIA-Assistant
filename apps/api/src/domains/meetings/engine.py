"""Which engine transcribes a meeting — decided BEFORE recording, shown to the user (ADR-258).

Resolution order for ``auto``: the provider of the admin ``voice_transcription``
slot when it has a key, then every other remote provider with a key in the
fallback order, then the local Whisper engine when speech-to-text is enabled.
``remote`` refuses to fall back to local; ``local`` never calls a provider.

Nothing here talks to a network: the decision reads the provider-key cache,
the settings and the pricing cache, so it is cheap enough to run at start (the
user sees engine and cost before the first second is captured) and again at
claim time (the truth at processing time wins).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.core.config import settings
from src.core.constants import (
    DEFAULT_ELEVENLABS_STT_MODEL,
    ELEVENLABS_PROVIDER_NAME,
    OPENAI_PROVIDER_NAME,
    OPENAI_STT_DIARIZE_MODEL_DEFAULT,
    STT_PROVIDER_FALLBACK_ORDER,
)
from src.core.llm_config_helper import merge_config
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.meetings.models import MeetingSttEnginePreference, MeetingSttProvider
from src.infrastructure.cache.pricing_cache import get_cached_cost_audio_usd_eur

logger = structlog.get_logger(__name__)

_PROVIDER_ENUM = {
    ELEVENLABS_PROVIDER_NAME: MeetingSttProvider.ELEVENLABS,
    OPENAI_PROVIDER_NAME: MeetingSttProvider.OPENAI,
}


@dataclass(frozen=True)
class ResolvedEngine:
    """The engine a meeting will use. ``api_key`` never reaches a log or a response."""

    provider: MeetingSttProvider
    model: str | None
    diarized: bool
    api_key: str | None
    cost_per_hour_eur: float | None
    local_rtf_estimate: float | None

    @property
    def is_remote(self) -> bool:
        return self.provider is not MeetingSttProvider.LOCAL


def _slot_provider_and_model() -> tuple[str, str]:
    """Provider + model of the admin ``voice_transcription`` slot (override or default)."""
    defaults = LLM_DEFAULTS["voice_transcription"]
    overrides = LLMConfigOverrideCache.get_override("voice_transcription") or {}
    effective = merge_config(defaults, overrides)
    return str(effective.provider), str(effective.model)


def _remote_model_for(provider: str, slot_provider: str, slot_model: str) -> str:
    """The slot's model when the slot names this provider, else the provider default."""
    if provider == slot_provider and slot_model:
        return slot_model
    if provider == OPENAI_PROVIDER_NAME:
        return OPENAI_STT_DIARIZE_MODEL_DEFAULT
    return DEFAULT_ELEVENLABS_STT_MODEL


def _provider_enabled(provider: str) -> bool:
    """Deployment kill switches per provider (ElevenLabs has one; OpenAI none)."""
    if provider == ELEVENLABS_PROVIDER_NAME:
        return bool(settings.elevenlabs_stt_enabled)
    return True


def _cost_per_hour_eur(model: str) -> float | None:
    """Administered price per audio hour, or ``None`` when no pricing row exists."""
    _usd, eur = get_cached_cost_audio_usd_eur(model, 3600.0)
    return round(eur, 4) if eur > 0 else None


def _remote_candidates() -> list[str]:
    """Slot provider first, then the fallback order, without duplicates."""
    slot_provider, _ = _slot_provider_and_model()
    candidates: list[str] = []
    for provider in (slot_provider, *STT_PROVIDER_FALLBACK_ORDER):
        if provider in _PROVIDER_ENUM and provider not in candidates:
            candidates.append(provider)
    return candidates


def _first_remote(exclude: frozenset[MeetingSttProvider]) -> ResolvedEngine | None:
    slot_provider, slot_model = _slot_provider_and_model()
    for provider in _remote_candidates():
        if not _provider_enabled(provider) or _PROVIDER_ENUM[provider] in exclude:
            continue
        api_key = LLMConfigOverrideCache.get_api_key(provider)
        if not api_key:
            continue
        model = _remote_model_for(provider, slot_provider, slot_model)
        return ResolvedEngine(
            provider=_PROVIDER_ENUM[provider],
            model=model,
            diarized=True,
            api_key=api_key,
            cost_per_hour_eur=_cost_per_hour_eur(model),
            local_rtf_estimate=None,
        )
    return None


def _local(exclude: frozenset[MeetingSttProvider]) -> ResolvedEngine | None:
    if not settings.voice_stt_enabled or MeetingSttProvider.LOCAL in exclude:
        return None
    return ResolvedEngine(
        provider=MeetingSttProvider.LOCAL,
        model=None,
        diarized=False,
        api_key=None,
        cost_per_hour_eur=None,
        local_rtf_estimate=float(settings.meetings_local_rtf_estimate),
    )


def resolve_engine(
    preference: MeetingSttEnginePreference,
    *,
    exclude: frozenset[MeetingSttProvider] = frozenset(),
) -> ResolvedEngine | None:
    """The engine for ``preference``, or ``None`` when nothing can transcribe.

    Args:
        preference: The user's choice (``auto`` / ``remote`` / ``local``).
        exclude: Providers already tried on this meeting (a permanent fault such
            as a refused key) — the chain continues past them.

    Returns:
        The resolved engine, or ``None`` — the caller refuses the start with an
        explicit ``no_engine_available`` so the user learns it before recording.
    """
    if preference is MeetingSttEnginePreference.LOCAL:
        engine = _local(exclude)
    elif preference is MeetingSttEnginePreference.REMOTE:
        engine = _first_remote(exclude)
    else:
        engine = _first_remote(exclude) or _local(exclude)
    logger.debug(
        "meeting_engine_resolved",
        preference=preference.value,
        provider=engine.provider.value if engine else None,
        model=engine.model if engine else None,
    )
    return engine
