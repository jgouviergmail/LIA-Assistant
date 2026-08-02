"""Local facts about a CONNECTED user named in the turn.

Naming a peer used to correct only the ROUTING (``apply_peer_domain_correction``
appends the ``peer`` domain) while injecting nothing — so the assistant
announced a lookup for facts the database already held, one query away.

What is injected, and why only this:

- **open commitments, calls, relayed messages** — the three sources the CRM
  owns locally. No connector is touched, so this costs database reads only and
  never spends the provider budget the 360° is bounded by;
- **not memories**: they already arrive through semantic relevance
  (``memory_injection``), and injecting them again would double their weight in
  the prompt for no new information;
- **not the contact card, mail or meetings**: those are provider-backed, and a
  turn that merely NAMES someone must not trigger external calls.

The user's own 360° scope decides which of the three blocks may be read: the
relationship card is where they said what a "point on this person" is allowed
to look at, and a section unticked there is not injected here either.

Sits in ``middleware/`` next to ``memory_injection``: same shape (build a
prompt block from a versioned template), same failure posture (any error
degrades to no context, never raises into the turn).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.agents.prompts import load_prompt
from src.domains.agents.services.analysis.peer_directory import detect_mentioned_peers
from src.domains.peers.repository import PeersRepository
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.service import RelationsService
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from src.domains.relations.schemas import RelationDetail

logger = structlog.get_logger(__name__)

#: The three sources this injection may read — the CRM's own half. Memories are
#: excluded by construction, not by configuration: they arrive semantically.
_LOCAL_SECTIONS = (
    OverviewSection.OPEN_LOOPS,
    OverviewSection.CALLS,
    OverviewSection.PEER_MESSAGES,
)


def _section_formats() -> dict[str, tuple[str, str]]:
    """``section -> (header, line_template)`` from the versioned file.

    Both the labels and the line wording live in the prompt file: prose in a
    ``.py`` is exactly what the versioned-prompt rule forbids, fallbacks and
    LLM scaffolding included.
    """
    formats: dict[str, tuple[str, str]] = {}
    for line in load_prompt("peer_context_section_headers").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.count("|") < 2:
            continue
        section, header, template = stripped.split("|", 2)
        formats[section.strip()] = (header.strip(), template.strip())
    return formats


async def _peer_directory(user_id: UUID) -> list[str]:
    """Display names of the user's accepted connections (own session)."""
    async with get_db_context() as db:
        profiles = await PeersRepository(db).list_accepted_peer_profiles(user_id)
    return [profile.peer_display_name for profile in profiles]


async def _overview_scope(user_id: UUID) -> RelationOverviewScope:
    """The scope the user selected for a 360° point on a relationship."""
    return await RelationsService(user_id).get_overview_scope()


async def _relation_detail(user_id: UUID, name: str) -> RelationDetail:
    """The CRM's full view of one relationship (database-local)."""
    return await RelationsService(user_id).build_detail(name)


def _open_loop_lines(detail: RelationDetail, limit: int, template: str) -> list[str]:
    return [
        template.format(subject=loop.subject, direction=loop.direction, days_open=loop.days_open)
        for loop in (detail.open_loops or [])[:limit]
    ]


def _call_lines(detail: RelationDetail, limit: int, template: str) -> list[str]:
    lines = []
    for call in (detail.recent_calls or [])[:limit]:
        # The separator travels WITH the value: a template cannot express
        # "only when present", and an empty summary must leave no dangling dash.
        summary = f" — {call.summary}" if call.summary else ""
        lines.append(
            template.format(objective=call.objective, outcome=call.outcome, summary=summary)
        )
    return lines


def _message_lines(detail: RelationDetail, limit: int, template: str) -> list[str]:
    return [
        template.format(direction=message.direction, content=message.content)
        for message in (detail.peer_messages or [])[:limit]
    ]


