"""The learned habits, as the user portrait reads them (2026-09-16, part B).

Three gates (the deployment ceiling, the capability read at the act, the
person's own preference); the rhythm through ``load_consumable_profile`` so a
paused or blocked window never colours the portrait either (ADR-214 c); the
recurring requests ACTIVE only, each with its shape, its hour and its usual
intent — never a date. Habits are bounded by construction (two day classes,
``habits_max_habits_per_kind`` rows), so the item budget does not apply; the
clamp does.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n_dates import format_half_hour_label
from src.domains.habits.capability import habits_capability_enabled
from src.domains.habits.consumption import load_consumable_profile
from src.domains.habits.models import HabitKind, HabitStatus, UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.rhythm import WEEKDAY, WEEKEND, RhythmProfile
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    SourceBudget,
    clamp_item,
    empty_section,
    install_portrait_source,
    portrait_lines,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "habits"


async def _allowed(user_id: UUID) -> bool:
    if not settings.habits_enabled:
        return False
    if not await habits_capability_enabled():
        return False
    async with get_db_context() as db:
        user = await db.get(User, user_id)
    return bool(user is not None and user.habits_enabled)


def _rhythm_line(profile: RhythmProfile, lines: dict[str, str]) -> str | None:
    """The one rhythm line, or None when nothing is learned yet."""
    parts = [
        f"{name}s " + ", ".join(window.label() for window in rhythm.windows)
        for name, rhythm in ((WEEKDAY, profile.weekday), (WEEKEND, profile.weekend))
        if rhythm.windows
    ]
    if not parts and not profile.sparse:
        return None
    # The lines parser trims its values, so a segment is JOINED with a space
    # rather than carrying one.
    return lines["habits_rhythm"].format(
        windows="; ".join(parts) if parts else "none claimed",
        active_pct=round(profile.active_days_fraction * 100),
        sparse=" " + lines["habits_rhythm_sparse"] if profile.sparse else "",
    )


def _recurring_line(habit: UserHabit, lines: dict[str, str], max_chars: int) -> str:
    payload = habit.payload or {}
    hour = payload.get("trigger_hour")
    intent = payload.get("usual_intent")
    return lines["habits_recurring"].format(
        key=clamp_item(str(habit.key), max_chars),
        shape=str(payload.get("shape") or ""),
        hour=(
            " " + lines["habits_recurring_hour"].format(hour=format_half_hour_label(float(hour)))
            if hour is not None
            else ""
        ),
        intent=(
            " " + lines["habits_recurring_intent"].format(intent=clamp_item(str(intent), max_chars))
            if intent
            else ""
        ),
    )


async def read_habits(
    *, user_id: UUID, language: str, budget: SourceBudget
) -> PortraitSourceSection:
    """Render the person's learned rhythm and recurring requests.

    Args:
        user_id: The account.
        language: Unused — the lines are the model's, hours are numeric.
        budget: The clamp applies; the item count is bounded by construction.

    Returns:
        The section; never raises.
    """
    try:
        if not await _allowed(user_id):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            repo = HabitsRepository(db)
            profile = await load_consumable_profile(repo, user_id)
            rows = [
                habit
                for habit in await repo.list_habits(user_id, HabitKind.RECURRING_REQUEST.value)
                if habit.status == HabitStatus.ACTIVE.value
            ]
        lines = portrait_lines()
        items: list[str] = []
        if profile is not None:
            rhythm = _rhythm_line(profile, lines)
            if rhythm is not None:
                items.append(rhythm)
        items.extend(_recurring_line(habit, lines, budget.item_max_chars) for habit in rows)
        if not items:
            return empty_section(KEY, "empty")
        return PortraitSourceSection(
            key=KEY,
            status="used",
            text="\n".join([lines["habits_header"], *items]),
            used=len(items),
            total=len(items),
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


#: Where this source's freshness is read (the consolidation's eligibility).
FRESHNESS = FreshnessProbe(table="user_habits", user_column="user_id", stamp_column="updated_at")

# Installed at import for every path that does not go through the boot; the
# boot INSTALLS explicitly too, because an already-imported module wires
# nothing (ADR-270, the ticket-release precedent).
install_portrait_source(KEY, read_habits, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_habits"]
