"""Map a requested level onto what a model actually accepts, safely.

Two rules, both measured rather than chosen, and both enforced by tests.

**Ties break upward.** With ties broken downward, ``deepseek-v4-flash`` asked
for ``low`` -- equidistant from ``none`` and ``high`` on its ("none", "high",
"max") ladder -- coerces to ``none``: reasoning silently disabled. So does
``claude-opus-4-6`` asked for ``minimal``. That is the exact failure this whole
model exists to remove, re-created through another door. The codebase already
carries the doctrine: *"an uninformed guess must never under-budget a hard
query"* (``utils/react_budget.py``).

**``none`` is never a coercion target.** Only an explicit ``level="none"``
disables reasoning, and only on a model that can be disabled at all.
"""

from __future__ import annotations

from src.core.reasoning_intent import level_ordinal
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile


def coerce(level: str, profile: ReasoningProfile) -> tuple[str, bool]:
    """Return the nearest level this model accepts, and whether it moved.

    Args:
        level: The requested level.
        profile: The model's derived profile.

    Returns:
        ``(effective_level, was_coerced)``. ``provider_default`` is returned
        unchanged, and is also the answer for a family with no ladder -- asking
        a non-reasoning model for ``high`` produces no kwarg rather than an
        error.
    """
    if level == "provider_default" or level in profile.levels:
        return level, False
    if not profile.levels:
        return "provider_default", True
    if level == "none" and profile.can_disable:
        # Whether reasoning can be switched off is answered by ``can_disable``,
        # NOT by ladder membership. A catalogue row may narrow the ladder to the
        # depths it offers (``claude-opus-4-6`` declares ["low","medium","high",
        # "max"]) without meaning "and it can no longer be turned off" -- and
        # coercing an explicit ``none`` upward there would silently ENABLE
        # reasoning on a slot configured to have none, inverting the caller's
        # instruction and its cost.
        return "none", False
    if level == "none" and not profile.can_disable:
        # A mandatory-reasoning model has no cheap mode. Give it the cheapest it
        # HAS rather than pretending it can be switched off -- a policy that
        # believed otherwise would be wrong about cost, not merely about depth.
        return profile.levels[0], True

    target = level_ordinal(level)
    # ``none`` is excluded as a target: coercion may lower depth, never remove
    # reasoning. The fallback keeps a ladder that is only ("none",) usable.
    candidates = [candidate for candidate in profile.levels if candidate != "none"]
    if not candidates:
        candidates = list(profile.levels)
    nearest = min(
        candidates,
        key=lambda candidate: (abs(level_ordinal(candidate) - target), -level_ordinal(candidate)),
    )
    return nearest, True
