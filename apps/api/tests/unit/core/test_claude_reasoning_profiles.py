"""The reasoning each Claude generation can be asked for, derived from its surface.

The ladders are the effort levels the Models API declares per model
(2026-09-23): the 4.6 pair has no ``xhigh``, every later generation has all
five, and the always-on generations have no off switch — ``disabled`` is a 400
there, so ``none`` must never reach them. The two families that already served
Opus/Sonnet 4.6 and the 4.5 generation are pinned unchanged: the golden
equivalence file froze what they emit.
"""

from __future__ import annotations

import pytest

from src.core.reasoning_profiles import resolve_reasoning_profile

pytestmark = pytest.mark.unit

_FULL = ("low", "medium", "high", "xhigh", "max")
_BUDGET_LADDER = ("none", "minimal", "low", "medium", "high", "xhigh")

#: model -> (family, ladder, can_disable, implicit_level)
EXPECTED: dict[str, tuple[str, tuple[str, ...], bool, str | None]] = {
    "claude-haiku-4-5": ("anthropic_budget", _BUDGET_LADDER, True, None),
    "claude-sonnet-4-5": ("anthropic_budget", _BUDGET_LADDER, True, None),
    "claude-opus-4-5": ("anthropic_budget", _BUDGET_LADDER, True, None),
    "claude-opus-4-6": ("anthropic_adaptive", ("none", "low", "medium", "high", "max"), True, None),
    "claude-sonnet-4-6": (
        "anthropic_adaptive",
        ("none", "low", "medium", "high", "max"),
        True,
        None,
    ),
    "claude-opus-4-7": ("anthropic_adaptive_display", ("none", *_FULL), True, None),
    "claude-opus-4-8": ("anthropic_adaptive_display", ("none", *_FULL), True, None),
    "claude-opus-5": ("anthropic_adaptive_display", ("none", *_FULL), True, "high"),
    "claude-sonnet-5": ("anthropic_adaptive_display", ("none", *_FULL), True, "high"),
    "claude-fable-5": ("anthropic_adaptive_display", _FULL, False, "high"),
    "claude-fable-5-1": ("anthropic_adaptive_display", _FULL, False, "high"),
    "claude-opus-5-5": ("anthropic_adaptive_display", _FULL, False, "medium"),
}


@pytest.mark.parametrize(("model", "expected"), sorted(EXPECTED.items()))
def test_each_generation_gets_its_measured_ladder(
    model: str, expected: tuple[str, tuple[str, ...], bool, str | None]
) -> None:
    profile = resolve_reasoning_profile("anthropic", model)
    assert (profile.family, profile.levels, profile.can_disable, profile.implicit_level) == expected


def test_the_budget_family_keeps_its_token_range() -> None:
    """The 4.5 generation takes a budget, never an effort level (effort is a 400
    on Haiku 4.5 and Sonnet 4.5)."""
    profile = resolve_reasoning_profile("anthropic", "claude-sonnet-4-5")
    assert profile.supports_budget is True
    assert profile.budget_range == (1024, 128000)


def test_no_later_generation_accepts_a_budget() -> None:
    """``budget_tokens`` is a 400 from Opus 4.7 on."""
    for model in ("claude-opus-4-7", "claude-opus-5", "claude-fable-5-1", "claude-opus-5-5"):
        assert resolve_reasoning_profile("anthropic", model).supports_budget is False


def test_an_undeclared_claude_model_carries_no_reasoning_claim() -> None:
    profile = resolve_reasoning_profile("anthropic", "claude-opus-6")
    assert profile.family == "none"
    assert profile.source == "unknown"


def test_the_catalogue_narrowing_still_applies_to_a_new_generation() -> None:
    """An administrator may untick depths; the ladder narrows, the off switch
    stays governed by the family."""
    narrowed = resolve_reasoning_profile(
        "anthropic", "claude-opus-5", model_levels=("low", "medium", "high")
    )
    assert narrowed.levels == ("low", "medium", "high")
    assert narrowed.can_disable is True
    assert narrowed.source == "model_refined"
