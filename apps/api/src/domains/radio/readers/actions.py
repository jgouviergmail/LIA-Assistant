"""What LIA did for the listener today, as drafts for the journal's « done » part.

The effect register (ADR-263) holds one row per ACTION LIA carried out — a mail sent,
a reminder created, a ticket updated — with the label every other surface reads
(``effects.labels.readable_label``, ONE reader): the radio reads the SUCCEEDED rows
of the day, whoever set them in motion, and names each by the capability that acted
(``readable_tool_name``, the same rendering as the confirmation card) and what its
label names. Nothing is invented: a row whose label says nothing names the tool alone.

The read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, tzinfo
from typing import Any
from uuid import UUID

from src.domains.agents.effects.confirmation import readable_tool_name
from src.domains.agents.effects.labels import readable_label
from src.domains.agents.effects.models import EffectStatus
from src.domains.agents.effects.origin import RegisterOrigin
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import MAX_PER_SOURCE, JournalPart, PersonalDraft, PersonalSource
from src.infrastructure.database.session import get_db_context


@dataclass(frozen=True, slots=True)
class ActionLine:
    """What the radio reads of one action.

    Attributes:
        id: The register row.
        tool_name: The capability that acted (its registered name).
        at: When it was claimed (aware).
        values: What its label names (a target, a recipient, a count…).
    """

    id: UUID
    tool_name: str
    at: datetime
    values: Mapping[str, Any]


def action_line(row: Any) -> ActionLine:
    """A register row as the radio reads it."""
    _key, values = readable_label(row)
    return ActionLine(id=row.id, tool_name=row.tool_name, at=row.claimed_at, values=values)


def action_drafts(lines: Sequence[ActionLine], *, tz: tzinfo) -> list[PersonalDraft]:
    """The actions as drafts, in the order given.

    Args:
        lines: The actions of the day, oldest first.
        tz: The listener's timezone.

    Returns:
        One draft per action.
    """
    drafts: list[PersonalDraft] = []
    for line in lines:
        named = ", ".join(
            f"{name}: {value}"
            for name, value in line.values.items()
            if value not in (None, "") and name != "tool"
        )
        text = f'LIA did "{readable_tool_name(line.tool_name)}"'
        if named:
            text += f" ({named})"
        text += f" on {local_time_text(line.at.astimezone(tz))}"
        drafts.append(
            PersonalDraft(
                FactKind.ACTION,
                text,
                f"done:action:{line.id}",
                Sensitivity.PERSONAL,
                JournalPart.DONE,
            )
        )
    return drafts


async def read_actions(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The actions LIA carried out for the listener today, oldest first.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    since = datetime.combine(now.astimezone(tz).date(), time(), tzinfo=tz)
    async with get_db_context() as db:
        rows, _total = await EffectLedgerRepository(db).list_for_user(
            user_id,
            limit=MAX_PER_SOURCE[PersonalSource.ACTIONS],
            offset=0,
            status=EffectStatus.SUCCEEDED,
            since=since,
            until=None,
            origin=RegisterOrigin.ALL,
        )
        lines = [action_line(row) for row in rows]
    return action_drafts(list(reversed(lines)), tz=tz)


__all__ = ["ActionLine", "action_drafts", "action_line", "read_actions"]
