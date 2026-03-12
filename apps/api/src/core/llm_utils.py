"""
Utility functions for LLM model name handling.

Centralized utilities to avoid code duplication across domains.
"""

import re


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
