"""Heartbeat habits source — the learned rhythm (ADR-214).

Its own module (``context_aggregator`` is frozen at its audited size and must
only shrink — the ``context_sources`` precedent). One-way dependency: this
module never imports the aggregator.

What lives here is the learned RHYTHM (claimed active windows per day class),
informational: the decision LLM prefers notifying inside these windows but the
person's configured hour bounds always prevail (the prompt says so). The
deterministic TICK SCORING lives in ``habits.tick_scoring`` (the interest sweep
reads it too).

The missed-routine OFFER this source used to carry is retired (ADR-375): it
rested on a locked hour, reached the person as a rank-4 signal a model could
drop, and its acceptance had no object. Proposals are now opened by the
nightly recompute and shown by the code — in the chat under an answer, and in
Alertes › Propositions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.capability import habits_capability_enabled
from src.domains.habits.consumption import load_consumable_profile
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.rhythm import RhythmProfile


def rhythm_summary(profile: RhythmProfile | None) -> dict[str, list[str]] | None:
    """Compact per-class window labels of a (consumable) rhythm profile.

    Args:
        profile: The profile as narrowed by ``load_consumable_profile`` —
            the caller never hands the raw stored payload here, or a window
            the person paused or blocked would be served again.

    Returns:
        ``{"weekday": ["08:00-10:00", ...], "weekend": [...]}`` with only the
        classes that actually claim windows; None when nothing is claimed.
    """
    if profile is None:
        return None
    summary = {
        name: [w.label() for w in rhythm.windows]
        for name, rhythm in (("weekday", profile.weekday), ("weekend", profile.weekend))
        if rhythm.windows
    }
    return summary or None


async def fetch_habits_context(
    db: AsyncSession,
    user_id: UUID,
    user: Any,
    settings: Any,
) -> dict[str, Any] | None:
    """Aggregate the habits block for the heartbeat decision context.

    Args:
        db: Fresh session provided by the aggregator (scoped fetcher).
        user_id: Owner.
        user: The User row (the person's preference).
        settings: Application settings.

    Returns:
        ``{"rhythm": ...}`` or None when the feature is off for this person or
        no window is claimed.
    """
    if not getattr(settings, "habits_enabled", False) or not getattr(user, "habits_enabled", True):
        return None
    if not await habits_capability_enabled():
        return None
    rhythm = rhythm_summary(await load_consumable_profile(HabitsRepository(db), user_id))
    return {"rhythm": rhythm} if rhythm else None
