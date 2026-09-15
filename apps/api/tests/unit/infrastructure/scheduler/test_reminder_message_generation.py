"""What the reminder job asks of the model, and what it does with an empty answer.

Measured 2026-09-12 on production, the ``response`` slot on ``deepseek-flash``:
the job asked for 150 tokens, the model spent all 150 on its hidden chain of
thought (thinking is on by default and billed inside ``max_tokens``), and the
notification went out as « 🔔 » and nothing else — three times out of three.
Two defects, one per test group:

* the call sized a budget it could not know. A two-sentence notification never
  needs reasoning, so the call now DECLARES ``none`` and keeps its small answer
  budget only where the model can actually stop reasoning; elsewhere the slot's
  own budget applies, because a cap that includes the thinking is not a cap on
  the answer;
* an empty or truncated answer was sent as-is. The written fallback existed for
  an exception only; a provider verdict of « cut at the budget » (ADR-275) or an
  empty text is now the same refusal, and the spend that DID happen is kept.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.core.constants import REMINDER_MESSAGE_MAX_TOKENS
from src.core.i18n_dates import format_short_stamp
from src.core.i18n_proactive import ProactiveMessages
from src.core.llm_agent_config import LLMAgentConfig
from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile
from src.infrastructure.scheduler.reminder_notification import generate_reminder_message

pytestmark = pytest.mark.unit

_CREATED = datetime(2026, 9, 12, 13, 43, 57, tzinfo=UTC)
_TIMEZONE = "Europe/Paris"


def _answer(content: str, *, finish_reason: str = "stop", reasoning: int = 0) -> AIMessage:
    return AIMessage(
        content=content,
        response_metadata={"finish_reason": finish_reason, "model_name": "deepseek-flash"},
        usage_metadata={
            "input_tokens": 328,
            "output_tokens": 150,
            "total_tokens": 478,
            "input_token_details": {"cache_read": 128},
            "output_token_details": {"reasoning": reasoning},
        },
    )


def _slot(provider: str = "deepseek", model: str = "deepseek-flash") -> LLMAgentConfig:
    return LLMAgentConfig(
        provider=provider,
        model=model,
        temperature=0.3,
        max_tokens=10_000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )


def _profile(can_disable: bool) -> ReasoningProfile:
    return ReasoningProfile(
        "deepseek_toggle", ("none", "low", "high", "max"), False, None, can_disable, True
    )


async def _generate(
    answer: AIMessage, *, profile: ReasoningProfile | None = None
) -> tuple[Any, MagicMock]:
    """Run the generator against a fake model; return the result and the ``get_llm`` mock."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=answer)
    with (
        patch("src.domains.usage_limits.enforcement.spend_blocked", AsyncMock(return_value=False)),
        patch("src.infrastructure.llm.factory.get_llm", return_value=llm) as get_llm,
        patch("src.core.llm_config_helper.get_llm_config_for_agent", return_value=_slot()),
        patch(
            "src.core.llm_config_helper.resolve_reasoning_profile",
            return_value=profile or _profile(can_disable=True),
        ),
    ):
        result = await generate_reminder_message(
            original_message="Rappelle-moi de chanter dans une minute",
            reminder_content="chanter",
            created_at=_CREATED,
            user_timezone=_TIMEZONE,
            personality=None,
            memories=[],
            language="fr",
            user_id=None,
            recurrence=None,
        )
    return result, get_llm


def _fallback() -> str:
    stamp = format_short_stamp(_CREATED, _TIMEZONE, "fr")
    return ProactiveMessages.reminder_fallback_body(stamp, "chanter", "fr")


# ---------------------------------------------------------------------------
# An empty or cut answer is a refusal, never « 🔔 » alone
# ---------------------------------------------------------------------------


async def test_an_empty_answer_falls_back_to_the_written_sentence() -> None:
    result, _ = await _generate(_answer("", finish_reason="length", reasoning=150))
    assert result.message == _fallback()


async def test_the_spend_of_an_empty_answer_is_still_accounted() -> None:
    """The call happened and was billed; a fallback text does not unspend it."""
    result, _ = await _generate(_answer("", finish_reason="length", reasoning=150))
    # prompt tokens are reported cache-EXCLUDED by the shared reader (328 - 128)
    assert (result.tokens_in, result.tokens_out) == (200, 150)
    assert result.model_name == "deepseek-flash"


async def test_an_answer_cut_at_the_budget_is_refused_too() -> None:
    """ADR-275: a truncation is a refusal, never a rescue — a half sentence is not a reminder."""
    result, _ = await _generate(_answer("Petit rappel tout doux : il est", finish_reason="length"))
    assert result.message == _fallback()


async def test_a_complete_answer_is_sent_as_written() -> None:
    result, _ = await _generate(_answer("Petit rappel : c'est l'heure de chanter !"))
    assert result.message == "Petit rappel : c'est l'heure de chanter !"


# ---------------------------------------------------------------------------
# The usage is read through the ONE reader
# ---------------------------------------------------------------------------


async def test_the_model_name_and_the_cache_are_read_from_the_normalised_shape() -> None:
    """``response_metadata['model_name']`` and ``input_token_details.cache_read``.

    The module used to read ``response_metadata['model']`` (never set by
    LangChain) and ``usage['cached_tokens']`` (the raw OpenAI key, not the
    normalised one), so every reminder was billed to an unnamed model at zero
    with no cache credit.
    """
    result, _ = await _generate(_answer("Petit rappel : chante !"))
    assert result.model_name == "deepseek-flash"
    assert result.tokens_cache == 128


# ---------------------------------------------------------------------------
# What the call asks for
# ---------------------------------------------------------------------------


def _override(get_llm: MagicMock) -> LLMAgentConfig:
    override = get_llm.call_args.kwargs["config_override"]
    assert isinstance(override, LLMAgentConfig)
    return override


async def test_the_call_declares_no_reasoning_where_the_model_can_stop() -> None:
    _, get_llm = await _generate(_answer("ok"), profile=_profile(can_disable=True))
    override = _override(get_llm)
    assert override.reasoning_effort == ReasoningIntent(level="none")
    assert override.max_tokens == REMINDER_MESSAGE_MAX_TOKENS
    # the slot's own provider and model, not a hard-coded pair
    assert (override.provider, override.model) == ("deepseek", "deepseek-flash")


async def test_the_answer_budget_is_not_applied_where_reasoning_cannot_be_switched_off() -> None:
    """A cap that includes the thinking is not a cap on the answer."""
    _, get_llm = await _generate(_answer("ok"), profile=_profile(can_disable=False))
    override = _override(get_llm)
    assert override.max_tokens == 10_000
    assert override.reasoning_effort is None
