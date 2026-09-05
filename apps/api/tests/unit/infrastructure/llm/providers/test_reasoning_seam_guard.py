"""Every provider branch routes the stored reasoning intent through the seam.

ADR-245 made ``kwargs_for(provider, model, stored)`` the ONE seam between a
stored :class:`ReasoningIntent` and the kwargs a provider SDK accepts, and said
it replaced six call sites. It had replaced five. The Ollama and Perplexity
branches of ``_prepare_provider_config`` never popped ``reasoning_effort``, so
the intent object itself reached ``ChatOpenAI(reasoning_effort=...)`` and
failed Pydantic validation -- for ANY stored level, ``provider_default``
included. Measured in production 2026-09-05: the ``response`` slot on Ollama
died at instantiation on every turn, and 29 of the 58 slot defaults carry a
non-null intent the merge inherits, so no admin choice could avoid it.

This guard is the test that would have been red since v1.32.0. It drives every
member of ``ProviderType`` -- a new provider must be added to the matrix or the
guard fails -- with every level that can be stored, and asserts that whatever
constructor the branch calls receives no ``ReasoningIntent`` anywhere in its
kwargs and only JSON-serialisable values.
"""

from __future__ import annotations

import json
from dataclasses import is_dataclass
from typing import Any, get_args
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama as _RealChatOllama

from src.core.reasoning_intent import LEVELS, ReasoningIntent
from src.infrastructure.llm.providers.adapter import ProviderAdapter, ProviderType

pytestmark = pytest.mark.unit

#: One model per provider branch. OpenAI has TWO branches (Responses API for
#: eligible models, Chat Completions otherwise), so it appears twice.
_MATRIX: list[tuple[str, str]] = [
    ("openai", "gpt-4.1-mini"),
    ("openai", "gpt-5.6-luna"),
    ("anthropic", "claude-sonnet-4-5"),
    ("deepseek", "deepseek-v4-flash"),
    ("gemini", "gemini-3.7-flash"),
    ("qwen", "qwen3.5-plus"),
    ("perplexity", "sonar-reasoning"),
    ("ollama", "qwen3.8:27b"),
]


def test_the_matrix_covers_every_chat_provider() -> None:
    """A provider added to ``ProviderType`` must be added here too."""
    assert {provider for provider, _ in _MATRIX} == set(get_args(ProviderType))


def _walk(value: Any):  # type: ignore[no-untyped-def]
    """Yield every leaf of a kwargs tree, so a nested intent cannot hide."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def _constructor_kwargs(provider: str, model: str, stored: ReasoningIntent) -> dict[str, Any]:
    """Create the LLM with every constructor mocked; return what the branch passed."""
    mock_llm = MagicMock(spec=BaseChatModel)
    with (
        patch(
            "src.infrastructure.llm.providers.adapter.init_chat_model", return_value=mock_llm
        ) as init_chat,
        patch(
            "src.infrastructure.llm.providers.adapter.create_responses_llm", return_value=mock_llm
        ) as responses,
        patch(
            "src.infrastructure.llm.providers._deepseek_patched.ChatDeepSeekPatched",
            return_value=mock_llm,
        ) as deepseek,
        patch("langchain_google_genai.ChatGoogleGenerativeAI", return_value=mock_llm) as gemini,
        patch(
            "src.infrastructure.llm.providers.ollama_chat.ChatOllamaTraced",
            return_value=mock_llm,
        ) as ollama,
        patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
            return_value="http://ollama.local:11434" if provider == "ollama" else "sk-test",
        ),
    ):
        # The real field list, so the escape-hatch filter behaves as in
        # production: a bare MagicMock answers "not a field" to everything and
        # would silently drop every kwarg this guard is meant to inspect.
        ollama.model_fields = _RealChatOllama.model_fields
        ProviderAdapter.create_llm(
            provider=provider,  # type: ignore[arg-type]
            model=model,
            temperature=0.3,
            max_tokens=1000,
            streaming=True,
            llm_type="response",
            reasoning_effort=stored,
        )
        called = [m for m in (init_chat, responses, deepseek, gemini, ollama) if m.called]
    assert len(called) == 1, f"{provider}/{model}: exactly one constructor must be called"
    return dict(called[0].call_args.kwargs)


@pytest.mark.parametrize(("provider", "model"), _MATRIX)
@pytest.mark.parametrize("level", LEVELS)
def test_no_constructor_ever_receives_the_intent_object(
    provider: str, model: str, level: str
) -> None:
    kwargs = _constructor_kwargs(provider, model, ReasoningIntent(level=level))  # type: ignore[arg-type]
    for leaf in _walk(kwargs):
        assert not isinstance(leaf, ReasoningIntent), f"{provider}/{model}/{level}: {leaf!r}"
        assert not is_dataclass(leaf), f"{provider}/{model}/{level}: {leaf!r}"
    # A provider SDK validates its kwargs into a JSON request: anything that
    # cannot be serialised is a value no SDK was meant to receive.
    json.dumps(kwargs)


@pytest.mark.parametrize(("provider", "model"), _MATRIX)
def test_a_budget_intent_is_translated_too(provider: str, model: str) -> None:
    kwargs = _constructor_kwargs(provider, model, ReasoningIntent(budget_tokens=2048))
    assert not any(isinstance(leaf, ReasoningIntent) for leaf in _walk(kwargs))
    json.dumps(kwargs)
