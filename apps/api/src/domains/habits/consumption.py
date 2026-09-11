"""What LIA may CONSUME of a learned rhythm: the windows the person left ACTIVE.

The rhythm profile is DERIVED data (``user_habit_profiles.payload``); the
settings panel edits MIRROR rows (``user_habits`` of kind ``active_window``:
pause, block, delete). Until 2026-09-11 the three consumers — the heartbeat
rhythm block, the tick scoring and the ambient block — read the profile and
never the rows, so a blocked window kept being served (measured, sim H).

This module is the single answer to « which windows may be used »: a window
is consumable only while its mirror row exists and is ACTIVE. A PAUSED row is
the person's snooze, a BLOCKED row their tombstone, an absent row their
deletion (relearned at the next nightly sync unless blocked first — the
documented contract). The detector's truth (verdicts, histograms, ``sparse``)
is never rewritten here: consumers read ``windows`` and nothing else.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from src.domains.habits.models import HabitKind, HabitStatus
from src.domains.habits.rhythm import DAY_CLASSES, ClassRhythm, RhythmProfile
from src.domains.habits.window_keys import window_habit_key

if TYPE_CHECKING:
    from src.domains.habits.repository import HabitsRepository


def consumable_windows(profile: RhythmProfile, active_keys: set[str]) -> RhythmProfile:
    """Keep only the windows whose mirror row is ACTIVE (pure).

    Args:
        profile: The stored rhythm profile.
        active_keys: Keys of the ACTIVE ``active_window`` rows of the user.

    Returns:
        The same profile with each class's ``windows`` narrowed to the
        consumable ones — the input object itself when nothing changes.
    """
    changes: dict[str, ClassRhythm] = {}
    for class_name in DAY_CLASSES:
        rhythm: ClassRhythm = getattr(profile, class_name)
        if not rhythm.windows:
            continue
        kept = tuple(
            window
            for window in rhythm.windows
            if window_habit_key(class_name, window, rhythm.bin_presence) in active_keys
        )
        if kept != rhythm.windows:
            changes[class_name] = replace(rhythm, windows=kept)
    if not changes:
        return profile
    return replace(
        profile,
        weekday=changes.get("weekday", profile.weekday),
        weekend=changes.get("weekend", profile.weekend),
    )


async def load_consumable_profile(repo: HabitsRepository, user_id: UUID) -> RhythmProfile | None:
    """The user's rhythm profile narrowed to its consumable windows.

    Args:
        repo: The habits repository — the heartbeat, the tick scoring and the
            ambient block each hand their own instance.
        user_id: Owner.

    Returns:
        The narrowed profile, or None when no profile is stored.
    """
    row = await repo.get_profile(user_id)
    if row is None:
        return None
    profile = RhythmProfile.from_payload(row.payload)
    if not profile.weekday.windows and not profile.weekend.windows:
        return profile
    rows = await repo.list_habits(user_id, HabitKind.ACTIVE_WINDOW.value)
    active_keys = {habit.key for habit in rows if habit.status == HabitStatus.ACTIVE.value}
    return consumable_windows(profile, active_keys)
