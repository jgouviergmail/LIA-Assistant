"""The connected user a name designates — told apart from everyone else LIA knows.

What must hold:
- the exact full name of a connection is read at once, the relationship list
  never consulted;
- a first name designating one connection is read, unless the relationship
  list knows a DIFFERENT person it designates too (a word the connection's
  name does not carry tells them apart) — then the person is asked;
- a name designating only people who are not connected is said as such;
- the relationship list only subtracts: it never selects a connection, and
  when it cannot be read the connections alone decide.
"""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.domains.agents.peer.name_directory import PeerNameOutcome, resolve_connected_peer
from src.domains.relations.identity import RelationIdentity
from src.domains.shared.name_resolution import MAX_NAMED_CANDIDATES

pytestmark = pytest.mark.unit

USER = uuid4()
MEI_DURAND = uuid4()
PAUL_MARTIN = uuid4()
CONNECTIONS: list[tuple[str, UUID]] = [
    ("Mei Durand", MEI_DURAND),
    ("Paul Martin", PAUL_MARTIN),
]


def _known(*people: tuple[str, bool], spellings: Sequence[str] = ()) -> AsyncMock:
    """A relationship list: ``(display name, is connected)`` per person."""
    identities = [
        RelationIdentity(
            key=name.casefold(),
            display_name=name,
            spellings=(name, *spellings) if index == 0 else (name,),
            is_peer=is_peer,
        )
        for index, (name, is_peer) in enumerate(people)
    ]
    return AsyncMock(return_value=identities)


class TestConnectionsDecide:
    async def test_an_exact_full_name_reads_without_asking_the_relationship_list(
        self,
    ) -> None:
        known = _known(("Mei Lin", False))

        match = await resolve_connected_peer(USER, "mei durand", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.READ
        assert match.peer_id == MEI_DURAND
        known.assert_not_awaited()

    async def test_a_unique_first_name_reads_when_nobody_else_is_known(self) -> None:
        match = await resolve_connected_peer(
            USER, "Paul", CONNECTIONS, known_people=_known(("Paul Martin", True))
        )

        assert match.outcome is PeerNameOutcome.READ
        assert match.peer_id == PAUL_MARTIN

    async def test_two_connections_sharing_a_first_name_are_asked_about(self) -> None:
        connections = [("Mei Durand", MEI_DURAND), ("Mei Lin", uuid4())]

        match = await resolve_connected_peer(USER, "Mei", connections, known_people=_known())

        assert match.outcome is PeerNameOutcome.AMBIGUOUS
        assert match.candidates == ("Mei Durand", "Mei Lin")
        assert match.peer_id is None

    async def test_exact_homonyms_are_asked_about_never_read(self) -> None:
        connections = [("Mei Durand", MEI_DURAND), ("Mei Durand", uuid4())]

        match = await resolve_connected_peer(USER, "Mei Durand", connections, known_people=_known())

        assert match.outcome is PeerNameOutcome.AMBIGUOUS
        assert match.peer_id is None


class TestTheRelationshipListSubtracts:
    async def test_a_different_person_with_the_same_first_name_makes_a_question(
        self,
    ) -> None:
        known = _known(("Mei Lin", False), ("Mei Durand", True))

        match = await resolve_connected_peer(USER, "Mei", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.AMBIGUOUS
        # The connection first, then who else the name designates.
        assert match.candidates == ("Mei Durand", "Mei Lin")

    async def test_the_connection_known_under_the_first_name_alone_is_no_other_person(
        self,
    ) -> None:
        # A source naming the same person by the first name only carries no
        # word telling them apart: it is not a second candidate.
        known = _known(("Mei", False), ("Mei Durand", True))

        match = await resolve_connected_peer(USER, "Mei", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.READ
        assert match.peer_id == MEI_DURAND

    async def test_a_name_designating_only_people_not_connected_is_said_as_such(
        self,
    ) -> None:
        known = _known(("Ana Costa", False))

        match = await resolve_connected_peer(USER, "Ana", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.NOT_A_CONNECTION
        assert match.candidates == ("Ana Costa",)
        assert match.peer_id is None

    async def test_a_known_connection_is_never_counted_as_someone_else(self) -> None:
        known = _known(("Paul Martin", True))

        match = await resolve_connected_peer(USER, "Martin", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.READ
        assert match.peer_id == PAUL_MARTIN

    async def test_a_merge_in_the_relationship_list_never_selects_a_connection(
        self,
    ) -> None:
        # « Papa » merged into a connected person's card names them on the
        # page; it is a display decision, not an account selection.
        known = _known(("Paul Martin", True), spellings=("Papa",))

        match = await resolve_connected_peer(USER, "Papa", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.UNKNOWN
        assert match.peer_id is None

    async def test_nobody_anywhere_is_unknown(self) -> None:
        match = await resolve_connected_peer(
            USER, "Zoé", CONNECTIONS, known_people=_known(("Ana Costa", False))
        )

        assert match.outcome is PeerNameOutcome.UNKNOWN

    async def test_candidates_are_bounded(self) -> None:
        others = [(f"Mei Other{index}", False) for index in range(MAX_NAMED_CANDIDATES + 3)]

        match = await resolve_connected_peer(USER, "Mei", CONNECTIONS, known_people=_known(*others))

        assert match.outcome is PeerNameOutcome.AMBIGUOUS
        assert len(match.candidates) == MAX_NAMED_CANDIDATES
        assert match.candidates[0] == "Mei Durand"


class TestDegradation:
    async def test_an_unreadable_relationship_list_leaves_the_connections_to_decide(
        self,
    ) -> None:
        known = AsyncMock(side_effect=RuntimeError("database unavailable"))

        match = await resolve_connected_peer(USER, "Paul", CONNECTIONS, known_people=known)

        assert match.outcome is PeerNameOutcome.READ
        assert match.peer_id == PAUL_MARTIN
