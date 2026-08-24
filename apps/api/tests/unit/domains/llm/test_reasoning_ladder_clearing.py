"""Widening a narrowed ladder back must reach the row.

The change-set an update builds uses ``exclude_none``, so a plain ``None``
never arrives: re-ticking every depth in the admin form means "no narrowing",
and it would have been dropped in transit, leaving the previous restriction in
place. A ladder that cannot be widened back is a knob that cannot express its
own default value -- the exact defect ADR-245 removed elsewhere, reintroduced
by the form that replaced the free-text field.

The codebase already answered this once, for an emptied cached price: the
intent needs a shape of its own.
"""

from __future__ import annotations

import pytest

from src.domains.llm.schemas import ModelPriceUpdate

pytestmark = pytest.mark.unit


def test_a_plain_null_ladder_is_dropped_in_transit() -> None:
    """Why the flag has to exist at all — the trap, pinned."""
    payload = ModelPriceUpdate(reasoning_enum_values=None)

    provided = payload.model_dump(exclude_unset=True, exclude_none=True)

    assert "reasoning_enum_values" not in provided


def test_the_clearing_intent_survives_the_change_set() -> None:
    payload = ModelPriceUpdate(clear_reasoning_enum_values=True)

    provided = payload.model_dump(exclude_unset=True, exclude_none=True)

    assert provided["clear_reasoning_enum_values"] is True


def test_clearing_and_setting_at_once_is_refused() -> None:
    """Ranking two contradictory intents silently is how a value becomes luck."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        ModelPriceUpdate(
            clear_reasoning_enum_values=True,
            reasoning_enum_values=["low", "high"],
        )


def test_a_ladder_still_travels_normally() -> None:
    payload = ModelPriceUpdate(reasoning_enum_values=["low", "high"])

    provided = payload.model_dump(exclude_unset=True, exclude_none=True)

    assert provided["reasoning_enum_values"] == ["low", "high"]
    # Unset, so absent: the flag only travels when someone asked for it.
    assert "clear_reasoning_enum_values" not in provided
