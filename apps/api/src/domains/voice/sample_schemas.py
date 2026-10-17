"""The bounded request and playable answer of a settings voice sample."""

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import VOICE_ID_MAX_CHARS
from src.domains.voice.lia_voices import Gender


class LiaVoiceSampleRequest(BaseModel):
    """A selection to hear; null means the instance's voice for that gender."""

    model_config = ConfigDict(extra="forbid")
    gender: Gender
    voice_id: str | None = Field(
        default=None, min_length=1, max_length=VOICE_ID_MAX_CHARS, pattern=r"\S"
    )


class VoiceSampleResponse(BaseModel):
    """An audio sample and the actual voice that produced it."""

    audio_base64: str
    mime_type: str
    voice_id: str
