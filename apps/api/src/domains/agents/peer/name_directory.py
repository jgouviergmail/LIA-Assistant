"""Which CONNECTED user a name designates — said against everyone LIA knows.

Two directories, one rule (``shared/name_resolution``). The accepted
connections are the only people whose shared data a peer tool may read; the
relationship list (``RelationsService.directory``) knows everyone else the
person deals with, connected or not. « Mei » designating one connection AND
someone who is not connected is a question to ask: reading the connection's
calendar would answer about a person the user may not have meant.

Four rules:

- the EXACT full name of a connection is read at once — the relationship list
  is not consulted, so the common case costs what it always cost;
- the relationship list only SUBTRACTS: it turns a partial match into a
  question, or names the people a name designates who are not connected; it
  never selects a connection. A merge declared on the Relations page is a
  display decision and must never pick an account (``relations/identity.py``);
- a person the list knows is a DIFFERENT candidate only when one of their
  spellings carries a word the matched connection's name does not: a source
  naming the connection by the first name alone is the same name, not a second
  person to ask about;
- a relationship list that cannot be read degrades to the connections alone,
  logged by type: the disambiguation is lost for this call, the answer is not.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import structlog

from src.domains.relations.identity import RelationIdentity
from src.domains.relations.service import RelationsService
from src.domains.shared.name_mentions import TOKEN_RE
from src.domains.shared.name_resolution import (
    MAX_NAMED_CANDIDATES,
    ResolutionStatus,
    resolve_name,
)
from src.domains.shared.text_normalization import fold_name

logger = structlog.get_logger(__name__)

type KnownPeople = Callable[[UUID], Awaitable[Sequence[RelationIdentity]]]


class PeerNameOutcome(StrEnum):
    """What a name designates for a peer tool."""

    READ = "read"
    AMBIGUOUS = "ambiguous"
    NOT_A_CONNECTION = "not_a_connection"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PeerNameMatch:
    """The decision, and who to name when it is not a read.

    Attributes:
        outcome: Read, ask, not connected, or nobody.
        peer_id: The connection to read — set only on ``READ``.
        candidates: Display names to ask about or to name, bounded; the
            connections first.
    """

    outcome: PeerNameOutcome
    peer_id: UUID | None = None
    candidates: tuple[str, ...] = ()


async def _relationship_list(user_id: UUID) -> Sequence[RelationIdentity]:
    """The relationship list, as the Relations page builds it."""
    return await RelationsService(user_id).directory()


async def _known_people(user_id: UUID, known_people: KnownPeople) -> Sequence[RelationIdentity]:
    """The relationship list, or nothing when it cannot be read."""
    try:
        return await known_people(user_id)
    except Exception as exc:
        # The list only refines the decision: losing it must never cost the
        # answer the connections can still give.
        logger.warning("peer_name_directory_unavailable", error_type=type(exc).__name__)
        return []


def _words(name: str) -> frozenset[str]:
    return frozenset(TOKEN_RE.findall(fold_name(name)))


def _other_people(
    spoken: str,
    identities: Sequence[RelationIdentity],
    connection_names: Sequence[str],
) -> list[str]:
    """Who else the name designates: not connected, and told apart by a word."""
    matched = resolve_name(
        spoken, [(spelling, identity) for identity in identities for spelling in identity.spellings]
    )
    connection_words = [_words(name) for name in connection_names]
    return [
        identity.display_name
        for identity in matched.matches
        if not identity.is_peer
        and not any(
            all(_words(spelling) <= words for spelling in identity.spellings)
            for words in connection_words
        )
    ]


async def resolve_connected_peer(
    user_id: UUID,
    spoken: str,
    connections: Sequence[tuple[str, UUID]],
    *,
    known_people: KnownPeople = _relationship_list,
) -> PeerNameMatch:
    """Decide which connected user a spoken name designates.

    Args:
        user_id: The asking user.
        spoken: The name as the person said it.
        connections: ``(display name, peer id)`` of the accepted connections.
        known_people: Reader of the relationship list — injected for tests.

    Returns:
        The decision.
    """
    names = {peer_id: name for name, peer_id in connections}
    resolution = resolve_name(spoken, connections)
    if resolution.exact:
        if resolution.status is ResolutionStatus.RESOLVED:
            return PeerNameMatch(PeerNameOutcome.READ, peer_id=resolution.match)
        return PeerNameMatch(
            PeerNameOutcome.AMBIGUOUS,
            candidates=tuple(names[peer] for peer in resolution.matches)[:MAX_NAMED_CANDIDATES],
        )
    peers = resolution.matches
    connected = [names[peer] for peer in peers]
    others = _other_people(spoken, await _known_people(user_id, known_people), connected)
    if len(peers) == 1 and not others:
        return PeerNameMatch(PeerNameOutcome.READ, peer_id=peers[0])
    if peers:
        return PeerNameMatch(
            PeerNameOutcome.AMBIGUOUS,
            candidates=tuple([*connected, *others][:MAX_NAMED_CANDIDATES]),
        )
    if others:
        return PeerNameMatch(
            PeerNameOutcome.NOT_A_CONNECTION, candidates=tuple(others[:MAX_NAMED_CANDIDATES])
        )
    return PeerNameMatch(PeerNameOutcome.UNKNOWN)


__all__ = ["PeerNameMatch", "PeerNameOutcome", "resolve_connected_peer"]
