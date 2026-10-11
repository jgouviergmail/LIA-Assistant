"""One source-owned management projection for the UI and explicit assistant reads."""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.memories.models import Memory
from src.domains.memories.retention import RetentionConfig, classify_purge_risk
from src.domains.memories.schemas import MemoryResponse


def build_retention_config() -> RetentionConfig:
    """Freeze the source retention settings once for a management observation."""
    return RetentionConfig(
        min_age_for_cleanup_days=settings.memory_min_age_for_cleanup_days,
        recency_decay_days=settings.memory_recency_decay_days,
        usage_penalty_age_days=settings.memory_usage_penalty_age_days,
        usage_penalty_factor=settings.memory_usage_penalty_factor,
        purge_threshold=settings.memory_purge_threshold,
        at_risk_margin=settings.memory_purge_at_risk_margin,
        weight_importance=settings.memory_retention_weight_importance,
        weight_recency=settings.memory_retention_weight_recency,
    )


def memory_to_response(
    memory: Memory,
    now: datetime | None = None,
    config: RetentionConfig | None = None,
) -> MemoryResponse:
    """Expose the same display fields without embeddings, usage writes or biometrics."""
    observed_at = now or datetime.now(UTC)
    policy = config or build_retention_config()
    purge_risk, retention_score = classify_purge_risk(memory, observed_at, policy)
    return MemoryResponse(
        id=str(memory.id),
        content=memory.content or "",
        category=memory.category or "personal",
        emotional_weight=memory.emotional_weight or 0,
        trigger_topic=memory.trigger_topic or "",
        usage_nuance=memory.usage_nuance or "",
        importance=0.7 if memory.importance is None else memory.importance,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        pinned=memory.pinned or False,
        usage_count=memory.usage_count or 0,
        last_accessed_at=memory.last_accessed_at,
        purge_risk=purge_risk,
        retention_score=retention_score,
    )
