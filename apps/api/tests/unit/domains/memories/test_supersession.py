"""Temporal supersession of memories (Lot 2-B1, ADR-235).

An automated correction never destroys history: the old fact is
invalidated (``invalidated_at``) and, when a successor exists, points at
it (``superseded_by_id``). Manual API edits keep their in-place semantics
— a user correction is an authority, not an evolution.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.memories.models import Memory
from src.domains.memories.service import MemoryService


def _memory(**over) -> MagicMock:
    row = MagicMock(spec=Memory)
    row.id = over.get("id", uuid4())
    row.user_id = over.get("user_id", uuid4())
    row.content = over.get("content", "il habite à Paris")
    row.category = over.get("category", "identity")
    row.emotional_weight = over.get("emotional_weight", 0)
    row.trigger_topic = over.get("trigger_topic", "logement")
    row.usage_nuance = over.get("usage_nuance", "")
    row.importance = over.get("importance", 0.7)
    row.pinned = False
    row.invalidated_at = None
    row.superseded_by_id = None
    return row


@pytest.mark.unit
class TestModelColumns:
    def test_memory_carries_the_supersession_trail(self):
        assert hasattr(Memory, "invalidated_at")
        assert hasattr(Memory, "superseded_by_id")


@pytest.mark.unit
class TestInvalidate:
    async def test_invalidate_soft_deletes_without_successor(self):
        repo = MagicMock()
        repo.update = AsyncMock(side_effect=lambda m: m)
        with patch("src.domains.memories.service.MemoryRepository", return_value=repo):
            service = MemoryService(MagicMock())
            memory = _memory()

            await service.invalidate_memory(memory)

        assert memory.invalidated_at is not None
        assert memory.superseded_by_id is None
        repo.update.assert_awaited_once_with(memory)


@pytest.mark.unit
class TestSupersedeWithUpdate:
    async def test_supersede_creates_successor_and_links_the_old_row(self):
        repo = MagicMock()
        created: list[Memory] = []

        async def _create(m):
            m.id = uuid4()
            created.append(m)
            return m

        repo.create = AsyncMock(side_effect=_create)
        repo.update = AsyncMock(side_effect=lambda m: m)

        with (
            patch("src.domains.memories.service.MemoryRepository", return_value=repo),
            patch(
                "src.domains.memories.service._generate_dual_embeddings",
                new=AsyncMock(return_value=(None, None)),
            ),
        ):
            service = MemoryService(MagicMock())
            old = _memory(content="il habite à Paris")

            successor = await service.supersede_with_update(
                memory=old, content="il habite à Lyon", importance=0.8
            )

        assert successor in created
        assert successor.content == "il habite à Lyon"
        # Untouched fields carry over from the superseded row.
        assert successor.category == old.category
        assert successor.trigger_topic == old.trigger_topic
        # The old row keeps existing but leaves the active set, pointing
        # at its successor — history preserved, never rewritten.
        assert old.invalidated_at is not None
        assert old.superseded_by_id == successor.id
        assert old.content == "il habite à Paris"
        repo.update.assert_awaited()

    async def test_supersession_timestamps_are_utc_aware(self):
        repo = MagicMock()
        repo.create = AsyncMock(side_effect=lambda m: m)
        repo.update = AsyncMock(side_effect=lambda m: m)
        with (
            patch("src.domains.memories.service.MemoryRepository", return_value=repo),
            patch(
                "src.domains.memories.service._generate_dual_embeddings",
                new=AsyncMock(return_value=(None, None)),
            ),
        ):
            service = MemoryService(MagicMock())
            old = _memory()

            await service.supersede_with_update(memory=old, content="nouveau")

        assert old.invalidated_at.tzinfo is not None
        assert old.invalidated_at.utcoffset().total_seconds() == 0
        assert old.invalidated_at <= datetime.now(UTC)


@pytest.mark.unit
class TestInvalidatedPurge:
    """Invalidated rows are a TRAIL, not an archive: they purge after a
    settings-driven retention window (their successors carry the facts)."""

    async def test_purge_statement_targets_only_stale_invalidated_rows(self):
        from sqlalchemy.dialects import postgresql

        from src.domains.memories.repository import MemoryRepository

        captured: list = []

        async def _execute(stmt, *args, **kwargs):
            captured.append(stmt)
            result = MagicMock()
            result.rowcount = 3
            return result

        db = MagicMock()
        db.execute = AsyncMock(side_effect=_execute)
        db.commit = AsyncMock()
        repo = MemoryRepository(db)

        deleted = await repo.delete_invalidated_older_than(days=90)

        assert deleted == 3
        sql = str(captured[0].compile(dialect=postgresql.dialect())).lower()
        assert "delete from memories" in sql
        assert "invalidated_at is not null" in sql
        assert "invalidated_at <" in sql


@pytest.mark.unit
class TestSupersessionGuards:
    """Structural guards (defense in depth over the callers' checks):
    a pinned fact is user-locked, an already-invalidated fact is a stale
    write — both are contract breaches, loud by design."""

    async def test_pinned_memory_cannot_be_invalidated(self):
        repo = MagicMock()
        repo.update = AsyncMock()
        with patch("src.domains.memories.service.MemoryRepository", return_value=repo):
            service = MemoryService(MagicMock())
            memory = _memory()
            memory.pinned = True

            with pytest.raises(ValueError, match="pinned"):
                await service.invalidate_memory(memory)

        repo.update.assert_not_awaited()

    async def test_pinned_memory_cannot_be_superseded(self):
        repo = MagicMock()
        repo.create = AsyncMock()
        with patch("src.domains.memories.service.MemoryRepository", return_value=repo):
            service = MemoryService(MagicMock())
            memory = _memory()
            memory.pinned = True

            with pytest.raises(ValueError, match="pinned"):
                await service.supersede_with_update(memory=memory, content="x")

        repo.create.assert_not_awaited()

    async def test_already_invalidated_memory_cannot_be_superseded_again(self):
        from datetime import UTC
        from datetime import datetime as _dt

        repo = MagicMock()
        repo.create = AsyncMock()
        with patch("src.domains.memories.service.MemoryRepository", return_value=repo):
            service = MemoryService(MagicMock())
            memory = _memory()
            memory.invalidated_at = _dt.now(UTC)

            with pytest.raises(ValueError, match="invalidated"):
                await service.supersede_with_update(memory=memory, content="x")

        repo.create.assert_not_awaited()
