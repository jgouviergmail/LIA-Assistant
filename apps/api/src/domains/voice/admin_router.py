"""Admin endpoints for the voice domain.

Currently exposes a single resource: ``GET /admin/voice/voices?provider=X``,
used by the Configuration LLM admin form to populate the voice picker
when the admin selects a TTS provider/model.

Kept in a separate module from the user-facing ``voice.router`` so the
superuser dependency is applied at the router level (defense in depth)
and so admin-only endpoints don't pollute the public-shaped voice
namespace.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.constants import (
    DEFAULT_ELEVENLABS_BASE_URL,
    ELEVENLABS_PROVIDER_NAME,
)
from src.core.exceptions import (
    raise_external_service_fetch_error,
    raise_invalid_input,
)
from src.core.session_dependencies import get_current_superuser_session
from src.domains.auth.models import User
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.voices_catalog import (
    ElevenLabsVoicesError,
    VoiceOption,
    get_edge_voices,
    get_elevenlabs_voices,
    get_openai_voices,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/voice",
    tags=["admin", "voice"],
    dependencies=[Depends(get_current_superuser_session)],
)


VoiceProviderName = Literal["edge", "openai", "elevenlabs"]


class VoiceOptionPayload(BaseModel):
    voice_id: str
    label: str
    gender: str | None = None
    language: str | None = None


class VoicesResponse(BaseModel):
    """Response shape for ``GET /admin/voice/voices``."""

    provider: VoiceProviderName
    voices: list[VoiceOptionPayload]
    source: Literal["static", "live"]


def _to_payload(options: list[VoiceOption]) -> list[VoiceOptionPayload]:
    return [
        VoiceOptionPayload(
            voice_id=o.voice_id,
            label=o.label,
            gender=o.gender,
            language=o.language,
        )
        for o in options
    ]


@router.get(
    "/voices",
    response_model=VoicesResponse,
    summary="List the voice IDs available for a TTS provider",
)
async def list_voices(
    provider: VoiceProviderName = Query(..., description="TTS provider name"),
    current_user: User = Depends(get_current_superuser_session),
) -> VoicesResponse:
    """Return the voice catalogue used by the Configuration LLM voice picker.

    - ``edge`` and ``openai`` return a curated static list (their voice
      sets are stable and well-documented).
    - ``elevenlabs`` triggers a live ``GET /v1/voices`` call against the
      configured account (custom + shared voices are account-scoped). The
      ``voices_read`` scope is required on the API key. A 502 is surfaced
      when the upstream call fails so the UI can show a precise toast.
    """
    if provider == "edge":
        return VoicesResponse(
            provider="edge", voices=_to_payload(get_edge_voices()), source="static"
        )
    if provider == "openai":
        return VoicesResponse(
            provider="openai", voices=_to_payload(get_openai_voices()), source="static"
        )
    if provider == "elevenlabs":
        api_key = LLMConfigOverrideCache.get_api_key(ELEVENLABS_PROVIDER_NAME)
        if not api_key:
            raise_invalid_input(
                "Configure the ElevenLabs API key under "
                "Tarification LLM Texte → Provider Keys before listing voices.",
                error_code="elevenlabs_api_key_missing",
                provider="elevenlabs",
            )
        try:
            voices = await get_elevenlabs_voices(
                api_key=api_key,
                base_url=DEFAULT_ELEVENLABS_BASE_URL,
            )
        except ElevenLabsVoicesError as exc:
            logger.warning(
                "voices_listing_elevenlabs_failed",
                admin_user_id=str(current_user.id),
                error=str(exc),
            )
            raise_external_service_fetch_error(
                service="elevenlabs",
                resource="voices",
                status_code=502,
            )
        return VoicesResponse(provider="elevenlabs", voices=_to_payload(voices), source="live")

    # Defensive: typing ensures this branch is unreachable.
    raise_invalid_input(f"Unsupported provider: {provider}", provider=provider)
