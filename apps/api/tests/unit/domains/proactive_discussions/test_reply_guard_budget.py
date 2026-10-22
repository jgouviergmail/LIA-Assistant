"""The live reply guards are read complete or not at all, under the operator's bounds (ADR-359).

Past either bound every run defers until memory acknowledges the replies or their
lifetime ends, so both bounds are settings, like the directives' own budget.
"""

from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.domains.proactive_discussions.replies import pending_controls
from src.domains.shared.discussion_directives import DirectiveBudgetExceeded

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)


class _Rows:
    def __init__(self, rows: list[tuple[UUID, str]]) -> None:
        self._rows = rows

    def tuples(self) -> Self:
        return self

    def all(self) -> list[tuple[UUID, str]]:
        return self._rows


class _Session:
    """The live replies the guard query found."""

    def __init__(self, rows: list[tuple[UUID, str]]) -> None:
        self.rows = rows

    async def execute(self, statement: object) -> _Rows:
        return _Rows(self.rows)


def _replies(count: int, text: str = "Please never mention that appointment.") -> list:
    return [(uuid4(), text) for _ in range(count)]


async def test_more_live_guards_than_the_operator_allows_defer_the_run(monkeypatch):
    monkeypatch.setattr(settings, "discussion_reply_guard_max_rows", 2)
    guards = await pending_controls(_Session(_replies(2)), uuid4(), memory_enabled=True, now=NOW)
    assert len(guards) == 2
    with pytest.raises(DirectiveBudgetExceeded):
        await pending_controls(_Session(_replies(3)), uuid4(), memory_enabled=True, now=NOW)


async def test_guards_longer_than_the_operator_allows_defer_the_run(monkeypatch):
    long_reply = _replies(1, "Please never mention that appointment again. " * 40)
    assert await pending_controls(_Session(long_reply), uuid4(), memory_enabled=True, now=NOW)
    monkeypatch.setattr(settings, "discussion_reply_guard_max_tokens", 100)
    with pytest.raises(DirectiveBudgetExceeded):
        await pending_controls(_Session(long_reply), uuid4(), memory_enabled=True, now=NOW)
