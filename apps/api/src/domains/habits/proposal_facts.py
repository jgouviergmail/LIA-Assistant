"""The facts each kind of proposal carries — ONE shape for its three readers (ADR-375).

A proposal stores facts, never a sentence: the rules WRITE them
(``proposal_rules``), the API publishes them for the card to phrase in the
person's language, and the action READS them back when the person accepts
(``proposal_handlers``). One model per kind keeps the three in step: a field a
rule stops writing is a validation error at the reader, never a ``KeyError``
in the middle of an act.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.habits.models import ProposalKind

Hour = Annotated[int, Field(ge=0, le=23, description="Local hour, 0-23.")]
Minute = Annotated[int, Field(ge=0, le=59, description="Minute of the hour, 0-59.")]


class _Facts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CitedRoutine(_Facts):
    """A routine that already reads the need, at another time of day."""

    id: str = Field(description="The routine's id.")
    title: str = Field(description="Its title, as the person named it.")
    hour: Hour
    minute: Minute


class AutomateNeedFacts(_Facts):
    """A recurring need LIA could have ready before the person asks."""

    domain: str = Field(description="The registered domain the need asks for.")
    cadence: Literal["daily", "weekdays", "weekly"] = Field(description="When it is asked.")
    weekday: int | None = Field(
        default=None, ge=0, le=6, description="0=Monday..6=Sunday for a weekly need."
    )
    hour: Hour = Field(description="The hour the routine would be ready by.")
    minute: Minute
    distinct_days: int = Field(ge=0, description="Days it was asked inside the window.")
    active_days: int = Field(ge=0, description="Days the person used LIA inside the window.")
    part_of_day: Literal["morning", "afternoon", "evening", "night", "any"] = Field(
        description="Where most asks fall."
    )
    existing_routine: CitedRoutine | None = Field(
        default=None, description="A routine already reading it, at another time."
    )

    @model_validator(mode="after")
    def _a_weekday_names_a_weekly_need(self) -> AutomateNeedFacts:
        """A weekday is named for a weekly need, and for it alone."""
        if (self.cadence == "weekly") != (self.weekday is not None):
            raise ValueError("a weekday is named for a weekly need, and for it alone")
        return self


class ShiftRoutineFacts(_Facts):
    """A routine the person keeps launching by hand at another time."""

    routine_id: str = Field(description="The routine's id.")
    routine_title: str = Field(description="Its title.")
    from_hour: Hour = Field(description="The planned time that would move.")
    from_minute: Minute
    hour: Hour = Field(description="The time the person actually runs it at.")
    minute: Minute
    manual_runs: int = Field(ge=0, description="Launches by hand inside the window.")
    manual_days: int = Field(ge=0, description="Distinct days of those launches.")


class FixRoutineFacts(_Facts):
    """A routine that keeps failing, or that the system switched off."""

    routine_id: str = Field(description="The routine's id.")
    routine_title: str = Field(description="Its title.")
    failures: int = Field(ge=0, description="Failures since its last success.")
    disabled: bool = Field(description="Whether the system switched it off.")


class ExtendWindowFacts(_Facts):
    """Proactive notifications that cannot reach the hours the person is present."""

    start: Hour = Field(description="The notification window's start (inclusive).")
    end: Hour = Field(description="Its end (exclusive; the window may wrap).")
    new_start: Hour = Field(description="The proposed start.")
    new_end: Hour = Field(description="The proposed end.")
    outside_days: int = Field(ge=0, description="Days with presence outside the window.")
    outside_share: float = Field(ge=0, le=1, description="Share of presence outside it.")


class ReviewNotificationsFacts(_Facts):
    """Many proactive notifications, and not one reaction."""

    sent: int = Field(ge=0, description="Notifications sent inside the window.")
    window_days: int = Field(ge=1, description="The window, in days.")


class ConnectSourceFacts(_Facts):
    """A domain asked for while no connector of its category is active."""

    category: str = Field(description="The connector category missing.")
    domain: str = Field(description="The domain asked for.")
    days: int = Field(ge=0, description="Days it was asked inside the window.")


ProposalFacts = (
    AutomateNeedFacts
    | ShiftRoutineFacts
    | FixRoutineFacts
    | ExtendWindowFacts
    | ReviewNotificationsFacts
    | ConnectSourceFacts
)

#: The facts model of each kind — held complete by the rules' tests.
FACTS_BY_KIND: Final[Mapping[ProposalKind, type[ProposalFacts]]] = MappingProxyType(
    {
        ProposalKind.AUTOMATE_NEED: AutomateNeedFacts,
        ProposalKind.SHIFT_ROUTINE: ShiftRoutineFacts,
        ProposalKind.FIX_ROUTINE: FixRoutineFacts,
        ProposalKind.EXTEND_NOTIFICATION_WINDOW: ExtendWindowFacts,
        ProposalKind.REVIEW_NOTIFICATIONS: ReviewNotificationsFacts,
        ProposalKind.CONNECT_SOURCE: ConnectSourceFacts,
    }
)
