"""
Schedule helpers for Scheduled Actions.

Uses APScheduler CronTrigger (already installed) to compute next trigger times.
No additional dependency needed (no croniter).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from src.core.time_utils import now_utc

# ISO 8601 weekday mapping: 1=Monday..7=Sunday -> APScheduler day names
DAY_NAMES: dict[int, str] = {
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
    7: "sun",
}

# Reverse mapping for display: APScheduler day names -> ISO weekday
DAY_LABELS_FR: dict[int, str] = {
    1: "Lun",
    2: "Mar",
    3: "Mer",
    4: "Jeu",
    5: "Ven",
    6: "Sam",
    7: "Dim",
}

DAY_LABELS_EN: dict[int, str] = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def compute_next_trigger_utc(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    after: datetime | None = None,
) -> datetime:
    """
    Compute the next trigger time in UTC using APScheduler CronTrigger.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in user timezone.
        minute: Minute of execution (0-59) in user timezone.
        user_timezone: IANA timezone (e.g., "Europe/Paris").
        after: Reference datetime (UTC). Defaults to now.

    Returns:
        Next trigger time in UTC (timezone-aware).

    Example:
        >>> compute_next_trigger_utc([1, 3, 5], 19, 30, "Europe/Paris")
        datetime(2026, 2, 28, 18, 30, tzinfo=UTC)  # Next Mon/Wed/Fri at 19:30 Paris
    """
    day_of_week_str = ",".join(DAY_NAMES[d] for d in sorted(days_of_week))
    trigger = CronTrigger(
        day_of_week=day_of_week_str,
        hour=hour,
        minute=minute,
        timezone=ZoneInfo(user_timezone),
    )
    reference = after or now_utc()
    next_fire = trigger.get_next_fire_time(None, reference)
    if next_fire is None:
        # Should never happen with valid inputs, but handle gracefully
        raise ValueError(
            f"Could not compute next trigger for days={days_of_week}, "
            f"hour={hour}, minute={minute}, tz={user_timezone}"
        )
    # CronTrigger returns fire time in the trigger's timezone — convert to UTC
    result: datetime = next_fire.astimezone(UTC)
    return result


def validate_days_of_week(days: list[int]) -> bool:
    """Validate that days_of_week contains valid ISO weekday numbers."""
    return bool(days) and all(1 <= d <= 7 for d in days) and len(days) == len(set(days))


def format_schedule_display(
    days_of_week: list[int],
    hour: int,
    minute: int,
    language: str = "fr",
) -> str:
    """
    Format schedule for human-readable display.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour (0-23).
        minute: Minute (0-59).
        language: Language code for day names.

    Returns:
        Human-readable schedule string.

    Example:
        >>> format_schedule_display([1, 3, 5], 19, 30, "fr")
        "Lun, Mer, Ven à 19:30"
    """
    labels = DAY_LABELS_FR if language == "fr" else DAY_LABELS_EN
    sorted_days = sorted(days_of_week)

    # Check for "every day"
    if sorted_days == [1, 2, 3, 4, 5, 6, 7]:
        days_str = "Tous les jours" if language == "fr" else "Every day"
    elif sorted_days == [1, 2, 3, 4, 5]:
        days_str = "Lun-Ven" if language == "fr" else "Mon-Fri"
    elif sorted_days == [6, 7]:
        days_str = "Sam-Dim" if language == "fr" else "Sat-Sun"
    else:
        days_str = ", ".join(labels[d] for d in sorted_days)

    time_str = f"{hour:02d}:{minute:02d}"
    separator = " à " if language == "fr" else " at "
    return f"{days_str}{separator}{time_str}"
