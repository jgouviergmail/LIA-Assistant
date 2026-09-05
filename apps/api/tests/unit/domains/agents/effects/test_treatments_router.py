"""Reading the consultation register (ADR-263, lot 4).

Same three properties as its sibling, for the same reasons: **private** (a
register is only trustworthy if it is also private), **exact** (the total comes
from an aggregate over the filtered set, never the page length — ADR-185), and
**keys, not sentences** (the API ships a domain key the client resolves, so the
wording follows the reader's language rather than the writer's).

One property is this register's own: a consultation row has no arguments to
leak, and the payload must not acquire any on the way out.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.treatments_router import (
    MAX_PAGE_SIZE,
    TreatmentPage,
    _entry,
    list_run_treatments,
    list_treatment_journal,
)

pytestmark = [pytest.mark.unit]

OWNER = uuid.uuid4()
SOMEONE_ELSE = uuid.uuid4()


def _row(user_id: uuid.UUID = OWNER, tool_name: str = "get_emails_tool") -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        tool_name=tool_name,
        mutation_policy="read",
        outcome=SimpleNamespace(value="ok"),
        source=SimpleNamespace(value="user"),
        execution_mode="pipeline",
        thread_id="conv-1",
        run_id="run-1",
        duration_ms=142,
        occurred_at=datetime.now(UTC),
    )


class _Repository:
    def __init__(self, rows: list[Any], total: int | None = None) -> None:
        self._rows = rows
        self._total = len(rows) if total is None else total
        self.seen: dict[str, Any] = {}

    async def list_for_run(self, run_id: str) -> list[Any]:
        return self._rows

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        tool_name: str | None = None,
        since: Any = None,
        until: Any = None,
    ) -> tuple[list[Any], int]:
        self.seen = {
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
            "tool_name": tool_name,
            "since": since,
            "until": until,
        }
        rows = [row for row in self._rows if tool_name is None or row.tool_name == tool_name]
        return rows[offset : offset + limit], self._total


def _user(user_id: uuid.UUID = OWNER) -> Any:
    return SimpleNamespace(id=user_id, language="fr", timezone="Europe/Paris")


def _with(repository: _Repository) -> Any:
    """Same seam as the action register's tests: the repository, replaced."""
    return patch(
        "src.domains.agents.effects.treatment_repository.TreatmentRepository",
        side_effect=lambda _db: repository,
    )


class TestTheEntryCarriesKeysNotSentences:
    def test_it_ships_a_domain_key(self) -> None:
        entry = _entry(_row())

        assert entry.domain == "email"
        assert entry.tool_name == "get_emails_tool"

    def test_it_ships_no_translated_string(self) -> None:
        """The client resolves the wording; the API never guesses a language."""
        payload = _entry(_row()).model_dump()

        assert "E-mails" not in str(payload)
        assert "Emails" not in str(payload)

    def test_it_carries_nothing_of_what_was_asked(self) -> None:
        payload = _entry(_row()).model_dump()

        assert "arguments" not in payload
        assert "query" not in payload


class TestTheRegisterIsPrivate:
    async def test_another_users_row_is_invisible_on_a_run(self) -> None:
        """Invisible, not forbidden: a register must not confirm existence."""
        repository = _Repository([_row(SOMEONE_ELSE)])

        with _with(repository):
            entries = await list_run_treatments("run-1", db=object(), user=_user())

        assert entries == []

    async def test_the_journal_asks_only_for_the_callers_rows(self) -> None:
        repository = _Repository([_row()])

        with _with(repository):
            await list_treatment_journal(
                limit=20,
                offset=0,
                tool_name=None,
                since=None,
                until=None,
                db=object(),
                user=_user(),
            )

        assert repository.seen["user_id"] == OWNER


class TestTheTotalIsExact:
    async def test_the_total_comes_from_the_aggregate_not_the_page(self) -> None:
        repository = _Repository([_row() for _ in range(5)], total=873)

        with _with(repository):
            page = await list_treatment_journal(
                limit=2,
                offset=0,
                tool_name=None,
                since=None,
                until=None,
                db=object(),
                user=_user(),
            )

        assert isinstance(page, TreatmentPage)
        assert len(page.entries) == 2
        assert page.total == 873

    async def test_a_filter_reaches_the_repository_so_the_count_matches(self) -> None:
        """Filtering client-side would leave the total describing another set."""
        repository = _Repository([_row(), _row(tool_name="get_events_tool")])

        with _with(repository):
            page = await list_treatment_journal(
                limit=20,
                offset=0,
                tool_name="get_events_tool",
                since=None,
                until=None,
                db=object(),
                user=_user(),
            )

        assert repository.seen["tool_name"] == "get_events_tool"
        assert [entry.tool_name for entry in page.entries] == ["get_events_tool"]

    async def test_a_period_reaches_the_repository_too(self) -> None:
        since = datetime(2026, 9, 1, tzinfo=UTC)
        until = datetime(2026, 9, 4, tzinfo=UTC)
        repository = _Repository([_row()])

        with _with(repository):
            await list_treatment_journal(
                limit=20,
                offset=0,
                tool_name=None,
                since=since,
                until=until,
                db=object(),
                user=_user(),
            )

        assert repository.seen["since"] == since
        assert repository.seen["until"] == until


class TestTheCapIsStated:
    def test_the_page_ceiling_exists(self) -> None:
        assert MAX_PAGE_SIZE >= 20

    async def test_the_applied_page_size_travels_in_the_answer(self) -> None:
        with _with(_Repository([_row()])):
            page = await list_treatment_journal(
                limit=7,
                offset=3,
                tool_name=None,
                since=None,
                until=None,
                db=object(),
                user=_user(),
            )

        assert page.limit == 7
        assert page.offset == 3
