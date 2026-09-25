"""An image prompt rewritten with recognised techniques, never distorted (ADR-315).

The person may ask for their image prompts to be improved before the image
model runs (« a realistic image of a cat » → « photorealistic photograph of a
cat, 85 mm lens at f/1.8, … »). What is pinned here is what makes that safe to
turn on:

- the image is NEVER lost to the enhancement: a ceiling refusal, a model
  failure, a truncated answer or an answer that fails the checks all hand the
  ORIGINAL prompt back — the enhancement is an improvement, never a gate;
- the checks are deterministic: an empty answer, one past the published bound,
  or one that lost a piece of text the image must carry is discarded;
- one call, on the slot of its own, with the account named so both ceilings
  see it and the turn's config so the turn's tracker bills it;
- the static rules travel as the system message and the prompt as the question
  (ADR-309), and the bound the checks enforce is the bound the prompt states
  (ADR-184).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.exceptions_domains import UsageLimitExceededError
from src.domains.agents.image_generation import prompt_enhancement
from src.domains.agents.image_generation.prompt_enhancement import (
    EnhancedImagePrompt,
    enhance_image_prompt,
    quoted_texts,
    rejection_reason,
)
from src.infrastructure.llm.structured_output_errors import StructuredOutputError

pytestmark = [pytest.mark.unit]

MODULE = "src.domains.agents.image_generation.prompt_enhancement"
USER = "35e9301b-86e1-4665-b47a-23363fff33aa"
#: Not the prompt's own example, so the layout test can tell the two apart.
ORIGINAL = "a lighthouse on a cliff at dusk"
ENHANCED = (
    "Photorealistic photograph of a lighthouse on a cliff at dusk, shot with a 35 mm lens, "
    "warm low sunlight from the side, weathered stone texture in crisp detail."
)


def _outcomes() -> dict[str, float]:
    from src.infrastructure.observability.metrics_extractions import (
        image_prompt_enhancement_total,
    )

    return {
        outcome: image_prompt_enhancement_total.labels(outcome=outcome)._value.get()
        for outcome in ("enhanced", "unchanged", "rejected", "failed", "skipped_quota")
    }


def _delta(before: dict[str, float]) -> dict[str, float]:
    return {k: v - before[k] for k, v in _outcomes().items() if v != before[k]}


@pytest.fixture
def doors() -> Any:
    """The doors the enhancement reaches, all closed for the test."""
    with (
        patch(
            f"{MODULE}.get_structured_output",
            AsyncMock(return_value=EnhancedImagePrompt(prompt=ENHANCED)),
        ) as structured,
        patch(f"{MODULE}.get_llm") as get_llm,
        patch(f"{MODULE}.spend_blocked", AsyncMock(return_value=False)) as blocked,
    ):
        yield {"structured": structured, "get_llm": get_llm, "blocked": blocked}


class TestQuotedTexts:
    @pytest.mark.parametrize(
        ("prompt", "expected"),
        [
            ('a sign that reads "OPEN 24/7"', ["OPEN 24/7"]),
            ("a card saying “Happy birthday Emma”", ["Happy birthday Emma"]),
            ("une affiche « Bonjour Paris » en néon", ["Bonjour Paris"]),
            ("ein Schild „Willkommen“ am Tor", ["Willkommen"]),
            ("写着「欢迎光临」的招牌和『新年快乐』", ["欢迎光临", "新年快乐"]),
        ],
    )
    def test_every_quote_style_names_the_text_the_image_carries(
        self, prompt: str, expected: list[str]
    ) -> None:
        assert quoted_texts(prompt) == expected

    def test_apostrophes_and_empty_quotes_are_not_texts(self) -> None:
        assert quoted_texts("the cat's toy, don't blur it, and \"\" nothing") == []


class TestRejectionReason:
    def test_a_faithful_rewrite_passes(self) -> None:
        assert rejection_reason(ORIGINAL, ENHANCED, max_chars=500) is None

    def test_an_empty_answer_is_rejected(self) -> None:
        assert rejection_reason(ORIGINAL, "   ", max_chars=500) == "empty"

    def test_an_answer_past_the_bound_is_rejected(self) -> None:
        assert rejection_reason(ORIGINAL, "x" * 501, max_chars=500) == "too_long"

    def test_an_answer_that_lost_a_text_is_rejected(self) -> None:
        original = 'a shop front with a sign that reads "Chez Léa"'

        assert (
            rejection_reason(original, "A shop front with a sign reading Chez Lea", max_chars=500)
            == "lost_text"
        )
        assert (
            rejection_reason(
                original, 'Street photograph of a shop, sign "Chez Léa"', max_chars=500
            )
            is None
        )

    def test_a_text_kept_in_another_quote_style_passes(self) -> None:
        assert (
            rejection_reason("a sign « Bonjour »", 'A neon sign reading "Bonjour"', max_chars=500)
            is None
        )


class TestEnhancement:
    async def test_a_faithful_rewrite_is_what_the_image_model_receives(self, doors: Any) -> None:
        before = _outcomes()

        result = await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        assert result.text == ENHANCED
        assert result.outcome == "enhanced"
        assert _delta(before) == {"enhanced": 1.0}

    async def test_one_call_on_its_own_slot_billed_to_the_account_and_the_turn(
        self, doors: Any
    ) -> None:
        config = {"callbacks": [MagicMock()]}

        await enhance_image_prompt(ORIGINAL, user_id=USER, config=config)

        doors["structured"].assert_awaited_once()
        kwargs = doors["structured"].await_args.kwargs
        assert kwargs["node_name"] == "image_prompt_enhancement"
        assert kwargs["user_id"] == USER
        assert kwargs["config"] is config
        assert doors["get_llm"].call_args.args[0] == "image_prompt_enhancement"

    async def test_the_rules_are_the_system_message_and_the_prompt_the_question(
        self, doors: Any
    ) -> None:
        await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        messages = doors["structured"].await_args.args[1]
        assert isinstance(messages[0], SystemMessage)
        assert DYNAMIC_CONTEXT_MARKER in messages[0].content.rstrip().splitlines()[-1]
        assert isinstance(messages[1], HumanMessage)
        assert ORIGINAL in messages[1].content
        assert ORIGINAL not in messages[0].content

    async def test_the_bound_the_checks_enforce_is_the_bound_the_prompt_states(
        self, doors: Any
    ) -> None:
        with patch(f"{MODULE}.settings.image_prompt_enhancement_max_chars", 777):
            await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)
            doors["structured"].return_value = EnhancedImagePrompt(prompt="y" * 778)
            result = await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        rules = doors["structured"].await_args_list[0].args[1][0].content
        assert "777" in rules
        assert result.outcome == "rejected"
        assert result.text == ORIGINAL

    async def test_an_identical_answer_reads_unchanged(self, doors: Any) -> None:
        doors["structured"].return_value = EnhancedImagePrompt(prompt=f"  {ORIGINAL} ")
        before = _outcomes()

        result = await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        assert (result.text, result.outcome) == (ORIGINAL, "unchanged")
        assert _delta(before) == {"unchanged": 1.0}

    async def test_a_rewrite_that_drops_a_text_keeps_the_original(self, doors: Any) -> None:
        original = 'a poster that reads "SALE -50%"'
        doors["structured"].return_value = EnhancedImagePrompt(prompt="A bold sale poster.")
        before = _outcomes()

        result = await enhance_image_prompt(original, user_id=USER, config=None)

        assert (result.text, result.outcome) == (original, "rejected")
        assert _delta(before) == {"rejected": 1.0}


class TestNeverAGate:
    async def test_a_closed_ceiling_calls_no_model_and_keeps_the_original(self, doors: Any) -> None:
        doors["blocked"].return_value = True
        before = _outcomes()

        result = await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        doors["structured"].assert_not_awaited()
        assert (result.text, result.outcome) == (ORIGINAL, "skipped_quota")
        assert _delta(before) == {"skipped_quota": 1.0}

    async def test_a_ceiling_closing_during_the_call_is_a_quota_skip(self, doors: Any) -> None:
        doors["structured"].side_effect = UsageLimitExceededError(
            limit_name="tokens", reason="ceiling reached"
        )

        result = await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        assert (result.text, result.outcome) == (ORIGINAL, "skipped_quota")

    @pytest.mark.parametrize(
        "error",
        [
            StructuredOutputError(
                "the answer was cut at the output cap",
                provider="openai",
                schema_name="EnhancedImagePrompt",
            ),
            TimeoutError(),
            RuntimeError("provider down"),
        ],
    )
    async def test_a_failure_or_a_truncation_keeps_the_original(
        self, doors: Any, error: Exception
    ) -> None:
        doors["structured"].side_effect = error
        before = _outcomes()

        result = await enhance_image_prompt(ORIGINAL, user_id=USER, config=None)

        assert (result.text, result.outcome) == (ORIGINAL, "failed")
        assert _delta(before) == {"failed": 1.0}


def test_the_default_bound_sits_far_below_the_vendors_own_limits() -> None:
    """gpt-image reads 32 000 characters, a Qwen Image 3.0 prompt holds up to 4 500 tokens."""
    assert settings.image_prompt_enhancement_max_chars <= 4000
    assert prompt_enhancement.LLM_TYPE == "image_prompt_enhancement"
