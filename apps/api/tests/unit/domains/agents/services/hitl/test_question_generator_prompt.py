"""What the confirmation-question model actually reads (prompt audit 2026-09-12).

The system prompt carried ``Tool name: {tool_name}`` — a placeholder nobody filled
since v1.0.0 — and its few-shot examples reached the model with doubled braces
because the file is a ``str.format`` template that the assembler only ever
``.replace()``d. These tests render the real assembler and read the result.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator

_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


@pytest.fixture
def generator() -> HitlQuestionGenerator:
    with patch("src.domains.agents.services.hitl.question_generator.get_llm") as get_llm:
        get_llm.return_value = MagicMock(name="llm")
        return HitlQuestionGenerator()


def _system_prompt(generator: HitlQuestionGenerator, **kwargs: object) -> str:
    messages = generator._build_prompt(
        tool_name=str(kwargs.get("tool_name", "send_email_tool")),
        tool_args=dict(kwargs.get("tool_args", {"to": ["alice@example.com"]})),  # type: ignore[call-overload]
        user_language=str(kwargs.get("user_language", "fr")),
    )
    return messages[0]["content"]


class TestConfirmationSystemPrompt:
    def test_no_placeholder_survives_assembly(self, generator: HitlQuestionGenerator) -> None:
        system = _system_prompt(generator)
        assert not _PLACEHOLDER_RE.findall(system), _PLACEHOLDER_RE.findall(system)

    def test_examples_reach_the_model_with_single_braces(
        self, generator: HitlQuestionGenerator
    ) -> None:
        system = _system_prompt(generator)
        assert "{{" not in system and "}}" not in system
        assert 'args={"query": "jean"}' in system

    def test_language_is_named_not_coded(self, generator: HitlQuestionGenerator) -> None:
        """The model is told « Simplified Chinese », never « zh-CN » — nor a frontend « zh »."""
        assert "User language: Simplified Chinese" in _system_prompt(
            generator, user_language="zh-CN"
        )
        assert "User language: Simplified Chinese" in _system_prompt(generator, user_language="zh")
        assert "User language: French" in _system_prompt(generator, user_language="fr")

    def test_personality_braces_are_not_interpreted(self, generator: HitlQuestionGenerator) -> None:
        """A personality written by a person may contain braces; they are text, not keys."""
        messages = generator._build_prompt(
            tool_name="send_email_tool",
            tool_args={"to": ["a@b.c"]},
            user_language="fr",
            personality_instruction="Style {direct} et {chaleureux}",
        )
        assert "Style {direct} et {chaleureux}" in messages[0]["content"]

    def test_tool_and_arguments_travel_in_the_user_message(
        self, generator: HitlQuestionGenerator
    ) -> None:
        messages = generator._build_prompt(
            tool_name="delete_contact_tool",
            tool_args={"resource_name": "people/c1", "_display_label": "Jean Dupont"},
            user_language="fr",
        )
        assert messages[1]["role"] == "user"
        assert "delete_contact_tool" in messages[1]["content"]
        assert "Jean Dupont" in messages[1]["content"]


class TestPlanApprovalSystemPrompt:
    def test_no_placeholder_survives_and_language_is_named(
        self, generator: HitlQuestionGenerator
    ) -> None:
        step = MagicMock(
            tool_name="send_email_tool", description="Send", parameters={"to": "a@b.c"}
        )
        plan = MagicMock(steps=[step], total_steps=1)
        messages = generator._build_plan_prompt(plan, ["write action"], user_language="de")
        system = messages[0]["content"]
        assert not _PLACEHOLDER_RE.findall(system), _PLACEHOLDER_RE.findall(system)
        assert "User language: German" in system
