"""Only the complete owned source reset is selectable; its digest stays private."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.domains.habits.forget_snapshot import HabitForgetSnapshot


class HabitForgetRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["all_owned"]


class HabitForgetPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit_data: HabitForgetSnapshot
