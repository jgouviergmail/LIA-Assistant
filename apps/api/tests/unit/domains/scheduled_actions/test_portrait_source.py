"""The routines as the portrait reads them (2026-10-12): what the person automated.

Every ACTIVE and enabled routine, whole, with its schedule in the person's
language (a time routine) or its condition (a condition routine) and its
instruction; a failed read is ``unavailable``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.journals.portrait_catalogue import eligible_source_items
from src.domains.scheduled_actions import portrait_source as module
from src.domains.scheduled_actions.portrait_source import read_routines

pytestmark = pytest.mark.unit

SPEC = {
    "freq": "weekly",
    "byweekday": [5],
    "times": {"mode": "at", "at": [{"hour": 16, "minute": 30}]},
    "anchor_date": "2026-09-04",
}


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _routine(
    title: str,
    *,
    prompt: str,
    trigger_kind: str = "time",
    recurrence: dict[str, Any] | None = SPEC,
    condition: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        action_prompt=prompt,
        trigger_kind=trigger_kind,
        recurrence=recurrence,
        condition_config=condition,
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    rows = [
        _routine("Résumé du vendredi", prompt="Résume les tickets\nouverts cette semaine."),
        _routine(
            "Veille courrier",
            prompt="Préviens-moi quand le devis arrive.",
            trigger_kind="condition",
            recurrence=None,
            condition={"type": "mail_match"},
        ),
    ]
    reader = AsyncMock(return_value=rows)
    monkeypatch.setattr(module, "get_db_context", _ctx(AsyncMock()))
    monkeypatch.setattr(module, "_rows", reader)
    monkeypatch.setattr(module, "describe", lambda spec, language: "chaque vendredi à 16:30")
    return SimpleNamespace(rows=reader)


async def test_every_routine_is_rendered_whole_with_its_clock(harness: SimpleNamespace) -> None:
    section = await read_routines(user_id=uuid.uuid4(), language="fr")
    assert section.key == "routines" and section.status == "used"
    assert (section.used, section.total) == (2, 2)
    assert section.text.startswith("## ROUTINES")
    assert (
        "- Résumé du vendredi — chaque vendredi à 16:30: Résume les tickets ouverts cette semaine."
        in section.text
    )
    assert (
        "- Veille courrier — when mail_match: Préviens-moi quand le devis arrive." in section.text
    )
    assert len(eligible_source_items("routines", section.text)) == 2


async def test_no_routine_is_empty(harness: SimpleNamespace) -> None:
    harness.rows.return_value = []
    section = await read_routines(user_id=uuid.uuid4(), language="fr")
    assert section.status == "empty" and section.total == 0


async def test_a_failed_read_is_named_never_read_as_empty(harness: SimpleNamespace) -> None:
    harness.rows.side_effect = RuntimeError("db gone")
    assert (await read_routines(user_id=uuid.uuid4(), language="fr")).status == "unavailable"
