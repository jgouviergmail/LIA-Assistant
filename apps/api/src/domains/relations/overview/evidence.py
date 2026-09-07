"""Assembling everything LIA holds about ONE person, under the reader's scope.

Three independent reads, each with its own session and its own failure boundary,
so the answer is honestly PARTIAL rather than all-or-nothing:

- the database-local half (``RelationsService.build_detail``);
- the provider-backed half (``RelationContextService.build``), **only for the
  sections the scope asks for**;
- the semantic memory recall.

Only the first is load-bearing: without the relationship itself there is nothing
to say, so its failure raises :class:`OverviewEvidenceUnavailable` while the
other two degrade into a named gap.

**The provider half is paid for only when it is wanted.** One 360° read costs up
to eleven external API calls (three mail searches per address, three addresses,
plus the contact card and the calendar). Reading them and then dropping the
blocks the scope excluded — which is what this assembly used to do — is ADR-184's
trap pointing at cost: a selection published, then not honoured.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from src.domains.relations.overview.blocks import (
    PROVIDER_SECTIONS,
    local_blocks,
    peer_connection,
    provider_blocks,
    unavailable_sections,
)
from src.domains.relations.overview.fallback import fill_by_name
from src.domains.relations.overview.recall import fetch_person_memories, recalled_memories
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.providers.schemas import RelationContext
from src.domains.relations.providers.service import RelationContextService
from src.domains.relations.schemas import RelationDetail
from src.domains.relations.service import RelationsService

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

__all__ = [
    "OverviewEvidence",
    "OverviewEvidenceUnavailable",
    "build_overview_evidence",
    "overview_payload",
]


class OverviewEvidenceUnavailable(Exception):
    """The relationship itself could not be read — nothing can be said about it."""


@dataclass(frozen=True, slots=True)
class OverviewEvidence:
    """Everything one 360° point read, and what it could not.

    Attributes:
        detail: The relationship as the database-local half reports it.
        blocks: The scoped payload blocks, keyed as the payload carries them.
        unavailable: Sections the reader asked for that could not be read.
    """

    detail: RelationDetail
    blocks: dict[str, Any]
    unavailable: list[str]


async def _nothing() -> None:
    """Placeholder for a read the scope excluded — keeps the gather shape."""
    return None


async def build_overview_evidence(
    user_id: UUID, person_name: str, scope: RelationOverviewScope
) -> OverviewEvidence:
    """Read everything the scope allows about one person.

    Args:
        user_id: Owner of the relationship.
        person_name: The person, as the user says it.
        scope: What the reader declared a point on this person may read.

    Returns:
        The evidence: the relationship, its scoped blocks, and the gaps.

    Raises:
        OverviewEvidenceUnavailable: When the relationship itself is unreadable.
    """
    wanted_provider = frozenset(
        section.value for section in PROVIDER_SECTIONS if scope.includes(section)
    )
    wants_memories = scope.includes(OverviewSection.MEMORIES)

    detail, context, memories = await asyncio.gather(
        RelationsService(user_id).build_detail(person_name),
        (
            RelationContextService(user_id).build(person_name, sections=wanted_provider)
            if wanted_provider
            else _nothing()
        ),
        fetch_person_memories(user_id, person_name) if wants_memories else _nothing(),
        return_exceptions=True,
    )
    if isinstance(detail, BaseException):
        logger.warning("overview_evidence_detail_failed", error_type=type(detail).__name__)
        raise OverviewEvidenceUnavailable(person_name) from detail

    blocks = local_blocks(detail, scope)
    unavailable = _apply_memories(blocks, memories, wants_memories=wants_memories)
    if wanted_provider:
        gaps = await _apply_provider(blocks, context, user_id, person_name, scope, wanted_provider)
        # Memories close the list, whatever else went missing: the provider
        # sections are read in payload order and a gap reads best in that same
        # order.
        unavailable = gaps + unavailable
    return OverviewEvidence(detail=detail, blocks=blocks, unavailable=unavailable)


def _apply_memories(blocks: dict[str, Any], memories: object, *, wants_memories: bool) -> list[str]:
    """Add the recalled memories, or name the recall as a gap.

    Args:
        blocks: Payload being assembled, mutated in place.
        memories: What the recall returned — a list, None, or an exception.
        wants_memories: Whether the reader asked for them at all.

    Returns:
        ``["memories"]`` when the recall could not run, otherwise empty. An
        empty LIST of memories is a result and never a gap.
    """
    if not wants_memories:
        return []
    recalled = recalled_memories(memories)
    if recalled is None:
        return [OverviewSection.MEMORIES.value]
    blocks["memories"] = recalled
    return []


async def _apply_provider(
    blocks: dict[str, Any],
    context: RelationContext | BaseException | None,
    user_id: UUID,
    person_name: str,
    scope: RelationOverviewScope,
    wanted_provider: frozenset[str],
) -> list[str]:
    """Add the provider-backed blocks, and name what could not be read.

    Args:
        blocks: Payload being assembled, mutated in place.
        context: The provider half, or the exception that replaced it.
        user_id: Owner.
        person_name: The person, for the by-name last resort.
        scope: What the reader ticked.
        wanted_provider: The provider sections the scope asked for.

    Returns:
        The sections that stayed unreadable, in payload order.
    """
    if not isinstance(context, RelationContext):
        # An exception, or the no-read placeholder the caller only substitutes
        # when nothing was wanted — which cannot reach here. Either way the
        # conservative answer is a stated gap, never a claim about sections
        # nothing looked at.
        if context is not None:
            logger.warning("overview_evidence_context_failed", error_type=type(context).__name__)
        # Payload order, not alphabetical — the two agree today and would drift
        # on the next section added.
        return [section.value for section in PROVIDER_SECTIONS if section.value in wanted_provider]
    blocks |= provider_blocks(context, scope)
    return await fill_by_name(
        blocks,
        unavailable_sections(context, scope),
        user_id,
        person_name,
        scope,
        context,
    )


def overview_payload(evidence: OverviewEvidence) -> dict[str, Any]:
    """The assembled answer: who this is, then what was read about them.

    Identity and relationship context first — the name, how confidently it was
    matched, whether this person is a connected LIA user and what the two sides
    share — then the scoped blocks, then what could NOT be read.

    Args:
        evidence: The result of :func:`build_overview_evidence`.

    Returns:
        The payload, in the order a reader (human or model) needs it.
    """
    connection = peer_connection(evidence.detail)
    return {
        "person": evidence.detail.display_name,
        "identity_confidence": evidence.detail.identity_confidence.value,
        "is_peer": evidence.detail.is_peer,
        **({"peer_connection": connection} if connection else {}),
        **evidence.blocks,
        "unavailable": evidence.unavailable,
    }
