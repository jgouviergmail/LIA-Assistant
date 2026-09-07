"""The written debrief, framed for a chat turn that names the person.

Two things this module refuses to do, both learned from the block next to it
(``agents/middleware/peer_context_injection``):

- **it never speaks with the peer block's authority.** That block states its
  facts are EXACT and tells the model to answer without looking, which is true
  of a live database read made this very turn. A debrief is a DATED summary,
  and the same sentence applied to it is a machine for producing false claims:
  "when did I last call her?" answered from a text written four days ago, with
  the confidence of something just verified. Its template says the opposite,
  by name, and points every movable fact at the tools.
- **it never guesses who.** The peer directory is a handful of accepted
  connections; the debrief directory is every relationship the reader has
  opened, which includes company names and phone numbers stored as
  counterparties. So a turn matching MORE THAN ONE debriefed person injects
  nothing at all — a false positive here does not degrade an answer, it hands
  one person's file to a question about somebody else.

Lives in ``relations`` rather than in ``agents/middleware``: the agents layer
already imports this domain, and the reverse edge would close a runtime cycle.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.relations.debrief.prompts import load_debrief_prompt
from src.domains.relations.debrief.repository import RelationDebriefRepository
from src.domains.relations.debrief.schemas import DebriefBody
from src.domains.relations.debrief.service import read_of
from src.domains.shared.name_mentions import detect_mentioned_names
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_relation_debrief import (
    relation_debrief_injections_total,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from src.domains.relations.debrief.models import RelationDebrief

logger = structlog.get_logger(__name__)


def _section_formats() -> list[tuple[str, str, str]]:
    """``(field, header, line_template)`` in injection order, from the file.

    Both the labels and the line wording live in the versioned prompt file:
    prose in a ``.py`` is exactly what the versioned-prompt rule forbids,
    scaffolding included.
    """
    formats: list[tuple[str, str, str]] = []
    for line in load_debrief_prompt("relation_debrief_context_sections").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.count("|") < 2:
            continue
        field, header, template = stripped.split("|", 2)
        formats.append((field.strip(), header.strip(), template.strip()))
    return formats


def _render_blocks(body: DebriefBody) -> list[str]:
    """One string per non-empty field, in the file's order.

    Blocks rather than the joined text so the caller can COUNT them: counting a
    marker in the rendered string instead would make the metric depend on the
    wording of a prompt file, and on the content — a debrief mentioning that
    marker would inflate the count.
    """
    blocks: list[str] = []
    for field, header, template in _section_formats():
        value = getattr(body, field, None)
        if not value:
            # An empty heading reads as "there is nothing here", which is a
            # claim about something the model was never asked to produce.
            continue
        lines = (
            [template.format(value=item) for item in value]
            if isinstance(value, list)
            else [template.format(value=value)]
        )
        blocks.append("\n".join([header, *lines]))
    return blocks


def _oldest_injectable(today: date) -> date:
    """The oldest local date still worth putting in front of the model."""
    return today - timedelta(days=settings.relation_debrief_injection_max_age_days)


async def _directory(user_id: UUID) -> tuple[list[RelationDebrief], date | None]:
    """Debriefs fresh enough to inject, and the reader's own day.

    The day travels back with the rows because it is also what the age in the
    log is measured against: reading a second clock — ``date.today()``, the
    server's — would report an age that is not the reader's, and is forbidden
    outright by the datetime doctrine.

    Args:
        user_id: The reader.

    Returns:
        The injectable rows and the reader's local date, or ``([], None)`` when
        the account wants no debrief at all.
    """
    async with get_db_context() as db:
        user = await db.get(User, user_id)
        if user is None or not getattr(user, "relation_debrief_enabled", True):
            return [], None
        today = datetime.now(resolve_user_timezone(user)).date()
        rows = await RelationDebriefRepository(db).list_injectable(
            user_id, not_before=_oldest_injectable(today)
        )
        return rows, today


def _sole_match(texts: Sequence[str | None], rows: list[RelationDebrief]) -> RelationDebrief | None:
    """The ONE debriefed person named in the turn, or nothing at all.

    Delegates to the same whole-word, accent-folded matcher the peer routing
    uses: two notions of "was this person named" would eventually disagree.
    Ambiguity resolves to silence — see the module docstring.

    Args:
        texts: Every text that may carry the name.
        rows: The debriefed relationships to match against.

    Returns:
        The single matching row, or None.
    """
    mentioned = detect_mentioned_names(texts, [row.display_name for row in rows])
    if len(mentioned) != 1:
        return None
    return next((row for row in rows if row.display_name == mentioned[0]), None)


async def build_debrief_context(user_id: UUID, texts: Sequence[str | None]) -> str:
    """Prompt block carrying the written debrief of a person named in the turn.

    Args:
        user_id: The reader.
        texts: Every text that may carry the name — the user's message, the
            English pivot, and the values of resolved references ("ma femme"
            resolves to a name that is nowhere in what the user typed).

    Returns:
        The formatted block, or ``""`` when the feature is off, nobody was
        named, two people were, there is no debrief fresh enough, or any read
        failed. Never raises: an injection is an enrichment, not a dependency.
    """
    if not (settings.relation_debrief_enabled and settings.relation_debrief_injection_enabled):
        return ""
    try:
        rows, today = await _directory(user_id)
        if not rows or today is None:
            return ""
        row = _sole_match(texts, rows)
        if row is None:
            return ""
        read = read_of(row)
        if read.body is None:
            return ""
        blocks = _render_blocks(read.body)
        if not blocks:
            return ""
        # The AGE, not only the date. The whole safety property of this block is
        # that the model treats it as DATED; handing it an ISO date and trusting
        # it to do the arithmetic against "today" is a weaker guarantee than
        # saying the number — and it is the READER's day that decides, which is
        # why the day travels back from the directory read.
        age_days = (today - row.generated_for).days
        relation_debrief_injections_total.inc()
        # No PII at INFO: the COUNT of blocks and the age, never the name nor
        # a line of what the debrief says.
        logger.info("relation_debrief_injected", block_count=len(blocks), age_days=age_days)
        return str(
            load_debrief_prompt("relation_debrief_context_template").format(
                person_name=row.display_name,
                generated_on=row.generated_for.isoformat(),
                age_days=age_days,
                sections="\n\n".join(blocks),
            )
        )
    except Exception as exc:  # noqa: BLE001 - enrichment, never fatal
        logger.warning("relation_debrief_injection_failed", error_type=type(exc).__name__)
        return ""


__all__ = ["build_debrief_context"]
