"""Canonical-provider-locked lookup into the vendored registry snapshot.

Matching a model id alone is FORBIDDEN. models.dev publishes 193 providers and
many republish the same id with contradictory metadata: ``deepseek-v4-flash``
appears under 23 of them with output caps from 32 768 to 1 048 576, and
``jiekou`` declares ``gpt-5.2`` as ``reasoning=False, temperature=True`` — the
opposite of the canonical ``openai`` entry. Every lookup therefore names LIA's
provider, and only entries from that provider's canonical vendor(s) match.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.infrastructure.llm.catalogue.snapshot_loader import load_snapshot

#: LIA provider -> the ``litellm_provider`` values that may serve it.
LITELLM_PROVIDERS: dict[str, tuple[str, ...]] = {
    "openai": ("openai",),
    "anthropic": ("anthropic",),
    "deepseek": ("deepseek",),
    "gemini": ("gemini", "vertex_ai-language-models"),
    "qwen": ("dashscope",),
    "perplexity": ("perplexity",),
    "ollama": ("ollama",),
    "elevenlabs": ("elevenlabs",),
}

#: LIA provider -> the models.dev vendor ids that may serve it.
MODELSDEV_PROVIDERS: dict[str, tuple[str, ...]] = {
    "openai": ("openai",),
    "anthropic": ("anthropic",),
    "deepseek": ("deepseek",),
    "gemini": ("google", "google-vertex"),
    "qwen": ("alibaba", "alibaba-cn"),
    "perplexity": ("perplexity",),
    "ollama": ("ollama",),
}


@lru_cache(maxsize=1)
def _litellm_by_bare_name() -> dict[tuple[str, str], dict[str, Any]]:
    """Index the LiteLLM snapshot by ``(litellm_provider, bare model name)``.

    LiteLLM keys many entries as ``vendor/model`` while LIA stores the bare
    name, so a lookup would otherwise scan 512 entries every time -- and the
    CI guards call it once per model. Where two keys reduce to the same
    ``(provider, bare name)``, the first in file order wins; the snapshot is
    written sorted, so that choice is deterministic across refreshes.
    """
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for key, value in load_snapshot()["litellm"].items():
        provider = value.get("litellm_provider")
        if not isinstance(provider, str):
            continue
        index.setdefault((provider, key.split("/")[-1]), value)
    return index


def match_litellm(provider: str, model: str) -> dict[str, Any] | None:
    """Look up ``model`` in the LiteLLM snapshot, locked to ``provider``.

    Args:
        provider: LIA provider id (``llm_models.provider``).
        model: LIA model name (``llm_models.model_name``).

    Returns:
        The snapshot entry, or ``None`` when the model is unknown to that
        provider.
    """
    allowed = LITELLM_PROVIDERS.get(provider)
    if not allowed:
        return None
    direct = load_snapshot()["litellm"].get(model)
    if isinstance(direct, dict) and direct.get("litellm_provider") in allowed:
        return direct
    index = _litellm_by_bare_name()
    for litellm_provider in allowed:
        entry = index.get((litellm_provider, model))
        if entry is not None:
            return entry
    return None


def match_modelsdev(provider: str, model: str) -> dict[str, Any] | None:
    """Look up ``model`` in the models.dev snapshot, locked to ``provider``.

    Args:
        provider: LIA provider id.
        model: LIA model name.

    Returns:
        The snapshot entry, or ``None``.
    """
    entries = load_snapshot()["modelsdev"]
    for vendor in MODELSDEV_PROVIDERS.get(provider, ()):
        entry = entries.get(f"{vendor}/{model}")
        if entry is not None:
            return entry
    return None
