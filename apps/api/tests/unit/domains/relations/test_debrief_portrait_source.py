"""The relationship debriefs as the portrait reads them (2026-09-16, part B).

Three gates; READY rows only, under the injection age the settings publish,
measured against the reader's LOCAL day; the headline and where things stand,
clamped; the date so the model treats the line as DATED (ADR-269).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.relations.debrief import portrait_source as module
from src.domains.relations.debrief.portrait_source import read_relation_debriefs
from src.domains.shared.portrait_sources import SourceBudget

pytestmark = pytest.mark.unit

BUDGET = SourceBudget(max_items=2, item_max_chars=40)


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _row(person: str, day: date, headline: str, stand: str) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=person,
        generated_for=day,
        body={"version": 1, "headline": headline, "where_we_stand": stand},
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    repo = AsyncMock()
    repo.list_injectable.return_value = [
        _row(
            "Claire Dupont",
            date(2026, 9, 15),
            "Le devis avance",
            "Elle attend une réponse sur le prix.",
        ),
        _row("Marc", date(2026, 9, 12), "Rien de neuf", "y" * 100),
        _row("Zoé", date(2026, 9, 10), "Vacances", "Partie en Grèce."),
    ]
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(relation_debrief_enabled=True, timezone="Europe/Paris")
    monkeypatch.setattr(module, "get_db_context", _ctx(db))
    monkeypatch.setattr(module, "RelationDebriefRepository", lambda db: repo)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module.settings, "relation_debrief_enabled", True, raising=False)
    monkeypatch.setattr(
        module.settings, "relation_debrief_injection_max_age_days", 7, raising=False
    )
    monkeypatch.setattr(
        module,
        "read_of",
        lambda row: SimpleNamespace(
            body=SimpleNamespace(
                headline=row.body["headline"], where_we_stand=row.body["where_we_stand"]
            )
        ),
    )
    return SimpleNamespace(repo=repo, db=db)


async def test_the_section_lists_the_newest_debriefs_dated_and_clamped(
    harness: SimpleNamespace,
) -> None:
    section = await read_relation_debriefs(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "used" and (section.used, section.total) == (2, 3)
    assert "## RELATIONSHIP DEBRIEFS" in section.text and "2 of 3" in section.text
    assert (
        "- Claire Dupont (written 2026-09-15): Le devis avance — Elle attend une réponse sur le prix."
        in section.text
    )
    assert (
        "- Marc (written 2026-09-12): Rien de neuf — " in section.text
        and "y" * 40 not in section.text
    )
    assert "Zoé" not in section.text
    # The age bound is the published setting, against the reader's own day.
    not_before = harness.repo.list_injectable.await_args.kwargs["not_before"]
    assert isinstance(not_before, date)


async def test_no_debrief_is_empty(harness: SimpleNamespace) -> None:
    harness.repo.list_injectable.return_value = []
    section = await read_relation_debriefs(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "empty" and section.total == 0


async def test_the_three_gates_each_disable(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "relation_debrief_enabled", False, raising=False)
    assert (
        await read_relation_debriefs(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    monkeypatch.setattr(module.settings, "relation_debrief_enabled", True, raising=False)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=False))
    assert (
        await read_relation_debriefs(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    harness.db.get.return_value = SimpleNamespace(relation_debrief_enabled=False, timezone="UTC")
    assert (
        await read_relation_debriefs(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"


async def test_a_failing_read_is_unavailable(harness: SimpleNamespace) -> None:
    harness.repo.list_injectable.side_effect = RuntimeError("db gone")
    assert (
        await read_relation_debriefs(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "unavailable"
