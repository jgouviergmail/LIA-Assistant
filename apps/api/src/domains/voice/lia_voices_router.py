"""LIA's voices for one person, in the voice mode settings (ADR-345 amendment 2026-10-14).

``GET /voice/lia-voices``: the engine that speaks in the chat, the voices the
person may choose (their language's rule applied), their choice and the
instance's voice for each gender. ``PUT``: keep a voice per gender for that
engine — a voice the engine does not offer is refused, a gender left null
speaks with the instance's voice.

Both read the engine's catalogue — a live one may ask the vendor — so each
authenticates on a session of its own, closed before the route runs (ADR-304).
The settings stay open whatever the TTS switch says (a switch removes the
capability, never the record, ADR-280): ``available`` tells the page whether LIA
speaks at all.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import VOICE_ID_MAX_CHARS
from src.core.i18n import normalize_language
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.users.models import User
from src.domains.voice.lia_voices import Gender, LiaVoices, lia_voices, save_lia_voices
from src.domains.voice.schemas import VoiceOptionPayload, voice_option_payloads

router = APIRouter(prefix="/voice/lia-voices", tags=["Voice"])

Person = Annotated[User, Depends(get_current_active_session_for_stream)]


class LiaVoicesRequest(BaseModel):
    """LIA's voices for the person, on the engine that speaks."""

    model_config = ConfigDict(extra="forbid")

    male: str | None = Field(
        default=None,
        min_length=1,
        max_length=VOICE_ID_MAX_CHARS,
        description="LIA's male voice; null for the instance's.",
    )
    female: str | None = Field(
        default=None,
        min_length=1,
        max_length=VOICE_ID_MAX_CHARS,
        description="LIA's female voice; null for the instance's.",
    )

    def choice(self) -> dict[Gender, str]:
        """The voices chosen, by gender (a gender left null is not chosen)."""
        chosen: dict[Gender, str] = {}
        if self.male is not None:
            chosen["male"] = self.male
        if self.female is not None:
            chosen["female"] = self.female
        return chosen


class LiaVoicesResponse(BaseModel):
    """LIA's voices as the voice mode settings show them."""

    available: bool = Field(description="Whether LIA speaks on this instance at all.")
    engine: str = Field(description="The engine that speaks in the chat (provider/model).")
    provider: str = Field(description="Its provider.")
    voices: list[VoiceOptionPayload] = Field(
        description="The voices the person may choose, those native to their language first."
    )
    male: str | None = Field(description="Their male voice; null for the instance's.")
    female: str | None = Field(description="Their female voice; null for the instance's.")
    default_male: VoiceOptionPayload = Field(description="The instance's male voice.")
    default_female: VoiceOptionPayload = Field(description="The instance's female voice.")


async def _response(view: LiaVoices) -> LiaVoicesResponse:
    male, female = voice_option_payloads([view.defaults["male"], view.defaults["female"]])
    return LiaVoicesResponse(
        available=await is_capability_enabled(PlatformCapability.TTS),
        engine=view.engine.name,
        provider=view.engine.config.provider,
        voices=voice_option_payloads(view.voices),
        male=view.chosen.get("male"),
        female=view.chosen.get("female"),
        default_male=male,
        default_female=female,
    )


@router.get("", response_model=LiaVoicesResponse, summary="LIA's voices for the person")
async def get_lia_voices(person: Person) -> LiaVoicesResponse:
    """The engine that speaks, the voices offered, the person's choice and the defaults."""
    return await _response(await lia_voices(person.id, normalize_language(person.language)))


@router.put("", response_model=LiaVoicesResponse, summary="Choose LIA's voices")
async def put_lia_voices(person: Person, body: LiaVoicesRequest) -> LiaVoicesResponse:
    """Keep the person's voices for the engine that speaks (422 for a voice it does not offer)."""
    view = await save_lia_voices(person.id, normalize_language(person.language), body.choice())
    return await _response(view)


__all__ = ["router"]
