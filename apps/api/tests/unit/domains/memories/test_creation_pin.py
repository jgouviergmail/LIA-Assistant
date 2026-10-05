"""Standing instructions are pinned before their creation is persisted."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory, MemoryCategory
from src.domains.memories.service import MemoryService

pytestmark = pytest.mark.unit


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> tuple[MemoryService, AsyncMock]:
    """Use real service/model behavior without a database or paid embeddings."""
    result = MemoryService(MagicMock(spec=AsyncSession))

    async def persist(memory: Memory) -> Memory:
        memory.id = uuid4()
        return memory

    create = AsyncMock(side_effect=persist)
    monkeypatch.setattr(result.repo, "create", create)
    monkeypatch.setattr(result.repo, "update", AsyncMock(side_effect=lambda memory: memory))
    return result, create


@pytest.mark.parametrize("category", list(MemoryCategory))
async def test_creation_pins_only_standing_instructions(
    service: tuple[MemoryService, AsyncMock], category: MemoryCategory
) -> None:
    memory_service, create = service
    with patch(
        "src.domains.memories.service._generate_dual_embeddings",
        new=AsyncMock(return_value=(None, None)),
    ):
        memory = await memory_service.create_memory(
            user_id=uuid4(), content="A durable memory", category=category.value
        )

    assert memory.pinned is (category is MemoryCategory.PROCEDURAL)
    assert memory.category == category.value
    assert memory.char_count == len(memory.content)
    create.assert_awaited_once_with(memory)


async def test_reclassification_creates_a_pinned_successor(
    service: tuple[MemoryService, AsyncMock],
) -> None:
    memory_service, _create = service
    old = Memory(
        id=uuid4(),
        user_id=uuid4(),
        content="Answer briefly",
        category=MemoryCategory.PREFERENCE.value,
        pinned=False,
        emotional_weight=0,
        trigger_topic="",
        usage_nuance="",
        importance=0.7,
    )
    with patch(
        "src.domains.memories.service._generate_dual_embeddings",
        new=AsyncMock(return_value=(None, None)),
    ):
        successor = await memory_service.supersede_with_update(
            old, category=MemoryCategory.PROCEDURAL.value
        )

    assert successor.pinned is True
    assert old.pinned is False
    assert old.superseded_by_id == successor.id
    assert old.invalidated_at is not None

    with pytest.raises(ValueError, match="pinned"):
        await memory_service.supersede_with_update(successor, content="Another instruction")


async def test_manual_edit_keeps_a_created_rule_pinned(
    service: tuple[MemoryService, AsyncMock],
) -> None:
    memory_service, _create = service
    with patch(
        "src.domains.memories.service._generate_dual_embeddings",
        new=AsyncMock(return_value=(None, None)),
    ):
        rule = await memory_service.create_memory(
            user_id=uuid4(), content="Answer briefly", category=MemoryCategory.PROCEDURAL.value
        )
        updated = await memory_service.update_memory(rule, content="Answer in short bullet points")

    assert updated is rule
    assert updated.content == "Answer in short bullet points"
    assert updated.pinned is True
    assert updated.invalidated_at is None
