"""Recompute authorizes current source data, not invented resulting windows."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HabitRecomputeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["current_account"]


class HabitRecomputeScope(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    timezone: str
    habits_enabled: bool


class HabitRecomputePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    habit_recompute: HabitRecomputeScope
