"""What the operator changed by hand, as the pricing seed's production extraction carries it.

The seed is an extraction of the production catalogue, and production moves on without any
migration: the operator retires a model, or enters a tariff again at the same price. A guard that
holds the seed to a migration keeps reading the row the migration wrote, at its own date, which
stays in the bundle as history; only ``is_active`` is the operator's word, and only for the models
named here (extraction of 2026-11-06, held honest by ``test_pricing_seed_extraction_guard.py``).

Four of them -- ``llama3.2``, ``mistral``, ``qwen2.5`` and ``sonar-reasoning`` -- left on
2026-11-11, when the owner had the bundle applied to production as written: it retires a model it
prices only in the past and that no slot names.
"""

from __future__ import annotations

#: The catalogue rows the operator took out of service in production.
RETIRED_BY_THE_OPERATOR: frozenset[str] = frozenset(
    {
        "claude-haiku-4-5",
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-flash-live-preview",
        "gemini-3.1-flash-tts-preview",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gpt-4.1-nano",
        "gpt-4o-2024-05-13",
        "gpt-5-chat-latest",
        "gpt-5-codex",
        "gpt-5.1-chat-latest",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini",
        "gpt-5.2-chat-latest",
        "gpt-5.2-codex",
        "gpt-5.3-chat-latest",
        "llama3.2",
        "mistral",
        "o1",
        "o1-pro",
        "o3-deep-research",
        "o3-mini",
        "o4-mini",
        "o4-mini-deep-research",
        "qwen2.5",
        "qwen3.5-flash",
        "qwen3.5-plus",
        "sonar-reasoning",
    }
)


def retired_by_the_operator(model_name: str, column: str) -> bool:
    """Whether this column of this catalogue row is the operator's word, not a migration's.

    Args:
        model_name: The catalogue row.
        column: The column a guard compares.

    Returns:
        ``True`` for the ``is_active`` of a model the operator retired.
    """
    return column == "is_active" and model_name in RETIRED_BY_THE_OPERATOR
