"""Ambient rhythm block for conversational flows (ADR-214, Lot 5).

Standalone builder symmetric to ``journals/portrait_builder.py``: reads the
stored rhythm profile and returns a compact, self-labelled prompt block
(~40-60 tokens) for the response flow. Degrades to ``""`` on any gate or
error so call sites splice it unconditionally.

The block carries at most three things, each a SERVICE cue and never a
surveillance remark (plan §5.4 exclusions):

- the learned activity windows (context for tone and timing);
- type 2 — the current hour is unusual for this user → adapt the format,
  acknowledge lightly at most once;
- type 3 — the user returns after an absence unusual FOR THEM (relative to
  their own typical gap, never an absolute threshold) → greet warmly, offer
  a brief catch-up.

Observability follows the portrait precedent: a per-flow presence counter
(``habit_ambient_block_total``), no per-request debug section — the block is
prompt scaffolding, not an extraction.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.habits.rhythm import WEEKDAY, WEEKEND, RhythmProfile, hour_in_windows
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_habits import habit_ambient_block_total

logger = get_logger(__name__)


def _window_labels(profile: RhythmProfile) -> str:
    parts = []
    for name, rhythm in ((WEEKDAY, profile.weekday), (WEEKEND, profile.weekend)):
        if rhythm.windows:
            labels = ", ".join(w.label() for w in rhythm.windows)
            parts.append(f"{name}s {labels}")
    return "; ".join(parts)


def _unusual_hour(profile: RhythmProfile, now_local: datetime) -> bool:
    """True when the current hour sits in a near-zero presence bin of a user
    who HAS a rhythm (without windows, no hour is 'unusual')."""
    rhythm = profile.weekday if now_local.weekday() < 5 else profile.weekend
    if not rhythm.windows:
        return False
    hour = now_local.hour + now_local.minute / 60.0
    if hour_in_windows(hour, rhythm.windows):
        return False
    return rhythm.bin_presence[now_local.hour] < 0.05


def _unusual_absence(
    profile: RhythmProfile, last_activity_at: datetime | None, now: datetime
) -> bool:
    """Relative absence test: gap >> the user's OWN typical gap.

    The typical gap is derived from the active-day fraction (≈ 1/fraction
    days between active days) — an occasional user's normal interval never
    reads as an absence (plan §5.6 refinement).
    """
    if last_activity_at is None or profile.active_days_fraction <= 0:
        return False
    gap_days = (now - last_activity_at).total_seconds() / 86_400
    typical_gap = 1.0 / max(profile.active_days_fraction, 0.05)
    return gap_days >= max(
        settings.habits_absence_min_days,
        settings.habits_absence_gap_factor * typical_gap,
    )


async def build_habits_rhythm_block(user_id: str | UUID, flow: str = "response") -> str:
    """Build the ambient rhythm block for prompt injection.

    Args:
        user_id: User UUID (str or UUID).
        flow: Caller flow name for the presence counter.

    Returns:
        Self-labelled ``<UserRhythmContext>…</UserRhythmContext>`` block, or
        ``""`` when the feature is off, nothing is learned, or any error
        occurs (graceful degradation — the portrait doctrine).
    """
    if not getattr(settings, "habits_enabled", False):
        return ""
    try:
        uid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
        async with get_db_context() as db:
            from src.domains.habits.repository import HabitsRepository
            from src.domains.users.models import User

            user = await db.get(User, uid)
            if user is None or not user.habits_enabled:
                return ""
            repo = HabitsRepository(db)
            profile_row = await repo.get_profile(uid)
            if profile_row is None:
                return ""
            _first, last_at = await repo.fetch_activity_bounds(uid)

        profile = RhythmProfile.from_payload(profile_row.payload)
        now = datetime.now(UTC)
        now_local = now.astimezone(resolve_user_timezone(user))

        lines: list[str] = []
        kinds: list[str] = []
        windows = _window_labels(profile)
        if windows:
            lines.append(f"Usual activity: {windows}.")
            kinds.append("rhythm")
            if _unusual_hour(profile, now_local):
                lines.append(
                    "The current hour is unusual for this user: you may "
                    "acknowledge it lightly AT MOST once, and prefer a concise "
                    "format, offering to defer detail."
                )
                kinds.append("unusual_hour")
        if _unusual_absence(profile, last_at, now):
            lines.append(
                "The user returns after an unusually long absence for them: "
                "greet warmly and briefly offer a catch-up — never comment on "
                "the absence itself."
            )
            kinds.append("absence")
        if not lines:
            return ""
        lines.append("Never mention this learned profile explicitly.")

        for kind in kinds:
            with suppress(Exception):
                habit_ambient_block_total.labels(flow=flow, kind=kind).inc()
        return "<UserRhythmContext>\n" + "\n".join(lines) + "\n</UserRhythmContext>"
    except Exception as exc:  # noqa: BLE001 — ambient block must never break a turn
        logger.warning("habit_ambient_block_failed", error=str(exc), flow=flow)
        return ""
