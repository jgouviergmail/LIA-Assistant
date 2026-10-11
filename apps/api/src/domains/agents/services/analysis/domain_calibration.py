"""Pure domain score calibration; compatibility export stays in the service."""

import numpy as np


def _apply_domain_softmax_calibration(
    primary_domain: str | None,
    secondary_domains: list[str],
    confidence: float,
    temperature: float = 0.1,
) -> dict[str, float]:
    """Apply softmax calibration to domain scores.

    Primary domain gets full confidence, secondary domains get decreasing weights.
    Then softmax is applied for probability-like distribution.

    Pattern: Same as tool_selector.py _apply_softmax_calibration().

    Args:
        primary_domain: Main detected domain (highest priority).
        secondary_domains: Additional domains (lower priority).
        confidence: Base confidence from LLM analysis.
        temperature: Softmax temperature (lower = sharper discrimination).

    Returns:
        Dict mapping domain names to calibrated scores summing to ~1.0.
    """
    if not primary_domain and not secondary_domains:
        return {}

    # Build domain list with weighted raw scores
    domains: list[str] = []
    raw_scores: list[float] = []

    if primary_domain:
        domains.append(primary_domain)
        raw_scores.append(confidence)

    for i, domain in enumerate(secondary_domains):
        domains.append(domain)
        # Secondary domains: decreasing weight (0.75, 0.6, 0.5, ...)
        weight = max(0.4, 0.75 - (i * 0.15))
        raw_scores.append(confidence * weight)

    if len(domains) == 1:
        return {domains[0]: 1.0}

    # Apply softmax calibration (same pattern as tool_selector.py)
    scores_array = np.array(raw_scores)

    # Stage 1: Min-Max Stretching
    min_score = np.min(scores_array)
    max_score = np.max(scores_array)
    score_range = max_score - min_score

    if score_range < 1e-6:
        # All scores identical - uniform distribution
        return dict.fromkeys(domains, 1.0 / len(domains))

    stretched = (scores_array - min_score) / score_range

    # Stage 2: Softmax with temperature
    scaled = stretched / temperature
    scaled_shifted = scaled - np.max(scaled)  # Prevent overflow
    exp_scores = np.exp(scaled_shifted)
    softmax_scores = exp_scores / np.sum(exp_scores)

    return {d: float(softmax_scores[i]) for i, d in enumerate(domains)}
