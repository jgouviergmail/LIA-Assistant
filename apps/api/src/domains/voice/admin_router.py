"""Admin endpoints for the voice domain.

Exposes ``GET /admin/voice/voices?provider=X``, used by the Configuration LLM
admin form to populate the voice picker when the admin selects a TTS
provider/model, and ``GET /admin/voice/fishaudio/voices/{voice_id}``, which
reads one Fish Audio library voice before the form offers to pin it (ADR-345).

Kept in a separate module from the user-facing ``voice.router`` so admin-only
endpoints don't pollute the public-shaped voice namespace. Both endpoints wait
on a vendor — a live catalogue, one library voice — so each authenticates on a
session of its own, closed before the vendor is asked (ADR-304): a request
session would hold a PostgreSQL backend ``idle in transaction`` across the
listing. The superuser check is therefore a CALL in each endpoint, as in the
voice library's router.
"""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.constants import (
    DEFAULT_ELEVENLABS_BASE_URL,
    ELEVENLABS_PROVIDER_NAME,
    FISHAUDIO_PROVIDER_NAME,
)
from src.core.exceptions import (
    raise_external_service_fetch_error,
    raise_invalid_input,
    raise_structured_validation_error,
)
from src.core.security.authorization import require_superuser
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.users.models import User
from src.domains.voice.fishaudio.pins import read_pins
from src.domains.voice.fishaudio.voices import (
    VOICE_ID_PATTERN,
    FishVoicesError,
    fetch_fish_voice,
    get_fish_voices,
)
from src.domains.voice.schemas import VoiceOptionPayload, voice_option_payloads
from src.domains.voice.voices_catalog import (
    ElevenLabsVoicesError,
    get_edge_voices,
    get_elevenlabs_voices,
    get_gemini_voices,
    get_openai_voices,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/voice", tags=["admin", "voice"])

Administrator = Annotated[User, Depends(get_current_active_session_for_stream)]


VoiceProviderName = Literal["edge", "openai", "elevenlabs", "gemini", "fishaudio"]


class VoicesResponse(BaseModel):
    """Response shape for ``GET /admin/voice/voices``."""

    provider: VoiceProviderName
    voices: list[VoiceOptionPayload]
    source: Literal["static", "live"]


def _fish_api_key() -> str:
    api_key = LLMConfigOverrideCache.get_api_key(FISHAUDIO_PROVIDER_NAME)
    if not api_key:
        raise_invalid_input(
            "Configure the Fish Audio API key under Provider Keys before listing voices.",
            error_code="fishaudio_api_key_missing",
            provider=FISHAUDIO_PROVIDER_NAME,
        )
    return api_key


def _refuse_malformed_voice_id(voice_id: str) -> None:
    if not VOICE_ID_PATTERN.fullmatch(voice_id):
        raise_structured_validation_error(
            error_type="fishaudio_voice_id_malformed",
            loc=["path", "voice_id"],
            msg="A Fish Audio voice id is 32 lowercase hexadecimal characters.",
            input_value=voice_id,
            ctx={"voice_id": voice_id},
        )


@router.get(
    "/voices",
    response_model=VoicesResponse,
    summary="List the voice IDs available for a TTS provider",
)
async def list_voices(
    current_user: Administrator,
    provider: VoiceProviderName = Query(..., description="TTS provider name"),
) -> VoicesResponse:
    """Return the voice catalogue used by the Configuration LLM voice picker.

    - ``edge``, ``openai`` and ``gemini`` return a curated static list
      (their voice sets are stable and well-documented).
    - ``elevenlabs`` triggers a live ``GET /v1/voices`` call against the
      configured account (custom + shared voices are account-scoped). The
      ``voices_read`` scope is required on the API key. A 502 is surfaced
      when the upstream call fails so the UI can show a precise toast.
    - ``fishaudio`` lists the account's own voices, the public ones the
      instance pinned for every voice slot and the vendor's licensed ones
      (ADR-345), each marked by source.
    """
    require_superuser(current_user, "list the voices of a TTS provider")
    if provider == "edge":
        return VoicesResponse(
            provider="edge", voices=voice_option_payloads(get_edge_voices()), source="static"
        )
    if provider == "openai":
        return VoicesResponse(
            provider="openai", voices=voice_option_payloads(get_openai_voices()), source="static"
        )
    if provider == "gemini":
        return VoicesResponse(
            provider="gemini", voices=voice_option_payloads(get_gemini_voices()), source="static"
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
            # Its facts, never its prose (ADR-317).
            logger.warning(
                "voices_listing_elevenlabs_failed",
                admin_user_id=str(current_user.id),
                status_code=exc.details.get("status_code"),
                vendor_code=exc.details.get("vendor_code"),
                exception_type=exc.details.get("exception_type"),
            )
            raise_external_service_fetch_error(
                service="elevenlabs",
                resource="voices",
                status_code=502,
            )
        return VoicesResponse(
            provider="elevenlabs", voices=voice_option_payloads(voices), source="live"
        )
    if provider == "fishaudio":
        api_key = _fish_api_key()
        pins = await read_pins()
        try:
            fish_voices = await get_fish_voices(api_key, pins)
        except FishVoicesError as exc:
            # Its facts, never its prose (ADR-317).
            logger.warning(
                "voices_listing_fishaudio_failed",
                admin_user_id=str(current_user.id),
                status_code=exc.details.get("status_code"),
                vendor_code=exc.details.get("vendor_code"),
            )
            raise_external_service_fetch_error(
                service=FISHAUDIO_PROVIDER_NAME, resource="voices", status_code=502
            )
        return VoicesResponse(
            provider="fishaudio", voices=voice_option_payloads(fish_voices), source="live"
        )

    # Defensive: typing ensures this branch is unreachable.
    raise_invalid_input(f"Unsupported provider: {provider}", provider=provider)


@router.get(
    "/fishaudio/voices/{voice_id}",
    response_model=VoiceOptionPayload,
    summary="Read one Fish Audio library voice before pinning it",
)
async def get_fish_voice(voice_id: str, current_user: Administrator) -> VoiceOptionPayload:
    """One public voice of the vendor's library, as a pin would offer it.

    The form offers to pin a voice only after this answered; the pin itself
    (``PUT /admin/voice/fishaudio/library/pins/{voice_id}``) files the
    administrator's attestation of the right to use it.
    """
    require_superuser(current_user, "read a Fish Audio library voice")
    _refuse_malformed_voice_id(voice_id)
    try:
        option = await fetch_fish_voice(_fish_api_key(), voice_id)
    except FishVoicesError as exc:
        logger.warning(
            "voice_lookup_fishaudio_failed",
            admin_user_id=str(current_user.id),
            status_code=exc.details.get("status_code"),
            vendor_code=exc.details.get("vendor_code"),
        )
        raise_external_service_fetch_error(
            service=FISHAUDIO_PROVIDER_NAME, resource="voice", status_code=502
        )
    if option is None:
        raise_structured_validation_error(
            error_type="fishaudio_voice_unavailable",
            loc=["path", "voice_id"],
            msg="This voice is not a trained speech voice the vendor serves.",
            input_value=voice_id,
            ctx={"voice_id": voice_id},
        )
    return voice_option_payloads([option])[0]
