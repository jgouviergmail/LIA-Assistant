"""Identity and source status are editable; observed source facts are sealed."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.habits.management_commands import ManagedHabit
from src.domains.habits.models import HabitStatus
from src.domains.habits.schemas import HabitStatusUpdate


class HabitStatusChange(HabitStatusUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HabitStatusRequest(HabitStatusChange):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit_id: UUID


class HabitDeleteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit_id: UUID


class HabitStatusValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: ManagedHabit
    status: HabitStatusChange


class HabitStatusPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit: HabitStatusValues


class HabitDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit: ManagedHabit


class HabitActionField(StrEnum):
    HABIT = "habit"
    HABIT_DATA = "habit_data"
    RECOMPUTE = "habit_recompute"


def habit_command(
    draft: ApplicationActionDraftContent,
) -> tuple[ManagedHabit, HabitStatusUpdate | None]:
    if draft.operation_id == "habits.status":
        values = HabitStatusPatch.model_validate(draft.intent).habit
        return values.expected, values.status
    if draft.operation_id == "habits.delete":
        return HabitDeletePatch.model_validate(draft.intent).habit, None
    raise ValueError("Unknown habit management operation")


def habit_after(expected: ManagedHabit, change: HabitStatusUpdate | None) -> dict[str, JsonValue]:
    return {
        "habit": (
            None
            if change is None
            else expected.model_copy(update={"status": HabitStatus(change.status)}).model_dump(
                mode="json"
            )
        )
    }


def canonical_habit(draft: ApplicationActionDraftContent) -> bool:
    expected, change = habit_command(draft)
    return draft.before == {
        "habit": expected.model_dump(mode="json")
    } and draft.after == habit_after(expected, change)
