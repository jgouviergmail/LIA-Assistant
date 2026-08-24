"""T4, permanent: the whole cross product translates without crashing."""

from __future__ import annotations

import json

import pytest

from src.core.reasoning_intent import LEVELS, ReasoningIntent
from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile
from src.infrastructure.llm.reasoning.translate import translate

pytestmark = pytest.mark.unit

MODELS = [
    ("openai", "gpt-5.2"),
    ("openai", "gpt-5.6-luna"),
    ("openai", "gpt-4.1"),
    ("anthropic", "claude-opus-4-6"),
    ("anthropic", "claude-opus-4-5"),
    ("deepseek", "deepseek-v4-flash"),
    ("gemini", "gemini-3.5-flash"),
    ("gemini", "gemini-2.5-flash"),
    ("qwen", "qwen3.5-plus"),
    ("perplexity", "sonar-reasoning"),
    ("ollama", "llama3.2"),
]
BUDGETS = (None, 0, 1024, 32768, 999999)


@pytest.mark.parametrize(("provider", "model"), MODELS)
def test_every_combination_translates_to_serialisable_kwargs(provider: str, model: str) -> None:
    profile = resolve_reasoning_profile(provider, model)
    for level in LEVELS:
        for budget in BUDGETS:
            produced = translate(
                ReasoningIntent(level=level, budget_tokens=budget),  # type: ignore[arg-type]
                profile,
                model,
                128_000,
            )
            json.dumps(produced)


def test_a_non_reasoning_model_produces_no_kwarg_whatever_is_asked() -> None:
    profile = resolve_reasoning_profile("openai", "gpt-4.1")
    for level in LEVELS:
        assert translate(ReasoningIntent(level=level), profile, "gpt-4.1", 32_768) == {}  # type: ignore[arg-type]


def test_provider_default_produces_no_kwarg_on_any_family() -> None:
    for provider, model in MODELS:
        profile = resolve_reasoning_profile(provider, model)
        assert translate(ReasoningIntent(), profile, model, 128_000) == {}


def test_a_budget_never_falls_below_the_anthropic_floor() -> None:
    """Anthropic rejects a thinking budget under its documented minimum."""
    from src.core.constants import ANTHROPIC_MIN_THINKING_BUDGET_TOKENS

    profile = resolve_reasoning_profile("anthropic", "claude-opus-4-5")
    for level in ("minimal", "low", "medium", "high", "xhigh"):
        produced = translate(ReasoningIntent(level=level), profile, "claude-opus-4-5", 512)  # type: ignore[arg-type]
        assert produced["thinking"]["budget_tokens"] >= ANTHROPIC_MIN_THINKING_BUDGET_TOKENS


def test_exclude_from_output_is_ignored_by_families_that_lack_it() -> None:
    """A caller must never have to know which families can express it."""
    for provider, model in (("openai", "gpt-5.2"), ("deepseek", "deepseek-v4-flash")):
        profile = resolve_reasoning_profile(provider, model)
        with_flag = translate(
            ReasoningIntent(level="high", exclude_from_output=True), profile, model, 128_000
        )
        without = translate(ReasoningIntent(level="high"), profile, model, 128_000)
        assert with_flag == without


def test_exclude_from_output_is_honoured_where_it_exists() -> None:
    profile = resolve_reasoning_profile("gemini", "gemini-3.5-flash")
    produced = translate(
        ReasoningIntent(level="high", exclude_from_output=True), profile, "gemini-3.5-flash", 65_536
    )
    assert produced["include_thoughts"] is False


def test_the_identity_sentinel_never_reaches_a_provider() -> None:
    """``provider_default`` is the identity, not a depth — it must never ship.

    The whole cross product, asserted on CONTENT rather than on
    serialisability: the previous matrix test rendered these same combinations
    and only checked that the result was JSON, so a literal
    ``"thinking_level": "provider_default"`` passed straight through it. Any
    intent that carries a budget but no depth reaches a renderer, and three
    families put the sentinel on the wire.
    """
    offenders: list[tuple[str, str, str, object]] = []
    for provider, model in MODELS:
        profile = resolve_reasoning_profile(provider, model)
        for level in LEVELS:
            for budget in BUDGETS:
                for exclude in (False, True):
                    produced = translate(
                        ReasoningIntent(  # type: ignore[arg-type]
                            level=level,
                            budget_tokens=budget,
                            exclude_from_output=exclude,
                        ),
                        profile,
                        model,
                        128_000,
                    )
                    if "provider_default" in json.dumps(produced):
                        offenders.append((model, level, str(budget), produced))
    assert offenders == [], offenders


def test_a_depthless_intent_still_carries_what_the_family_can_express() -> None:
    """Asking only to hide the reasoning is an instruction, not an absence.

    The admin can flip that switch without choosing a depth — the widget offers
    it independently — and the value is accepted by the write path. Dropping it
    at translation time is the published-vs-applied gap this design exists to
    close, pointing inwards.
    """
    profile = resolve_reasoning_profile("gemini", "gemini-3.5-flash")
    produced = translate(
        ReasoningIntent(exclude_from_output=True), profile, "gemini-3.5-flash", 65_536
    )
    assert produced.get("include_thoughts") is False
    assert "thinking_level" not in produced  # no depth was asked for


def test_a_depthless_intent_stays_empty_where_the_flag_means_nothing() -> None:
    """And it must not start sending kwargs to families that cannot express it."""
    for provider, model in (("openai", "gpt-5.2"), ("deepseek", "deepseek-v4-flash")):
        profile = resolve_reasoning_profile(provider, model)
        assert translate(ReasoningIntent(exclude_from_output=True), profile, model, 128_000) == {}


def test_every_family_has_a_renderer() -> None:
    """A family with no renderer would silently emit no kwarg at all.

    The dispatch table is what makes a new provider one entry plus one small
    function; the price of a table is that a missing key fails silently, so it
    is checked rather than trusted.
    """
    from src.infrastructure.llm.reasoning.profiles import FAMILIES
    from src.infrastructure.llm.reasoning.translate import _RENDERERS

    assert set(_RENDERERS) == FAMILIES - {"none"}
