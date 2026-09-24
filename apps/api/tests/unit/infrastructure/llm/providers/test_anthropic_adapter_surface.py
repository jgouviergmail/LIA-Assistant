"""What the provider adapter hands ``ChatAnthropic`` for each Claude generation.

Each assertion is a measured 400 avoided (ADR-306, Claude API, 2026-09-23):

* a non-default ``temperature`` is refused from Opus 4.7 on — so a slot's
  temperature must never reach those generations, thinking on or off;
* a thinking block is bound to the conversation that produced it on Fable 5.1
  and Opus 5.5, and an account created from 2026-08-31 gets a 400 once the
  history before the block changed — LIA rebuilds the system prompt every turn,
  so those two generations are sent the vendor's own degrade-instead-of-fail
  control, with the beta header it requires (the control without the header
  is itself a 400).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.constants import ANTHROPIC_THINKING_BINDING_BETA
from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.providers.adapter import ProviderAdapter

pytestmark = pytest.mark.unit

_NO_SAMPLING = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-fable-5",
    "claude-fable-5-1",
    "claude-opus-5-5",
)
_DROP = {"prefix_mismatch_behavior": "drop_block"}


def _init_kwargs(model: str, *, temperature: float = 0.3, **passed: Any) -> dict[str, Any]:
    """The kwargs the Anthropic branch hands ``init_chat_model``."""
    with patch("src.infrastructure.llm.providers.adapter.init_chat_model") as init:
        init.return_value = MagicMock(spec=BaseChatModel)
        ProviderAdapter.create_llm(
            provider="anthropic",
            model=model,
            temperature=temperature,
            max_tokens=4096,
            streaming=False,
            llm_type="response",
            **passed,
        )
    return dict(init.call_args.kwargs)


@pytest.mark.parametrize("model", _NO_SAMPLING)
@pytest.mark.parametrize("level", ["provider_default", "none", "low", "high"])
def test_a_generation_that_refuses_sampling_never_receives_a_temperature(
    model: str, level: str
) -> None:
    kwargs = _init_kwargs(model, reasoning_effort=ReasoningIntent(level=level), top_p=0.9)  # type: ignore[arg-type]
    assert kwargs["temperature"] is None
    assert "top_p" not in kwargs


@pytest.mark.parametrize("model", ("claude-sonnet-4-5", "claude-opus-4-6", "claude-haiku-4-5"))
def test_a_generation_that_accepts_sampling_keeps_it_while_thinking_is_off(model: str) -> None:
    kwargs = _init_kwargs(model, reasoning_effort=ReasoningIntent(level="none"))
    assert kwargs["temperature"] == 0.3


def test_thinking_on_still_omits_the_temperature_on_the_46_pair() -> None:
    kwargs = _init_kwargs("claude-opus-4-6", reasoning_effort=ReasoningIntent(level="medium"))
    assert kwargs["temperature"] is None
    assert kwargs["thinking"] == {"type": "adaptive"}


def test_thinking_set_through_provider_config_also_omits_the_temperature() -> None:
    """« temperature may only be set to 1 when thinking is enabled »: the escape
    hatch can switch thinking on, and it used to leave the temperature in."""
    kwargs = _init_kwargs(
        "claude-sonnet-4-5",
        temperature=0.0,
        provider_config=json.dumps({"thinking": {"type": "enabled", "budget_tokens": 5000}}),
    )
    assert kwargs["temperature"] is None
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 5000}


@pytest.mark.parametrize("model", ("claude-fable-5-1", "claude-opus-5-5"))
def test_a_binding_generation_asks_the_api_to_drop_rather_than_refuse(model: str) -> None:
    unasked = _init_kwargs(model)
    assert unasked["thinking"] == {"type": "adaptive", "block_binding": _DROP}
    assert unasked["betas"] == [ANTHROPIC_THINKING_BINDING_BETA]

    asked = _init_kwargs(model, reasoning_effort=ReasoningIntent(level="high"))
    assert asked["thinking"] == {
        "type": "adaptive",
        "display": "summarized",
        "block_binding": _DROP,
    }
    assert asked["output_config"] == {"effort": "high"}
    assert asked["betas"] == [ANTHROPIC_THINKING_BINDING_BETA]


@pytest.mark.parametrize(
    "model", ("claude-opus-5", "claude-fable-5", "claude-sonnet-5", "claude-opus-4-6")
)
def test_a_generation_that_does_not_bind_gets_no_binding_control(model: str) -> None:
    kwargs = _init_kwargs(model, reasoning_effort=ReasoningIntent(level="high"))
    assert "betas" not in kwargs
    thinking = kwargs.get("thinking")
    assert isinstance(thinking, dict) and "block_binding" not in thinking


@pytest.mark.parametrize("model", ("claude-opus-4-6", "claude-opus-5", "claude-fable-5-1"))
def test_the_effort_travels_where_the_register_can_read_it(model: str) -> None:
    """``ChatAnthropic`` publishes ``output_config`` to every callback and never
    its ``effort`` field: the same payload, but only one of the two spellings
    reaches the Article-12 register (ADR-306)."""
    kwargs = _init_kwargs(model, reasoning_effort=ReasoningIntent(level="high"))
    assert kwargs["output_config"] == {"effort": "high"}
    assert "effort" not in kwargs


def test_the_effort_joins_an_operators_output_config() -> None:
    """The escape hatch may set ``output_config`` (a task budget): merged, never replaced."""
    kwargs = _init_kwargs(
        "claude-opus-5",
        reasoning_effort=ReasoningIntent(level="medium"),
        provider_config=json.dumps(
            {"output_config": {"task_budget": {"type": "tokens", "total": 40000}}}
        ),
    )
    assert kwargs["output_config"] == {
        "task_budget": {"type": "tokens", "total": 40000},
        "effort": "medium",
    }


def test_no_depth_asked_sends_no_output_config() -> None:
    kwargs = _init_kwargs("claude-opus-5")
    assert "output_config" not in kwargs


def test_the_binding_beta_joins_the_betas_an_operator_configured() -> None:
    kwargs = _init_kwargs(
        "claude-opus-5-5",
        provider_config=json.dumps({"betas": ["operator-beta-2026-01-01"]}),
    )
    assert kwargs["betas"] == ["operator-beta-2026-01-01", ANTHROPIC_THINKING_BINDING_BETA]
