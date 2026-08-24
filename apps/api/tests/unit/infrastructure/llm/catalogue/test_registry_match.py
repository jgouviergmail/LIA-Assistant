"""A registry entry is accepted only from LIA's canonical provider.

models.dev publishes 193 providers; ``deepseek-v4-flash`` appears under 23 of
them with output caps from 32 768 to 1 048 576, and ``jiekou`` declares
``gpt-5.2`` with the opposite reasoning flags to the canonical ``openai``
entry. Matching by model id alone would ingest resale metadata.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.catalogue.registry_match import (
    LITELLM_PROVIDERS,
    MODELSDEV_PROVIDERS,
    match_litellm,
    match_modelsdev,
)


def test_litellm_matches_canonical_provider() -> None:
    entry = match_litellm("openai", "gpt-5.2")
    assert entry is not None
    assert entry["litellm_provider"] == "openai"


def test_litellm_rejects_wrong_provider() -> None:
    """The same model id under another LIA provider must not match."""
    assert match_litellm("anthropic", "gpt-5.2") is None


def test_modelsdev_matches_canonical_vendor_only() -> None:
    entry = match_modelsdev("openai", "gpt-5.2")
    assert entry is not None
    assert entry["provider"] == "openai"


def test_modelsdev_never_returns_a_reseller_entry() -> None:
    """Every models.dev hit must come from a declared canonical vendor."""
    for lia_provider, vendors in MODELSDEV_PROVIDERS.items():
        for model in ("deepseek-v4-flash", "gpt-5.2", "claude-opus-4-6"):
            entry = match_modelsdev(lia_provider, model)
            if entry is not None:
                assert entry["provider"] in vendors


def test_unknown_provider_returns_none() -> None:
    assert match_litellm("edge", "edge-tts") is None
    assert match_modelsdev("edge", "edge-tts") is None


def test_unknown_model_returns_none() -> None:
    assert match_litellm("openai", "a-model-that-does-not-exist") is None
    assert match_modelsdev("openai", "a-model-that-does-not-exist") is None


@pytest.mark.parametrize("lia_provider", sorted(LITELLM_PROVIDERS))
def test_every_declared_litellm_provider_is_a_known_lia_provider(lia_provider: str) -> None:
    from src.domains.llm.models import LLMProviderEnum

    assert lia_provider in {member.value for member in LLMProviderEnum}


@pytest.mark.parametrize("lia_provider", sorted(MODELSDEV_PROVIDERS))
def test_every_declared_modelsdev_provider_is_a_known_lia_provider(lia_provider: str) -> None:
    from src.domains.llm.models import LLMProviderEnum

    assert lia_provider in {member.value for member in LLMProviderEnum}


def test_prefixed_litellm_key_matches_its_bare_model_name() -> None:
    """LiteLLM keys many entries as ``vendor/model``; LIA stores the bare name."""
    entry = match_litellm("gemini", "gemini-3-pro-preview")
    assert entry is not None
    assert entry["litellm_provider"] in LITELLM_PROVIDERS["gemini"]
