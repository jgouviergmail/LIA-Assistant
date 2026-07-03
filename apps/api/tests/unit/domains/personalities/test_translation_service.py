"""Tests for PersonalityTranslationService LLM wiring (audit wave 3, N-219.1).

Before this fix the service hardcoded provider/model/temperature/max_tokens
and invoked ProviderAdapter directly with a ``personality_translation``
llm_type that did NOT exist in LLM_TYPES_REGISTRY — invisible in the admin
LLM Configuration UI and immune to DB overrides. The prompt was also inlined
in Python instead of living in prompts/v1/.

Criteria: the slot appears in the registry (hence the admin UI) and a DB
override is honored via the standard get_llm() resolution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.personalities.translation_service import (
    PersonalityTranslationService,
    clear_translation_cache,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_translation_cache()
    yield
    clear_translation_cache()


def _make_llm(payload: str = '{"title": "Ami", "description": "Chaleureux"}') -> MagicMock:
    llm = MagicMock()
    response = MagicMock()
    response.content = payload
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.mark.unit
class TestLLMSlotRegistration:
    """The slot must exist in the registry (admin UI) and defaults."""

    def test_slot_in_registry_and_defaults(self) -> None:
        from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY

        assert "personality_translation" in LLM_TYPES_REGISTRY
        assert "personality_translation" in LLM_DEFAULTS

    def test_prompt_is_versioned(self) -> None:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        text = load_prompt("personality_translation_prompt", version="v1")
        assert "{source_language}" in text
        assert "{target_language}" in text


@pytest.mark.unit
class TestTranslatePersonality:
    """Translation goes through get_llm() so DB overrides are honored."""

    async def test_uses_registered_llm_slot(self) -> None:
        llm = _make_llm()
        with patch(
            "src.domains.personalities.translation_service.get_llm", return_value=llm
        ) as mock_get_llm:
            result = await PersonalityTranslationService.translate_personality(
                source_title="Friend",
                source_description="Warm and supportive",
                source_language="en",
                target_language="fr",
                personality_code="friend",
            )

        mock_get_llm.assert_called_once_with("personality_translation")
        assert result == {"title": "Ami", "description": "Chaleureux"}

    async def test_cache_hit_skips_llm(self) -> None:
        llm = _make_llm()
        with patch("src.domains.personalities.translation_service.get_llm", return_value=llm):
            first = await PersonalityTranslationService.translate_personality(
                source_title="Friend",
                source_description="Warm and supportive",
                source_language="en",
                target_language="fr",
                personality_code="friend",
            )
            second = await PersonalityTranslationService.translate_personality(
                source_title="Friend",
                source_description="Warm and supportive",
                source_language="en",
                target_language="fr",
                personality_code="friend",
            )

        assert first == second
        assert llm.ainvoke.await_count == 1

    async def test_same_language_passthrough(self) -> None:
        with patch("src.domains.personalities.translation_service.get_llm") as mock_get_llm:
            result = await PersonalityTranslationService.translate_personality(
                source_title="Friend",
                source_description="Warm",
                source_language="en",
                target_language="en",
                personality_code="friend",
            )

        mock_get_llm.assert_not_called()
        assert result == {"title": "Friend", "description": "Warm"}

    async def test_markdown_fenced_json_parsed(self) -> None:
        llm = _make_llm('```json\n{"title": "Ami", "description": "Chaleureux"}\n```')
        with patch("src.domains.personalities.translation_service.get_llm", return_value=llm):
            result = await PersonalityTranslationService.translate_personality(
                source_title="Friend",
                source_description="Warm",
                source_language="en",
                target_language="fr",
                personality_code="friend",
            )

        assert result == {"title": "Ami", "description": "Chaleureux"}
