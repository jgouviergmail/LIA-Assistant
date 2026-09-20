"""The extended-thinking live model offers low/medium/high and no off switch;
the plain live model offers nothing to set (ADR-299, spec A10)."""

from __future__ import annotations

import pytest

from src.core.reasoning_profiles import FAMILIES, resolve_reasoning_profile

pytestmark = pytest.mark.unit


def test_extended_thinking_ladder() -> None:
    profile = resolve_reasoning_profile("gemini_live", "gemini-3.8-live-extended-thinking")
    assert profile.family == "gemini_live_level"
    assert profile.levels == ("low", "medium", "high")
    assert profile.can_disable is False
    assert "gemini_live_level" in FAMILIES


def test_plain_live_model_offers_no_level() -> None:
    profile = resolve_reasoning_profile("gemini_live", "gemini-3.8-live")
    assert profile.levels == ()
