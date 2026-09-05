"""What the meeting repository SENDS to the database (ADR-258, amended 2026-09-05).

The transitions are ``UPDATE … WHERE`` statements and the ``status`` column is a
``native_enum=False`` enum: it stores the member NAME (``STOPPED``), never the
value (``stopped``). Measured in production on 2026-09-05: a bare enum member
inside ``case()`` is bound as ``NullType`` — no bind processor, the VALUE goes
to the database, ``RETURNING`` cannot read it back, the transaction rolls back
and the meeting stays ``processing`` forever. These tests compile the statements
the repository builds and assert what every enum bind renders.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import BindParameter

from src.domains.meetings.models import MeetingStage, MeetingStatus
from src.domains.meetings.repository import MeetingRepository

pytestmark = pytest.mark.unit


class _CapturingSession:
    """Records the statements executed and answers ``RETURNING`` with a fixed row.

    The row carries what SQLAlchemy delivers AFTER the column's result processor
    (an enum member for an ``Enum`` column), which is what the repository reads.
    """

    def __init__(self, row: tuple[Any, ...] | None = None) -> None:
        self.statements: list[Any] = []
        self._row = row

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.statements.append(statement)
        row = self._row

        class _Result:
            rowcount = 1

            @staticmethod
            def first() -> tuple[Any, ...] | None:
                return row

            @staticmethod
            def all() -> list[tuple[Any, ...]]:
                return [row] if row is not None else []

            @staticmethod
            def scalars() -> Any:
                class _Scalars:
                    @staticmethod
                    def all() -> list[Any]:
                        return []

                return _Scalars()

        return _Result()

    async def commit(self) -> None:
        return None


def _enum_binds(statement: Any) -> dict[str, tuple[type, Any]]:
    """``{bind name: (type, value the driver receives)}`` for every non-integer bind."""
    compiled = statement.compile(dialect=postgresql.asyncpg.dialect())
    rendered: dict[str, tuple[type, Any]] = {}
    seen: set[int] = set()
    # ``compiled.binds`` lists each parameter under its anonymous key AND its
    # positional name: dedupe by identity so a bind is counted once.
    for name, bind in compiled.binds.items():
        assert isinstance(bind, BindParameter)
        if id(bind) in seen or not isinstance(bind.value, MeetingStatus):
            continue
        seen.add(id(bind))
        processor = bind.type._cached_bind_processor(compiled.dialect)
        rendered[name] = (type(bind.type), processor(bind.value) if processor else bind.value)
    return rendered


async def test_fail_or_retry_binds_every_status_as_the_enum_name() -> None:
    session = _CapturingSession(row=(MeetingStatus.STOPPED,))
    repo = MeetingRepository(session)  # type: ignore[arg-type]

    status = await repo.fail_or_retry(
        uuid.uuid4(), code="synthesis_failed", message="boom", max_attempts=3
    )

    assert status is MeetingStatus.STOPPED
    binds = _enum_binds(session.statements[0])
    # Three statuses travel: the WHERE (processing) and the two case() results.
    assert len(binds) == 3, binds
    for name, (bind_type, rendered) in binds.items():
        assert bind_type is SAEnum, f"{name} is bound as {bind_type.__name__}"
        assert rendered in {"PROCESSING", "STOPPED", "FAILED"}, f"{name} renders {rendered!r}"


async def test_requeue_expired_leases_binds_its_statuses_and_error_code_typed() -> None:
    """The reaper's dead-letter branch writes two enum-typed columns through case()."""
    session = _CapturingSession()
    repo = MeetingRepository(session)  # type: ignore[arg-type]

    await repo.requeue_expired_leases(max_attempts=3)

    binds = _enum_binds(session.statements[0])
    assert {rendered for _, rendered in binds.values()} == {"PROCESSING", "STOPPED", "FAILED"}
    assert all(bind_type is SAEnum for bind_type, _ in binds.values()), binds


async def test_retention_only_purges_ready_meetings() -> None:
    """A failed meeting keeps its audio for the retry its owner may ask for."""
    session = _CapturingSession()
    repo = MeetingRepository(session)  # type: ignore[arg-type]

    await repo.fetch_audio_to_purge(limit=10)

    binds = _enum_binds(session.statements[0])
    assert {rendered for _, rendered in binds.values()} == {"READY"}


async def test_delete_unless_leased_deletes_by_the_database_clock() -> None:
    session = _CapturingSession()
    repo = MeetingRepository(session)  # type: ignore[arg-type]

    assert await repo.delete_unless_leased(uuid.uuid4()) is True

    rendered = str(session.statements[0].compile(dialect=postgresql.asyncpg.dialect()))
    assert rendered.startswith("DELETE FROM meetings")
    assert "lease_expires_at < now()" in rendered and "lease_expires_at IS NULL" in rendered
    binds = _enum_binds(session.statements[0])
    assert {rendered for _, rendered in binds.values()} == {"PROCESSING"}


async def test_heartbeat_writes_the_checkpoint_values_it_is_given() -> None:
    """A checkpoint is a heartbeat carrying columns: same ownership predicate, one statement."""
    session = _CapturingSession()
    repo = MeetingRepository(session)  # type: ignore[arg-type]

    await repo.heartbeat(
        uuid.uuid4(),
        worker_id="w1",
        lease_ttl_s=900,
        stage=MeetingStage.TRANSCRIBING,
        values={"audio_path": "u/m/audio.webm", "audio_duration_seconds": 33.0},
    )

    compiled = session.statements[0].compile(dialect=postgresql.asyncpg.dialect())
    rendered = str(compiled)
    assert "audio_path=" in rendered and "audio_duration_seconds=" in rendered
    assert "worker_id = " in rendered  # the ownership predicate stays
