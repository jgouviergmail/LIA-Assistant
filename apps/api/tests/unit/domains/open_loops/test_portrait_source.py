"""The open loops as the portrait reads them (2026-10-12): gated, whole, never raising.

Every OPEN loop, earliest deadline first, with its direction, its counterparty
and its due hint; two gates read at call time; a failed read is ``unavailable``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.journals.portrait_catalogue import eligible_source_items
from src.domains.open_loops import portrait_source as module
from src.domains.open_loops.portrait_source import read_open_loops

pytestmark = pytest.mark.unit


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _loop(
    subject: str, direction: str, counterparty: str | None, due: datetime | None
) -> SimpleNamespace:
    return SimpleNamespace(
        subject=subject, direction=direction, counterparty=counterparty, due_hint=due
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    rows = [
        _loop("Renvoyer le devis", "user_owes", "l'ébéniste", datetime(2026, 10, 15, tzinfo=UTC)),
        _loop("Réponse du fournisseur\nsur le prix", "waiting_on_other", None, None),
    ]
    reader = AsyncMock(return_value=rows)
    monkeypatch.setattr(module, "get_db_context", _ctx(AsyncMock()))
    monkeypatch.setattr(module, "_rows", reader)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module.settings, "open_loops_enabled", True, raising=False)
    return SimpleNamespace(rows=reader)


async def test_every_open_loop_is_rendered_whole_with_its_direction(
    harness: SimpleNamespace,
) -> None:
    section = await read_open_loops(user_id=uuid.uuid4(), language="fr")
    assert section.key == "open_loops" and section.status == "used"
    assert (section.used, section.total) == (2, 2)
    assert section.text.startswith("## OPEN LOOPS")
    assert (
        "- Renvoyer le devis (the person owes it, l'ébéniste; due around 2026-10-15)"
        in section.text
    )
    assert "- Réponse du fournisseur sur le prix (the person is waiting on someone)" in section.text
    assert len(eligible_source_items("open_loops", section.text)) == 2


async def test_no_open_loop_is_empty(harness: SimpleNamespace) -> None:
    harness.rows.return_value = []
    section = await read_open_loops(user_id=uuid.uuid4(), language="fr")
    assert section.status == "empty" and section.total == 0


async def test_a_closed_gate_answers_disabled(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "open_loops_enabled", False, raising=False)
    assert (await read_open_loops(user_id=uuid.uuid4(), language="fr")).status == "disabled"
    monkeypatch.setattr(module.settings, "open_loops_enabled", True, raising=False)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=False))
    assert (await read_open_loops(user_id=uuid.uuid4(), language="fr")).status == "disabled"
    harness.rows.assert_not_awaited()


async def test_a_failed_read_is_named_never_read_as_empty(harness: SimpleNamespace) -> None:
    harness.rows.side_effect = RuntimeError("db gone")
    section = await read_open_loops(user_id=uuid.uuid4(), language="fr")
    assert section.status == "unavailable" and section.text == ""
