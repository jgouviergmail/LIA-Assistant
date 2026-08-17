"""The document_generation LLM slot exists and is coherently declared (ADR-226)."""

import pytest

from src.domains.llm.models import LLMModelKindEnum
from src.domains.llm_config.constants import (
    CATEGORY_SPECIALIZED,
    LLM_DEFAULTS,
    LLM_TYPES_REGISTRY,
)


@pytest.mark.unit
class TestDocumentGenerationLLMType:
    """Registry + defaults for the dedicated document-writer slot."""

    def test_registered_with_chat_kind(self) -> None:
        meta = LLM_TYPES_REGISTRY["document_generation"]
        assert meta.category == CATEGORY_SPECIALIZED
        assert meta.required_kind == LLMModelKindEnum.chat
        assert meta.description_key == "settings.admin.llmConfig.types.document_generation"

    def test_defaults_present_and_generous_output(self) -> None:
        cfg = LLM_DEFAULTS["document_generation"]
        # Whole documents are written in one structured-output call.
        assert cfg.max_tokens >= 8000
        assert cfg.timeout_seconds >= 60.0
