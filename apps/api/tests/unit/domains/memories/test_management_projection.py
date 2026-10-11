"""The displayed management projection preserves explicit values and private storage boundaries."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.memories.models import MEMORY_EMBEDDING_DIMENSIONS, Memory, PurgeRiskLevel
from src.domains.memories.router import _memory_to_response

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("importance", [0.0, 0.7])
def test_management_projection_preserves_zero_importance_without_read_side_effects(
    importance: float,
) -> None:
    now = datetime.now(UTC)
    memory = Memory(
        id=uuid4(),
        user_id=uuid4(),
        content="A deliberate user fact",
        category="procedural",
        importance=importance,
        pinned=False,
        emotional_weight=0,
        usage_count=0,
        trigger_topic="",
        usage_nuance="",
        embedding=[0.1] * MEMORY_EMBEDDING_DIMENSIONS,
        context_biometric={"private": "value"},
        created_at=now,
        updated_at=now,
    )
    projection = _memory_to_response(memory, now)
    assert projection.importance == importance
    assert projection.purge_risk == PurgeRiskLevel.PROTECTED
    assert "embedding" not in projection.model_dump()
    assert projection.context_biometric is None
    assert memory.usage_count == 0 and memory.last_accessed_at is None
