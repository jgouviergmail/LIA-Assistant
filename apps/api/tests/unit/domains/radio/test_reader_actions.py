"""What LIA did today, read from the effect register and named as the register names it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.personal import JournalPart
from src.domains.radio.readers.actions import ActionLine, action_drafts, action_line

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 8, 12, tzinfo=UTC)
PLUS_TWO = timezone(timedelta(hours=2))


def test_an_action_names_the_capability_and_what_its_label_names() -> None:
    lines = [
        ActionLine(
            id=UUID(int=1),
            tool_name="send_email_to_me_tool",
            at=NOW,
            values={"target": "Quarterly report"},
        ),
        ActionLine(
            id=UUID(int=2), tool_name="run_python_tool", at=NOW + timedelta(minutes=5), values={}
        ),
        ActionLine(
            id=UUID(int=3),
            tool_name="mcp_era_cancel_subscription",
            at=NOW + timedelta(minutes=9),
            values={"tool": "era: cancel subscription", "count": None},
        ),
    ]
    drafts = action_drafts(lines, tz=PLUS_TWO)
    assert [d.text for d in drafts] == [
        'LIA did "send email to me" (target: Quarterly report) on Saturday 2026-09-26, 10:12',
        'LIA did "run python" on Saturday 2026-09-26, 10:17',
        'LIA did "era: cancel subscription" on Saturday 2026-09-26, 10:21',
    ]
    assert {d.kind for d in drafts} == {FactKind.ACTION}
    assert {d.sensitivity for d in drafts} == {Sensitivity.PERSONAL}
    assert {d.part for d in drafts} == {JournalPart.DONE}
    assert [d.key for d in drafts] == [f"done:action:{UUID(int=n)}" for n in (1, 2, 3)]


@dataclass
class EffectRow:
    """A register row as ``readable_label`` reads it (the label, encrypted or not)."""

    id: UUID
    tool_name: str
    claimed_at: datetime
    label: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def test_a_row_whose_label_cannot_be_read_still_names_the_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.radio.readers import actions as module

    monkeypatch.setattr(
        module, "readable_label", lambda row: ("effects.labels.generic", {"tool": row.tool_name})
    )
    line = action_line(EffectRow(id=UUID(int=7), tool_name="delete_event_tool", claimed_at=NOW))
    assert line == ActionLine(
        id=UUID(int=7), tool_name="delete_event_tool", at=NOW, values={"tool": "delete_event_tool"}
    )
    [draft] = action_drafts([line], tz=UTC)
    assert draft.text == 'LIA did "delete event" on Saturday 2026-09-26, 08:12'
