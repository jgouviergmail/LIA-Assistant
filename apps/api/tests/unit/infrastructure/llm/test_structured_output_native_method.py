"""One method choice for the native structured-output path (ADR-267)."""

from __future__ import annotations

import pytest

from src.infrastructure.llm.structured_output import native_structured_method

pytestmark = pytest.mark.unit


def test_strict_mode_wins_for_openai() -> None:
    assert native_structured_method("openai", True) == {"method": "json_schema", "strict": True}


def test_openai_without_strict_uses_function_calling() -> None:
    assert native_structured_method("openai", False) == {"method": "function_calling"}


def test_ollama_uses_the_native_format_field_never_a_forced_tool() -> None:
    """Ollama does not implement ``tool_choice``; its ``format`` is grammar-constrained."""
    assert native_structured_method("ollama", False) == {"method": "json_schema"}


@pytest.mark.parametrize("provider", ["anthropic", "deepseek", "gemini", "qwen", "perplexity"])
def test_every_other_provider_keeps_function_calling(provider: str) -> None:
    assert native_structured_method(provider, False) == {"method": "function_calling"}


def test_ollama_is_declared_a_native_structured_output_provider() -> None:
    from src.core.config import settings

    assert settings.provider_supports_structured_output["ollama"] is True
