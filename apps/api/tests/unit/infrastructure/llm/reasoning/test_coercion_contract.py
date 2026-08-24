"""Coercion is a safety contract, not a convenience.

T3, T5 and T10 of the validation harness, made permanent.
"""

from __future__ import annotations

import pytest

from src.core.reasoning_intent import LEVELS
from src.infrastructure.llm.reasoning.coerce import coerce
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile, resolve_reasoning_profile

pytestmark = pytest.mark.unit


def test_a_supported_level_is_never_coerced() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-5.2")
    for level in profile.levels:
        assert coerce(level, profile) == (level, False)


def test_provider_default_is_always_the_identity() -> None:
    for provider, model in (("openai", "gpt-5.2"), ("gemini", "gemini-3.5-flash")):
        profile = resolve_reasoning_profile(provider, model)
        assert coerce("provider_default", profile) == ("provider_default", False)


def test_the_measured_case_never_disables_reasoning() -> None:
    """The decisive measured case: downward re-creates the failure being removed.

    ``deepseek-v4-flash`` accepts ("none", "high", "max"). A request for "low"
    is equidistant from "none" and "high". Breaking down disables reasoning
    silently — the exact defect this model exists to remove, arriving through
    another door.

    NOTE: this case is decided by the ``none``-exclusion rule BEFORE the
    tie-break sign is consulted, so it does not pin that sign. Measured: with
    the sign reversed, this assertion still passes. The sign has its own test
    below, on a ladder where two real depths tie.
    """
    profile = resolve_reasoning_profile("deepseek", "deepseek-v4-flash")
    assert coerce("low", profile) == ("high", True)

    adaptive = resolve_reasoning_profile("anthropic", "claude-opus-4-6")
    assert coerce("minimal", adaptive) == ("low", True)


def test_ties_between_two_real_depths_break_upward() -> None:
    """The tie-break sign itself, on a ladder that makes it observable.

    ``minimal`` and ``medium`` are equidistant from ``low``, and neither is
    ``none``, so nothing else decides: only the sign does. Upward is the
    codebase's own doctrine — *"an uninformed guess must never under-budget a
    hard query"* (``utils/react_budget.py``) — and the cheaper choice is the one
    that under-delivers invisibly, while the dearer one shows up in the costs.
    """
    gapped = ReasoningProfile("openai", ("minimal", "medium"), False, None, True, True)
    assert coerce("low", gapped) == ("medium", True)

    # And symmetrically higher up the ladder: "high" ties "medium" and "xhigh".
    wide = ReasoningProfile("openai", ("medium", "xhigh"), False, None, True, True)
    assert coerce("high", wide) == ("xhigh", True)


def test_none_is_never_a_coercion_target() -> None:
    """Only an EXPLICIT level="none" may disable reasoning."""
    for provider, model in (
        ("deepseek", "deepseek-v4-flash"),
        ("anthropic", "claude-opus-4-6"),
        ("openai", "gpt-5.2"),
        ("qwen", "qwen3.5-plus"),
        ("gemini", "gemini-2.5-flash"),
    ):
        profile = resolve_reasoning_profile(provider, model)
        for level in ("minimal", "low", "medium", "high", "xhigh", "max"):
            coerced, _ = coerce(level, profile)
            assert coerced != "none", f"{model}: {level} coerced to none"


def test_an_explicit_none_is_honoured_when_the_model_can_disable() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-5.2")
    assert coerce("none", profile) == ("none", False)


def test_a_mandatory_model_never_gets_a_disabling_level() -> None:
    """T5: ``gemini-3.5-flash`` is reasoning.mandatory — it has no cheap mode."""
    profile = resolve_reasoning_profile("gemini", "gemini-3.5-flash")
    assert profile.can_disable is False
    coerced, was_coerced = coerce("none", profile)
    assert coerced != "none"
    assert was_coerced is True


def test_a_family_with_no_ladder_falls_back_to_the_identity() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-4.1")
    assert coerce("high", profile) == ("provider_default", True)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("openai", "gpt-5.2"),
        ("openai", "gpt-5.6-luna"),
        ("anthropic", "claude-opus-4-6"),
        ("anthropic", "claude-opus-4-5"),
        ("deepseek", "deepseek-v4-flash"),
        ("gemini", "gemini-3.5-flash"),
        ("gemini", "gemini-2.5-flash"),
        ("qwen", "qwen3.5-plus"),
        ("perplexity", "sonar-reasoning"),
    ],
)
def test_every_coercion_lands_inside_the_ladder(provider: str, model: str) -> None:
    """T4's invariant: coercion never invents a level."""
    profile = resolve_reasoning_profile(provider, model)
    for level in LEVELS:
        coerced, _ = coerce(level, profile)
        assert coerced in profile.levels or coerced == "provider_default"


def test_a_narrowed_ladder_still_coerces_inside_itself() -> None:
    """``gpt-5.2-chat-latest`` declares a single-level ladder: ["medium"]."""
    profile = resolve_reasoning_profile("openai", "gpt-5.2-chat-latest", model_levels=("medium",))
    assert profile.levels == ("medium",)
    for level in ("minimal", "low", "high", "xhigh", "max"):
        assert coerce(level, profile) == ("medium", True)


def test_an_explicit_none_is_honoured_even_when_the_ladder_omits_it() -> None:
    """``can_disable`` answers "can it be off", not ladder membership.

    Caught by an existing service test, not by the golden: ``claude-opus-4-6``'s
    catalogue row narrows the ladder to ["low","medium","high","max"], which does
    not contain ``none``. Treating that as "none is unsupported" coerced an
    explicit ``none`` UPWARD — silently enabling reasoning on a slot configured
    to have none, inverting both the instruction and its cost.
    """
    profile = resolve_reasoning_profile(
        "anthropic", "claude-opus-4-6", model_levels=("low", "medium", "high", "max")
    )
    assert "none" not in profile.levels
    assert profile.can_disable is True
    assert coerce("none", profile) == ("none", False)


def test_a_narrowed_ladder_still_refuses_none_on_a_mandatory_model() -> None:
    profile = resolve_reasoning_profile("gemini", "gemini-3.5-flash", model_levels=("low", "high"))
    assert profile.can_disable is False
    coerced, was_coerced = coerce("none", profile)
    assert coerced == "low"
    assert was_coerced is True
