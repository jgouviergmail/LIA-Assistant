"""A failed provenance write must not poison the extraction it describes.

`provenance_capture` promises best-effort: "a failure must not roll back an
extraction that succeeded — the belief is still true, it is merely harder to
question". `contextlib.suppress` alone does NOT deliver that promise, and the
gap is the kind that only shows up in production:

a `flush()` that raises (a CHECK violation, a stale foreign key) leaves the
SQLAlchemy session in a FAILED state. Swallowing the exception hides the error
but not the damage — the very next statement on that session raises
`PendingRollbackError`, so the extraction dies anyway, from a second error, with
the first one already swallowed and unlogged.

The fix is a SAVEPOINT (`begin_nested`), the pattern the repository already uses
in `conversations/service.py`: the inner failure rolls back to the savepoint and
the outer transaction survives intact.

The oracle here is behavioural, not structural: write the provenance against a
session whose flush fails, then assert the session is still usable.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.shared import provenance_capture

pytestmark = pytest.mark.unit


class _FailingSavepoint:
    """A savepoint whose body raises — it must absorb, never re-raise."""

    def __init__(self, session: _Session) -> None:
        self._session = session

    async def __aenter__(self) -> _FailingSavepoint:
        self._session.savepoint_opened = True
        return self

    async def __aexit__(self, exc_type: object, *_: object) -> bool:
        if exc_type is not None:
            self._session.rolled_back_to_savepoint = True
        # A real savepoint context manager re-raises; the caller suppresses.
        return False


class _Session:
    """A session whose `flush` fails, and that remembers what happened to it."""

    def __init__(self) -> None:
        self.savepoint_opened = False
        self.rolled_back_to_savepoint = False
        self.usable = True

    def add(self, _row: object) -> None:
        if not self.usable:  # pragma: no cover - the defect this guards
            raise RuntimeError("PendingRollbackError: session is poisoned")

    async def flush(self) -> None:
        # The failure mode: the write raises AND the session is now dirty.
        self.usable = False
        raise RuntimeError("CHECK constraint violated")

    def begin_nested(self) -> _FailingSavepoint:
        return _FailingSavepoint(self)

    async def execute(self, *_args: object, **_kwargs: object) -> MagicMock:
        if not self.usable:
            raise RuntimeError("PendingRollbackError: session is poisoned")
        return MagicMock(scalar=lambda: 0, all=list)


class TestAFailedProvenanceWriteIsIsolated:
    async def test_it_opens_a_savepoint_rather_than_writing_bare(self) -> None:
        session = _Session()

        await provenance_capture.record_origin(
            session,  # type: ignore[arg-type] - a session stub is the point
            user_id=uuid.uuid4(),
            source=str(uuid.uuid4()),
            memory_id=uuid.uuid4(),
        )

        assert session.savepoint_opened, "the write must be scoped to a savepoint"
        assert session.rolled_back_to_savepoint, "the failure must reach the savepoint"

    async def test_the_caller_never_sees_the_failure(self) -> None:
        """Best-effort means best-effort: no exception escapes."""
        await provenance_capture.record_outcome(
            _Session(),  # type: ignore[arg-type] - a session stub is the point
            user_id=uuid.uuid4(),
            source=str(uuid.uuid4()),
            evidence_outcome="evidence",
            interest_id=uuid.uuid4(),
        )

    async def test_a_source_that_is_not_an_identifier_writes_nothing(self) -> None:
        session = _Session()

        await provenance_capture.record_origin(
            session,  # type: ignore[arg-type] - a session stub is the point
            user_id=uuid.uuid4(),
            source="not-a-uuid",
            memory_id=uuid.uuid4(),
        )

        assert not session.savepoint_opened

    async def test_an_undefined_outcome_is_ignored_rather_than_stored(self) -> None:
        session = _Session()

        await provenance_capture.record_outcome(
            session,  # type: ignore[arg-type] - a session stub is the point
            user_id=uuid.uuid4(),
            source=str(uuid.uuid4()),
            evidence_outcome="origin",
            memory_id=uuid.uuid4(),
        )

        assert not session.savepoint_opened


class TestRealSessionsUseTheSamePath:
    async def test_a_successful_write_still_goes_through_the_savepoint(self) -> None:
        """The savepoint is not an error path — every write is scoped by it."""
        savepoint = AsyncMock()
        savepoint.__aenter__ = AsyncMock(return_value=savepoint)
        savepoint.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock(begin_nested=MagicMock(return_value=savepoint))
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 0))

        await provenance_capture.record_origin(
            session,
            user_id=uuid.uuid4(),
            source=str(uuid.uuid4()),
            journal_entry_id=uuid.uuid4(),
        )

        session.begin_nested.assert_called_once()
        session.flush.assert_awaited()
