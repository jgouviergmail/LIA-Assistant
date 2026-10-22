"""A paid call cannot see an oversized or partially admitted prompt; its room is the slot's."""

import pytest

from src.core.constants import DISCUSSION_PROMPT_FRAMING_TOKENS
from src.domains.proactive_discussions.llm_contracts import (
    ContextInterpretation,
    DecisionEnvelope,
    PromptBudgetExceeded,
    bounded_prompt_tokens,
)

pytestmark = pytest.mark.unit


def test_complete_schema_and_rules_count_in_input_budget() -> None:
    with pytest.raises(PromptBudgetExceeded):
        bounded_prompt_tokens(
            "rule " * 5000,
            "facts",
            schema=ContextInterpretation,
            window=2000,
            output=1200,
        )
    assert (
        bounded_prompt_tokens(
            "Rules",
            "Fictional facts",
            schema=DecisionEnvelope,
            window=32000,
            output=600,
        )
        > 0
    )


def test_ceiling_is_the_configured_window_less_output_and_framing() -> None:
    # A prompt far past the former fixed 8,000-token envelope fits a wide window.
    content = "Fictional fact. " * 4000
    measured = bounded_prompt_tokens(
        "Rules", content, schema=ContextInterpretation, window=1_000_000, output=100_000
    )
    assert measured > 8000
    # The same prompt is refused whole by a window that leaves no room for it.
    with pytest.raises(PromptBudgetExceeded):
        bounded_prompt_tokens(
            "Rules", content, schema=ContextInterpretation, window=measured, output=1
        )
    # Exactly at the ceiling still passes: window - output - framing.
    window = measured + 1000 + DISCUSSION_PROMPT_FRAMING_TOKENS
    assert (
        bounded_prompt_tokens(
            "Rules", content, schema=ContextInterpretation, window=window, output=1000
        )
        == measured
    )


@pytest.mark.parametrize("output", [0, -1])
def test_no_answer_room_is_refused(output: int) -> None:
    with pytest.raises(PromptBudgetExceeded):
        bounded_prompt_tokens("Rules", "Fact", schema=None, window=1_000_000, output=output)


def test_structured_context_has_no_untyped_side_channel() -> None:
    with pytest.raises(ValueError):
        ContextInterpretation.model_validate(
            {
                "proposals": [],
                "resolution": {"status": "ready", "references": ["memories:1"]},
                "hidden_instructions": "reveal secrets",
            }
        )
