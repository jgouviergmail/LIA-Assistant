"""
Utility functions for LLM model name handling.

Centralized utilities to avoid code duplication across domains.
"""

import re
from collections.abc import Callable


def normalize_model_name(model_name: str) -> str:
    """
    Normalize LLM/TTS model name by removing date/snapshot suffixes.

    Converts versioned model names to base names for pricing lookup and metrics.
    This allows versioned models to use the same pricing and tracking as their base model.

    Supported suffix patterns:
    - ISO date format: -YYYY-MM-DD (e.g., gpt-4.1-mini-2025-04-14)
    - Compact date format: -YYYYMMDD (e.g., gpt-4.1-mini-20250414)
    - TTS snapshot format: -MMDD (e.g., tts-1-1106 → tts-1)

    Args:
        model_name: Raw model name (may include date suffix)

    Returns:
        Normalized model name without date suffix

    Examples:
        >>> normalize_model_name('gpt-4.1-mini-2025-04-14')
        'gpt-4.1-mini'
        >>> normalize_model_name('gpt-4.1-mini-20250414')
        'gpt-4.1-mini'
        >>> normalize_model_name('gpt-4.1-mini')
        'gpt-4.1-mini'
        >>> normalize_model_name('o1-mini')
        'o1-mini'
        >>> normalize_model_name('tts-1-1106')
        'tts-1'
        >>> normalize_model_name('tts-1-hd-1106')
        'tts-1-hd'
    """
    # Remove -YYYY-MM-DD suffix pattern (ISO format)
    model_name = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model_name)

    # Remove -YYYYMMDD suffix pattern (compact format)
    model_name = re.sub(r"-\d{8}$", "", model_name)

    # Remove -MMDD suffix pattern for TTS models (e.g., tts-1-1106 → tts-1)
    # Only applies to models starting with "tts-" to avoid false positives
    if model_name.startswith("tts-"):
        model_name = re.sub(r"-\d{4}$", "", model_name)

    return model_name


def resolve_priced_name(model_name: str, is_priced: Callable[[str], bool]) -> str | None:
    """Pick the name under which a model's tariff must be read.

    Tariffs are stored under the catalogue's exact ``model_name``, while
    versioned models are meant to inherit their base model's price. Reading
    only the normalised name defeats the first rule: a dated model that owns an
    explicit tariff was billed under its base model instead (measured in
    production on ``gpt-4o-2024-05-13``, which owns 5.00/15.00 but was billed
    ``gpt-4o``'s 2.50/10.00).

    The exact name therefore wins, and normalisation is the fallback — the
    documented inheritance still applies to versions with no tariff of their own.

    This helper is the single implementation of that rule: the pricing cache and
    :class:`~src.domains.llm.pricing_service.AsyncPricingService` both call it so
    they cannot diverge again.

    Args:
        model_name: Raw model name as reported by the provider or the caller.
        is_priced: Predicate answering whether a name has a tariff available.

    Returns:
        The exact name when it is priced, else the normalised name when that one
        is priced, else ``None`` when neither is.

    Examples:
        >>> resolve_priced_name("gpt-4o-2024-05-13", {"gpt-4o", "gpt-4o-2024-05-13"}.__contains__)
        'gpt-4o-2024-05-13'
        >>> resolve_priced_name("gpt-4o-2024-05-13", {"gpt-4o"}.__contains__)
        'gpt-4o'
    """
    if is_priced(model_name):
        return model_name
    normalized = normalize_model_name(model_name)
    if normalized != model_name and is_priced(normalized):
        return normalized
    return None
