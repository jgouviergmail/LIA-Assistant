"""Discussion stages are independently configurable native slots, not heartbeat overrides."""

from typing import get_args

import pytest

from src.domains.agents.prompts.prompt_loader import PromptName
from src.domains.llm_config.constants import (
    CATEGORY_BACKGROUND,
    LLM_DEFAULTS,
    LLM_TYPES_REGISTRY,
)
from src.infrastructure.llm.factory import LLMType

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("slot", "output", "structured"),
    [
        ("discussion_context", 1200, True),
        ("discussion_decision", 600, True),
        ("discussion_message", 250, False),
    ],
)
def test_discussion_slots_are_native_bounded_and_independent(
    slot: str, output: int, structured: bool
) -> None:
    metadata = LLM_TYPES_REGISTRY[slot]
    assert slot in get_args(LLMType)
    assert f"{slot}_prompt" in get_args(PromptName)
    assert metadata.category == CATEGORY_BACKGROUND
    assert ("structured_output" in metadata.required_capabilities) is structured
    assert metadata.description_key == f"settings.admin.llmConfig.types.{slot}"
    config = LLM_DEFAULTS[slot]
    assert config.max_tokens == output
    assert config is not LLM_DEFAULTS["heartbeat_decision"]
    assert config is not LLM_DEFAULTS["heartbeat_message"]
    assert config.reasoning_effort is not LLM_DEFAULTS["heartbeat_decision"].reasoning_effort
