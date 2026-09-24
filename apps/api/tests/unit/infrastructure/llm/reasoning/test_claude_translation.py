"""What a stored reasoning intent becomes on the wire for each Claude generation.

Each expected dict is the exact request fragment the Claude API accepted on
2026-09-23 (ADR-306); the two failure modes it guards are both measured 400s:
``thinking.type.disabled`` sent to an always-on model, and ``budget_tokens``
sent to any generation from Opus 4.7 on. A third one is a silent cost: omitting
``thinking`` on Opus 5 or Sonnet 5 does not switch thinking off, it switches it
ON — so ``none`` must be spelled out.
"""

from __future__ import annotations

import pytest

from src.core.reasoning_intent import LEVELS, ReasoningIntent
from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile
from src.infrastructure.llm.reasoning.translate import honours_exclude_from_output, translate

pytestmark = pytest.mark.unit

_DISPLAY_MODELS = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-fable-5-1",
    "claude-opus-5-5",
)


def _render(model: str, intent: ReasoningIntent) -> dict[str, object]:
    return translate(intent, resolve_reasoning_profile("anthropic", model), model, 128_000)


@pytest.mark.parametrize("model", _DISPLAY_MODELS)
def test_a_depth_asks_for_adaptive_thinking_shown_as_a_summary(model: str) -> None:
    assert _render(model, ReasoningIntent(level="high")) == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "effort": "high",
    }


@pytest.mark.parametrize("model", _DISPLAY_MODELS)
def test_hiding_the_reasoning_is_the_omitted_display(model: str) -> None:
    assert _render(model, ReasoningIntent(level="xhigh", exclude_from_output=True)) == {
        "thinking": {"type": "adaptive", "display": "omitted"},
        "effort": "xhigh",
    }


@pytest.mark.parametrize(
    "model", ("claude-opus-4-7", "claude-opus-4-8", "claude-opus-5", "claude-sonnet-5")
)
def test_an_explicit_off_is_spelled_out(model: str) -> None:
    """On Opus 5 and Sonnet 5 an absent ``thinking`` THINKS; ``disabled`` is the only off."""
    assert _render(model, ReasoningIntent(level="none")) == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize("model", ("claude-fable-5", "claude-fable-5-1", "claude-opus-5-5"))
def test_an_always_on_model_is_never_sent_disabled(model: str) -> None:
    """``disabled`` is a 400 there: the off switch becomes the cheapest depth."""
    assert _render(model, ReasoningIntent(level="none")) == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "effort": "low",
    }


@pytest.mark.parametrize("model", _DISPLAY_MODELS)
def test_no_intent_asks_for_nothing(model: str) -> None:
    """``provider_default`` is the identity: hiding a reasoning nobody asked for
    is already the API default from Opus 4.7 on, so nothing is sent either."""
    assert _render(model, ReasoningIntent()) == {}
    assert _render(model, ReasoningIntent(exclude_from_output=True)) == {}


@pytest.mark.parametrize("model", _DISPLAY_MODELS)
def test_a_budget_never_reaches_a_generation_that_refuses_it(model: str) -> None:
    for level in LEVELS:
        produced = _render(model, ReasoningIntent(level=level, budget_tokens=8192))  # type: ignore[arg-type]
        thinking = produced.get("thinking")
        assert not (isinstance(thinking, dict) and "budget_tokens" in thinking), (level, produced)


def test_the_visibility_switch_is_offered_where_it_reaches_the_api() -> None:
    """Derived by rendering, so the admin switch follows the renderer."""
    assert honours_exclude_from_output("anthropic_adaptive_display") is True
    # The 4.6 pair's renderer sends no visibility control (golden file).
    assert honours_exclude_from_output("anthropic_adaptive") is False


def test_the_46_and_45_generations_render_exactly_as_before() -> None:
    """The two families that already served Claude keep their wire shape."""
    assert _render("claude-opus-4-6", ReasoningIntent(level="medium")) == {
        "thinking": {"type": "adaptive"},
        "effort": "medium",
    }
    assert _render("claude-opus-4-6", ReasoningIntent(level="none")) == {}
    assert _render("claude-sonnet-4-5", ReasoningIntent(level="none")) == {}
    produced = _render("claude-sonnet-4-5", ReasoningIntent(level="high", budget_tokens=4096))
    assert produced == {"thinking": {"type": "enabled", "budget_tokens": 4096}}
