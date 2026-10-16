"""The day a test speaks on, for a voice model its vendor retires (ADR-345).

Fish Audio serves ``s1`` as ``s2.1-pro`` once its announced retirement has
passed, and the cue dialect follows the model that speaks. A test about
``s1``'s own dialect pins the clock to that model's last day, read from the
vendor table, so it never turns red on the morning after.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.domains.voice import expressive_cues
from src.infrastructure.llm.catalogue.vendor_announcements import announced_shutdown


def retirement_day(provider: str, model: str) -> date:
    """The last day ``model`` is served as itself, as its vendor announced it."""
    _, day = announced_shutdown(provider, model)
    assert day is not None, f"{provider}/{model} has no announced retirement"
    return day


def speak_on(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    """Make the cue dialects decide retirements against ``day``."""
    monkeypatch.setattr(expressive_cues, "_today", lambda: day)


__all__ = ["retirement_day", "speak_on"]
