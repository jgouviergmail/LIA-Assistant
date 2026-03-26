"""Unit tests for the journal analyst persona prompt system."""

import pytest

from src.domains.agents.prompts.prompt_loader import PromptName, load_prompt


@pytest.mark.unit
class TestJournalAnalystPersona:
    """Tests for the journal analyst persona prompt."""

    def test_analyst_persona_loads(self) -> None:
        """Analyst persona prompt file loads successfully."""
        prompt = load_prompt("journal_analyst_persona")
        assert len(prompt) > 0

    def test_analyst_persona_has_personality_code_placeholder(self) -> None:
        """Analyst persona prompt contains {personality_code} placeholder."""
        prompt = load_prompt("journal_analyst_persona")
        assert "{personality_code}" in prompt

    def test_analyst_persona_format_with_code(self) -> None:
        """Analyst persona prompt can be formatted with a personality code."""
        prompt = load_prompt("journal_analyst_persona")
        formatted = prompt.format(personality_code="cynic")
        assert "cynic" in formatted
        assert "{personality_code}" not in formatted

    def test_analyst_persona_format_with_none(self) -> None:
        """Analyst persona prompt can be formatted with 'none' personality."""
        prompt = load_prompt("journal_analyst_persona")
        formatted = prompt.format(personality_code="none")
        assert "none" in formatted

    def test_personality_addon_not_in_prompt_names(self) -> None:
        """Deprecated personality addon is no longer registered."""
        # PromptName is a Literal type — check its args
        valid_names = PromptName.__args__  # type: ignore[attr-defined]
        assert "journal_introspection_personality_addon" not in valid_names

    def test_analyst_persona_in_prompt_names(self) -> None:
        """Journal analyst persona is registered in PromptName."""
        valid_names = PromptName.__args__  # type: ignore[attr-defined]
        assert "journal_analyst_persona" in valid_names

    def test_extraction_prompt_loads(self) -> None:
        """Extraction prompt loads with new theme definitions."""
        prompt = load_prompt("journal_introspection_prompt")
        assert "THEME SELECTION GUIDE" in prompt
        assert "QUALITY GATE" in prompt

    def test_consolidation_prompt_loads(self) -> None:
        """Consolidation prompt loads with mandatory dedup step."""
        prompt = load_prompt("journal_consolidation_prompt")
        assert "MANDATORY DEDUP" in prompt
        assert "PROGRESSIVE REFORMAT" in prompt
