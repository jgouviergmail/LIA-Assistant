"""The listener's taste: only what the start allowed, only preferences, as many as are shown."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.domains.radio.prompting import INTERESTS_SHOWN_MAX, STATED_TASTES_SHOWN_MAX
from src.domains.radio.readers import taste as module
from src.domains.radio.readers.taste import read_taste

pytestmark = pytest.mark.unit


@dataclass
class Reads:
    """What the fake repositories were asked."""

    interests: list[int] = field(default_factory=list)
    memories: list[tuple[str, int]] = field(default_factory=list)
    memories_fail: bool = False


class Recorder:
    """What the read recorded as opened and failed."""

    def __init__(self) -> None:
        self.rows: list[tuple[frozenset[str], frozenset[str]]] = []

    def __call__(self, *, opened: frozenset[str], failed: frozenset[str], duration_ms: int) -> None:
        self.rows.append((opened, failed))


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> Reads:
    seen = Reads()

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    class Interests:
        def __init__(self, db: object) -> None:
            self._db = db

        async def list_active_by_signals(
            self, user_id: UUID, *, limit: int
        ) -> list[SimpleNamespace]:
            seen.interests.append(limit)
            return [SimpleNamespace(topic="astronomy"), SimpleNamespace(topic="  ")]

    class Memories:
        def __init__(self, db: object) -> None:
            self._db = db

        async def get_by_category(
            self, user_id: UUID, category: str, *, limit: int
        ) -> list[SimpleNamespace]:
            seen.memories.append((category, limit))
            if seen.memories_fail:
                raise ConnectionError("database unavailable")
            return [SimpleNamespace(content="Dislikes football")]

    monkeypatch.setattr(module, "get_db_context", session)
    monkeypatch.setattr(module, "InterestRepository", Interests)
    monkeypatch.setattr(module, "MemoryRepository", Memories)
    return seen


async def test_only_preferences_are_read_and_as_many_as_the_writer_is_shown(reads: Reads) -> None:
    recorder = Recorder()
    taste = await read_taste(uuid4(), interests_allowed=True, stated_allowed=True, record=recorder)
    assert (taste.interests, taste.stated) == (("astronomy",), ("Dislikes football",))
    assert reads.interests == [INTERESTS_SHOWN_MAX]
    assert reads.memories == [("preference", STATED_TASTES_SHOWN_MAX)]
    assert recorder.rows == [(frozenset({"interests", "memories"}), frozenset())]


async def test_a_part_the_start_did_not_allow_is_neither_read_nor_recorded(reads: Reads) -> None:
    recorder = Recorder()
    taste = await read_taste(uuid4(), interests_allowed=True, stated_allowed=False, record=recorder)
    assert (taste.stated, reads.memories) == ((), [])
    assert recorder.rows == [(frozenset({"interests"}), frozenset())]
    nothing = await read_taste(
        uuid4(), interests_allowed=False, stated_allowed=False, record=recorder
    )
    assert (nothing.interests, nothing.stated, len(recorder.rows)) == ((), (), 1)


async def test_a_blind_part_is_empty_and_recorded_failed_the_other_kept(reads: Reads) -> None:
    reads.memories_fail = True
    recorder = Recorder()
    taste = await read_taste(uuid4(), interests_allowed=True, stated_allowed=True, record=recorder)
    assert (taste.interests, taste.stated) == (("astronomy",), ())
    assert recorder.rows == [(frozenset({"interests", "memories"}), frozenset({"memories"}))]
