"""Native habit settings inherit source fields and reject coerced or structural values."""

from enum import StrEnum

from pydantic import ConfigDict

from src.domains.habits.preference_commands import HABIT_SETTING_FIELDS
from src.domains.habits.schemas import HabitsSettingsUpdate


class HabitSettingField(StrEnum):
    ENABLED = "habits_enabled"


class HabitSettingsPatch(HabitsSettingsUpdate):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


if {field.value for field in HabitSettingField} != HABIT_SETTING_FIELDS:
    raise AssertionError(
        "New habit preferences require reviewed confirmation fields and UI invalidation"
    )
