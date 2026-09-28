"""What the pricing cache has counted, read from the registry the counter writes."""

from __future__ import annotations

from prometheus_client import REGISTRY

#: Every reason ``pricing_cache_fallback_total`` counts a token-priced miss under.
_TOKEN_MISS_REASONS = ("cache_not_initialized", "model_not_found")


def fallbacks_counted() -> float:
    """Every token-priced miss the pricing cache has counted, whatever its reason.

    Returns:
        The sum of the counter's samples over its token reasons (a reason that
        never fired has no sample and counts zero).
    """
    return sum(
        REGISTRY.get_sample_value("pricing_cache_fallback_total", {"reason": reason}) or 0.0
        for reason in _TOKEN_MISS_REASONS
    )
