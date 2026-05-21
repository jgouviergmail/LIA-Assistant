"""Pure retention-scoring logic for memories.

These functions are I/O-free and shared by:
- the daily cleanup scheduler (purge decision), and
- the memories API (read-only purge-risk exposure).

Moved out of infrastructure/scheduler/memory_cleanup.py so the domain/API can
reuse them without an infrastructure dependency.
"""

from dataclasses import dataclass
from datetime import datetime

from src.domains.memories.models import Memory, PurgeRiskLevel


def calculate_retention_score(
    memory: Memory,
    now: datetime,
    recency_decay_days: int,
    usage_penalty_age_days: int,
    usage_penalty_factor: float,
    weight_importance: float,
    weight_recency: float,
) -> float:
    """Calculate retention score for a memory (0-1).

    Higher score = higher chance of being kept.

    Formula:
        score = weight_importance * importance + weight_recency * recency_factor
        recency_factor = max(0, 1 - age_days / recency_decay_days)

    Negative penalty:
        if usage_count == 0 and age_days > usage_penalty_age_days:
            score *= usage_penalty_factor

    Args:
        memory: Memory ORM object.
        now: Current datetime.
        recency_decay_days: Horizon over which recency_factor decays to 0.
        usage_penalty_age_days: Age threshold for applying the zero-usage penalty.
        usage_penalty_factor: Multiplier applied to the score when the penalty triggers.
        weight_importance: Weight for the importance component.
        weight_recency: Weight for the recency component.

    Returns:
        Retention score between 0.0 and 1.0.
    """
    importance_boost = memory.importance or 0.7

    created_at = memory.created_at
    if created_at:
        age_days = (now - created_at).days
        recency_boost = max(0.0, 1.0 - age_days / max(1, recency_decay_days))
    else:
        age_days = 0
        recency_boost = 0.5  # Default if no date

    score = weight_importance * importance_boost + weight_recency * recency_boost

    # Negative penalty for never-activated memories past grace period
    if age_days > usage_penalty_age_days and (memory.usage_count or 0) == 0:
        score *= usage_penalty_factor

    return float(score)


def should_purge(
    memory: Memory,
    now: datetime,
    min_age_for_cleanup_days: int,
    recency_decay_days: int,
    usage_penalty_age_days: int,
    usage_penalty_factor: float,
    purge_threshold: float,
    weight_importance: float,
    weight_recency: float,
) -> tuple[bool, float]:
    """Determine if a memory should be purged.

    Protection rules (never purged):
    1. pinned = True (user-locked)
    2. Age < min_age_for_cleanup_days (grace period)

    If none of the above, purge if retention_score < purge_threshold.

    Args:
        memory: Memory ORM object.
        now: Current datetime.
        min_age_for_cleanup_days: Grace period before purge eligibility.
        recency_decay_days: Horizon for recency decay.
        usage_penalty_age_days: Age threshold for the zero-usage penalty.
        usage_penalty_factor: Multiplier applied when the penalty triggers.
        purge_threshold: Score below which to purge.
        weight_importance: Weight for the importance component.
        weight_recency: Weight for the recency component.

    Returns:
        Tuple of (should_purge, retention_score).
    """
    # Protection 1: Pinned
    if memory.pinned:
        return False, 1.0

    # Protection 2: Grace period not yet elapsed
    created_at = memory.created_at
    if created_at:
        age_days = (now - created_at).days
        if age_days < min_age_for_cleanup_days:
            return False, 1.0  # Not yet eligible

    retention_score = calculate_retention_score(
        memory,
        now,
        recency_decay_days,
        usage_penalty_age_days,
        usage_penalty_factor,
        weight_importance,
        weight_recency,
    )

    return retention_score < purge_threshold, retention_score


@dataclass(frozen=True)
class RetentionConfig:
    """Frozen snapshot of retention settings for a single request or job.

    Attributes:
        min_age_for_cleanup_days: Grace period before a memory is purge-eligible.
        recency_decay_days: Horizon over which the recency factor decays to 0.
        usage_penalty_age_days: Age past which a zero-usage memory is penalized.
        usage_penalty_factor: Multiplier applied when the zero-usage penalty triggers.
        purge_threshold: Score below which an eligible memory is purged.
        at_risk_margin: Band above the threshold flagged as ``at_risk`` (UI hint only).
        weight_importance: Weight of the importance component in the score.
        weight_recency: Weight of the recency component in the score.
    """

    min_age_for_cleanup_days: int
    recency_decay_days: int
    usage_penalty_age_days: int
    usage_penalty_factor: float
    purge_threshold: float
    at_risk_margin: float
    weight_importance: float
    weight_recency: float


def classify_purge_risk(
    memory: Memory,
    now: datetime,
    config: RetentionConfig,
) -> tuple[PurgeRiskLevel, float | None]:
    """Classify a memory's purge risk and return (risk, retention_score).

    States (evaluated in order):
    - PROTECTED: pinned (never auto-purged) — score None.
    - SAFE (grace): age < min_age_for_cleanup_days — score None (not yet eligible).
    - IMMINENT: eligible and score < purge_threshold (would be deleted next run).
    - AT_RISK: eligible and purge_threshold <= score < purge_threshold + at_risk_margin.
    - SAFE: eligible and score >= purge_threshold + at_risk_margin.

    Does NOT call should_purge (which short-circuits the score to 1.0 for
    pinned/grace); computes the real score directly so it can be exposed.

    Args:
        memory: Memory ORM object.
        now: Current datetime.
        config: Retention configuration snapshot.

    Returns:
        Tuple of (purge_risk, retention_score). retention_score is None for
        pinned memories and for memories still within the grace period.
    """
    if memory.pinned:
        return PurgeRiskLevel.PROTECTED, None

    created_at = memory.created_at
    age_days = (now - created_at).days if created_at else 0
    if age_days < config.min_age_for_cleanup_days:
        return PurgeRiskLevel.SAFE, None

    score = calculate_retention_score(
        memory,
        now,
        config.recency_decay_days,
        config.usage_penalty_age_days,
        config.usage_penalty_factor,
        config.weight_importance,
        config.weight_recency,
    )

    if score < config.purge_threshold:
        return PurgeRiskLevel.IMMINENT, score
    if score < config.purge_threshold + config.at_risk_margin:
        return PurgeRiskLevel.AT_RISK, score
    return PurgeRiskLevel.SAFE, score
