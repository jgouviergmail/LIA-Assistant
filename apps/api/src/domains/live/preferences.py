"""What the person set about how a live conversation behaves (ADR-299).

Account-level, not connector-level: a change of provider must not hand the
person back reflexes they already tuned. STRICT on the way in (the request
schema refuses a word off the ladder), TOLERANT on the way out (a stored value
nobody understands is the default, never a 500 on the settings page) — the
``settings_shortcuts`` doctrine of ADR-277.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EndOfSpeech = Literal["calm", "normal", "lively"]
ResultDelivery = Literal["interrupt", "when_idle"]


class LivePreferences(BaseModel):
    """The three reflexes, each a closed vocabulary, and the provider choice.

    There is no « talk mode »: a live session is always automatic — the
    provider's voice activity detection decides the turns (owner decision
    2026-09-19; a stored ``talk_mode`` is ignored by the tolerant reader).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    interruptions: bool = Field(
        default=True, description="Whether the person's speech stops LIA mid-sentence."
    )
    end_of_speech: EndOfSpeech = Field(
        default="normal", description="How quickly LIA takes a pause for the end of a sentence."
    )
    result_delivery: ResultDelivery = Field(
        default="interrupt",
        description="Whether a delegated answer is announced at once or at the next pause.",
    )
    provider: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "The live provider the sessions open on, among the account's active connectors "
            "(wave 2 spec A10); None means the first active one. Set by the connector the "
            "person last saved, kept by the reflexes' own PUT."
        ),
    )


def read_live_preferences(value: object) -> LivePreferences:
    """Read the stored column as it is, field by field.

    Args:
        value: Whatever the JSONB column holds.

    Returns:
        The preferences, every unreadable field at its default.
    """
    if not isinstance(value, dict):
        return LivePreferences()
    kept: dict[str, Any] = {}
    for name in LivePreferences.model_fields:
        candidate = value.get(name)
        if candidate is None:
            continue
        try:
            LivePreferences.model_validate({name: candidate})
        except ValidationError:
            continue
        kept[name] = candidate
    return LivePreferences.model_validate(kept)


__all__ = ["EndOfSpeech", "LivePreferences", "ResultDelivery", "read_live_preferences"]
