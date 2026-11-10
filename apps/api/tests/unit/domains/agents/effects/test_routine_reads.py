"""What routine runs READ, offered to the habits domain (ADR-375).

The rows are the treatments register's (every row is a consultation); the
domain is the register's own reading of the capability (``treatment_domain``).
Only registered domains leave: an unknown capability is not a need LIA could
propose to automate.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.effects import routine_reads
from src.domains.habits import usage_ports

pytestmark = pytest.mark.unit


def _db(rows: list[tuple[str, str]]) -> Any:
    result = MagicMock()
    result.all.return_value = rows
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


async def test_each_run_reads_the_domains_of_its_consultations() -> None:
    db = _db([("run-1", "get_events_tool"), ("run-1", "get_emails_tool"), ("run-2", "x")])
    domains = {"get_events_tool": "event", "get_emails_tool": "email", "x": "unknown"}
    with patch.object(routine_reads, "treatment_domain", side_effect=domains.__getitem__):
        read = await routine_reads.read_routine_run_domains(db, uuid4(), ["run-1", "run-2"])
    assert read == {"run-1": frozenset({"event", "email"})}


async def test_no_run_asked_reads_no_database() -> None:
    db = _db([])
    assert await routine_reads.read_routine_run_domains(db, uuid4(), []) == {}
    db.execute.assert_not_awaited()


def test_the_reader_is_offered_to_habits_at_import() -> None:
    usage_ports.install_routine_reads_reader(routine_reads.read_routine_run_domains)
    assert usage_ports.routine_reads_reader() is routine_reads.read_routine_run_domains
