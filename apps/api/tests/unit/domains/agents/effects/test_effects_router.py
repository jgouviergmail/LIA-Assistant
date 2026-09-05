"""Reading the register is private, exact, and bounded (ADR-263).

Three properties, each of which the register would be worthless without:

- **private**: a user reads their own rows and no one else's, and the endpoint
  does not even confirm that another user's effect exists;
- **exact**: the journal ships the total from an aggregate, never the length of
  the page (ADR-185 — a count shown to a user is exact or it does not exist);
- **keys, not sentences**: the payload carries ``label_key`` and ``values``, so
  the wording follows the reader's language rather than the writer's.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.models import EffectStatus
from src.domains.agents.effects.router import (
    MAX_PAGE_SIZE,
    EffectPage,
    _entry,
    list_journal,
    list_run_effects,
)

pytestmark = [pytest.mark.unit]

OWNER = uuid.uuid4()
SOMEONE_ELSE = uuid.uuid4()


def _row(user_id: uuid.UUID = OWNER, tool_name: str = "control_hue_light_tool") -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        tool_name=tool_name,
        mutation_policy="reversible",
        status=EffectStatus.SUCCEEDED,
        source=SimpleNamespace(value="user"),
        execution_mode="pipeline",
        approval_kind=None,
        error_code=None,
        claimed_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
        label=b"encrypted",
    )


class _Repository:
    def __init__(self, rows: list[Any], total: int | None = None) -> None:
        self._rows = rows
        self._total = len(rows) if total is None else total

    async def list_for_run(self, run_id: str) -> list[Any]:
        return self._rows

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int, status: Any = None
    ) -> tuple[list[Any], int]:
        self.seen = {"user_id": user_id, "limit": limit, "offset": offset, "status": status}
        rows = [row for row in self._rows if status is None or row.status == status]
        return rows[offset : offset + limit], self._total


def _with(repository: _Repository, label: dict[str, Any] | None = None) -> Any:
    return (
        patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository",
            side_effect=lambda _db: repository,
        ),
        patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
            staticmethod(lambda _row: label),
        ),
    )


class TestOneUserNeverSeesAnother:
    async def test_a_run_of_someone_else_reads_as_empty(self) -> None:
        """Empty, not forbidden: a 403 would confirm the run exists."""
        repository = _Repository([_row(user_id=SOMEONE_ELSE)])
        patches = _with(repository)
        with patches[0], patches[1]:
            entries = await list_run_effects("run-1", db=object(), user=SimpleNamespace(id=OWNER))
        assert entries == []

    async def test_the_owner_reads_their_own_rows(self) -> None:
        repository = _Repository([_row(), _row(user_id=SOMEONE_ELSE)])
        patches = _with(repository)
        with patches[0], patches[1]:
            entries = await list_run_effects("run-1", db=object(), user=SimpleNamespace(id=OWNER))
        assert len(entries) == 1

    async def test_the_journal_asks_only_for_the_caller(self) -> None:
        repository = _Repository([_row() for _ in range(3)])
        patches = _with(repository)
        with patches[0], patches[1]:
            await list_journal(limit=20, offset=0, db=object(), user=SimpleNamespace(id=OWNER))
        assert repository.seen["user_id"] == OWNER


class TestTheCountIsExact:
    async def test_the_total_is_the_aggregate_not_the_page(self) -> None:
        repository = _Repository([_row() for _ in range(50)], total=1234)
        patches = _with(repository)
        with patches[0], patches[1]:
            page = await list_journal(
                limit=10, offset=0, db=object(), user=SimpleNamespace(id=OWNER)
            )

        assert isinstance(page, EffectPage)
        assert len(page.entries) == 10
        assert page.total == 1234, "the page length would under-report the moment data grows"
        assert page.limit == 10

    def test_the_page_size_ceiling_is_stated(self) -> None:
        """A cap is published, never applied in silence."""
        import inspect

        signature = inspect.signature(list_journal)
        limit = signature.parameters["limit"].default
        constraints = [getattr(item, "le", None) for item in getattr(limit, "metadata", [])]
        assert (
            MAX_PAGE_SIZE in constraints
        ), f"the page ceiling is not published on the query parameter: {constraints}"


class TestTheFilterIsServerSide:
    """A total computed over everything, shown above a filtered list, lies."""

    async def test_the_status_travels_to_the_query(self) -> None:
        repository = _Repository([_row()])
        patches = _with(repository)
        with patches[0], patches[1]:
            await list_journal(
                limit=20,
                offset=0,
                status=EffectStatus.FAILED,
                db=object(),
                user=SimpleNamespace(id=OWNER),
            )

        assert repository.seen["status"] is EffectStatus.FAILED

    async def test_no_filter_asks_for_everything(self) -> None:
        repository = _Repository([_row()])
        patches = _with(repository)
        with patches[0], patches[1]:
            await list_journal(limit=20, offset=0, db=object(), user=SimpleNamespace(id=OWNER))

        assert repository.seen["status"] is None

    def test_an_unknown_status_cannot_reach_the_query(self) -> None:
        """Typed as the enum: FastAPI answers 422, never a 500 from a ValueError."""
        import inspect

        annotation = inspect.signature(list_journal).parameters["status"].annotation
        assert "EffectStatus" in str(annotation)


class TestTheEntryShape:
    def test_it_carries_keys_and_values_never_a_sentence(self) -> None:
        label = {"i18n_key": "effects.labels.draft.email", "values": {"recipient": "Marie"}}
        with patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
            staticmethod(lambda _row: label),
        ):
            entry = _entry(_row())

        assert entry.label_key == "effects.labels.draft.email"
        assert entry.values == {"recipient": "Marie"}
        assert not hasattr(entry, "label")

    def test_an_unreadable_label_still_produces_a_line(self) -> None:
        with patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
            staticmethod(lambda _row: None),
        ):
            entry = _entry(_row())

        assert entry.label_key == "effects.labels.generic"
        assert entry.values == {"tool": "control_hue_light_tool"}

    def test_enum_columns_are_rendered_as_their_stored_spelling(self) -> None:
        with patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
            staticmethod(lambda _row: None),
        ):
            entry = _entry(_row())

        assert entry.status == "succeeded"
        assert entry.source == "user"


class TestTheRegisterIsReadOnly:
    def test_no_route_writes(self) -> None:
        """An executor able to edit its own record defeats the register."""
        from src.domains.agents.effects.router import router

        methods = {method for route in router.routes for method in getattr(route, "methods", set())}
        assert methods <= {"GET", "HEAD", "OPTIONS"}, f"a writing route appeared: {methods}"