#: One line-builder per local section, keyed by its OverviewSection value.
_SECTION_BUILDERS = {
    OverviewSection.OPEN_LOOPS.value: _open_loop_lines,
    OverviewSection.CALLS.value: _call_lines,
    OverviewSection.PEER_MESSAGES.value: _message_lines,
}

# Completeness at IMPORT time, the way every enum-keyed registry here is
# guarded (ADR-085). Adding a section to `_LOCAL_SECTIONS` without its builder
# would raise a KeyError that the enrichment's own `except` swallows — the
# feature would simply stop injecting, quietly, for whoever ticked that box.
_MISSING_BUILDERS = {section.value for section in _LOCAL_SECTIONS} - set(_SECTION_BUILDERS)
assert not _MISSING_BUILDERS, f"local sections without a line builder: {_MISSING_BUILDERS}"


def _render(
    detail: RelationDetail,
    scope: RelationOverviewScope,
    formats: dict[str, tuple[str, str]],
) -> list[str]:
    """The scoped blocks, one string each; empty list when nothing may be shown.

    Returns the blocks rather than the joined text so the caller can COUNT them.
    Counting a marker in the rendered string instead made the metric depend on
    the wording of a prompt file — and on the content, since a relayed message
    containing that marker inflated the count.
    """
    blocks: list[str] = []
    for section in _LOCAL_SECTIONS:
        if not scope.includes(section) or section.value not in formats:
            continue
        header, template = formats[section.value]
        lines = _SECTION_BUILDERS[section.value](detail, scope.max_items, template)
        if not lines:
            # An empty block would read as "there is nothing", which is a claim
            # about data the model was never shown.
            continue
        blocks.append("\n".join([header, *lines]))
    return blocks


def _first_mentioned(texts: Sequence[str | None], directory: Iterable[str]) -> str | None:
    """The first connected user named in the turn, or None.

    Delegates to the SAME whole-word, accent-folded matcher the routing
    correction uses: two notions of "was this person named" would eventually
    disagree, and a false positive here leaks one person's private data into a
    turn that is not about them.
    """
    mentioned = detect_mentioned_peers(texts, list(directory))
    return mentioned[0] if mentioned else None


async def build_peer_context(user_id: UUID, texts: Sequence[str | None]) -> str:
    """Prompt block of local facts about a connected user named in the turn.

    Args:
        user_id: The CRM owner.
        texts: Every text that may carry the name — the user's message, the
            English pivot, and the values of resolved references ("ma femme"
            resolves to a name that is nowhere in what the user typed).

    Returns:
        The formatted block, or ``""`` when the feature is off, nobody was
        named, the scope allows nothing, there is nothing to say, or any read
        failed. Never raises: an injection is an enrichment, not a dependency.
    """
    if not (
        getattr(settings, "peer_context_injection_enabled", False)
        and getattr(settings, "peers_enabled", False)
    ):
        return ""

    try:
        directory = await _peer_directory(user_id)
        if not directory:
            return ""

        peer_name = _first_mentioned(texts, directory)
        if not peer_name:
            return ""

        scope = await _overview_scope(user_id)
        if not any(scope.includes(section) for section in _LOCAL_SECTIONS):
            return ""

        # ONE peer per turn: reading every named connection would multiply the
        # database cost of a single message by the size of the directory.
        detail = await _relation_detail(user_id, peer_name)
        blocks = _render(detail, scope, _section_formats())
        if not blocks:
            return ""

        # No PII at INFO: the COUNT of blocks, never the name or the content.
        logger.info("peer_context_injected", block_count=len(blocks))
        return str(
            load_prompt("peer_context_template").format(
                peer_name=detail.display_name or peer_name,
                sections="\n\n".join(blocks),
            )
        )
    except Exception as exc:  # noqa: BLE001 - enrichment, never fatal
        logger.warning(
            "peer_context_injection_failed",
            error_type=type(exc).__name__,
        )
        return ""


__all__ = ["build_peer_context"]
