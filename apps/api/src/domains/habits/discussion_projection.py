"""Only the native consumable habit payload enters personal context.

Debugging state and bookkeeping are not activity facts. Unknown native
versions fail closed instead of being guessed from a JSON bag: a recurring
need is read in its ADR-375 shape (days, a usual hour and a part of the day,
never a locked hour).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.domains.habits.models import HabitKind
from src.domains.habits.needs import NEED_PAYLOAD_VERSION
from src.domains.habits.schemas import HabitResponse, HabitWindowSchema
from src.domains.habits.service import ACTIVE_WINDOW_PAYLOAD_VERSION
from src.domains.shared.discussion_lines import evidence_lines
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    semantic_version,
)


class ActiveWindowPayload(BaseModel):
    """A learned activity window's native payload: its day class and hour windows."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    version: StrictInt
    day_class: Literal["weekday", "weekend"]
    windows: tuple[HabitWindowSchema, ...] = Field(max_length=24)


class RecurringPayload(BaseModel):
    """A learned recurring need's native payload: what, how often, and when — described."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    version: StrictInt
    domain: Annotated[str, Field(max_length=64)]
    cadence: Literal["daily", "weekdays", "weekly"]
    weekday: Annotated[StrictInt | None, Field(ge=0, le=6)] = None
    usual_hour: Annotated[float, Field(ge=0, lt=24, allow_inf_nan=False)]
    part_of_day: Literal["morning", "afternoon", "evening", "night", "any"]
    distinct_days: Annotated[StrictInt, Field(ge=0)]
    active_days: Annotated[StrictInt, Field(ge=0)]
    usual_intent: Annotated[str | None, Field(max_length=4000)] = None


def _semantic_payload(row: HabitResponse) -> str:
    if row.kind == HabitKind.ACTIVE_WINDOW:
        window = ActiveWindowPayload.model_validate(row.payload)
        if window.version != ACTIVE_WINDOW_PAYLOAD_VERSION:
            raise ValueError("unknown native active-window version")
        return window.model_dump_json()
    recurring = RecurringPayload.model_validate(row.payload)
    if recurring.version != NEED_PAYLOAD_VERSION:
        raise ValueError("unknown native recurrence version")
    return recurring.model_dump_json()


def habit_evidence(row: HabitResponse, request: SourceReadRequest) -> DiscussionEvidence:
    """Project an active learned habit into derived, inferred evidence.

    Only the native consumable payload enters; an unknown payload version fails
    closed instead of being guessed.

    Args:
        row: The habit.
        request: The read.

    Returns:
        The evidence.

    Raises:
        ValueError: The payload's version is unknown.
    """
    semantic = _semantic_payload(row)
    lines = evidence_lines()
    text = lines["habit_frame"].format(key=row.key, kind=row.kind.value) + "\n" + semantic
    return DiscussionEvidence(
        reference=f"habits:{row.id}",
        source=SourceKey.HABITS,
        object_id=str(row.id),
        version=semantic_version((row.kind.value, row.key, semantic)),
        observed_at=request.now,
        recorded_at=row.created_at,
        assertion="inferred",
        derived=True,
        category=row.kind.value,
        excerpt=text[: request.item_max_chars],
        excerpt_truncated=len(text) > request.item_max_chars,
        usage_nuance=lines["habit_nuance"],
    )
