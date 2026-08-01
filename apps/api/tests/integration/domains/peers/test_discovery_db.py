"""Discovery search against real PostgreSQL — the scan and its guards (Bloc B).

The unit tests stub the row scan, so they can prove the branching but not that
the scan itself selects the right population. What only a database can show:

- the opt-in, active and self exclusions really are WHERE clauses;
- an address search reaches a row whose stored case differs from the typed
  one, which is exactly what registration produces (Pydantic ``EmailStr``
  lowercases the domain and keeps the local part as typed);
- accents are folded away for NAMES and never for ADDRESSES, on real UTF-8
  columns rather than on Python literals;
- two mailboxes differing only by case can coexist (the UNIQUE index is on
  the raw string), and the search answers with BOTH rather than picking one.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.service import PeersService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def _user(
    session: AsyncSession,
    *,
    email: str,
    full_name: str | None,
    discovery_enabled: bool = True,
    is_active: bool = True,
) -> User:
    """Persist one user with the discovery-relevant flags under test."""
    user = User(
        email=email,
        hashed_password="x",
        is_active=is_active,
        is_superuser=False,
        full_name=full_name,
        discovery_enabled=discovery_enabled,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def searcher(async_session: AsyncSession) -> User:
    """The caller — discoverable themselves, and never their own result."""
    return await _user(async_session, email="searcher@test.local", full_name="Search Er")


class TestSearchByEmail:
    """Bloc B: the address branch, on real rows."""

    async def test_finds_the_owner_whatever_the_stored_case(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        target = await _user(async_session, email="Jean.Dupont@gmail.com", full_name="Jean Dupont")
        service = PeersService(async_session)

        matches = await service.search_discoverable(searcher.id, "jean.dupont@gmail.com")

        assert [m.peer_id for m in matches] == [target.id]
        assert matches[0].display_name == "Jean Dupont"

    async def test_never_returns_the_searcher_themselves(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, searcher.email) == []

    async def test_an_opted_out_owner_is_not_found(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        await _user(
            async_session,
            email="hidden@test.local",
            full_name="Hidden One",
            discovery_enabled=False,
        )
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, "hidden@test.local") == []

    async def test_an_inactive_owner_is_not_found(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        await _user(
            async_session,
            email="gone@test.local",
            full_name="Gone Away",
            is_active=False,
        )
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, "gone@test.local") == []

    async def test_a_nameless_owner_stays_unfindable(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        """Same rule as the name branch: no display name, no result row."""
        await _user(async_session, email="nameless@test.local", full_name=None)
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, "nameless@test.local") == []

    async def test_accents_are_never_folded_away_in_an_address(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        await _user(async_session, email="jerome@test.local", full_name="Jerome Plain")
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, "jérôme@test.local") == []

    async def test_a_blank_name_is_as_unfindable_as_a_missing_one(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        """The column is only NOT NULL — the database really does accept "   "."""
        await _user(async_session, email="blank@test.local", full_name="   ")
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, "blank@test.local") == []

    async def test_both_mailboxes_answer_when_only_case_separates_them(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        """The UNIQUE index is on the raw string, so both rows can exist."""
        upper = await _user(async_session, email="Twin@test.local", full_name="Twin Upper")
        lower = await _user(async_session, email="twin@test.local", full_name="Twin Lower")
        service = PeersService(async_session)

        matches = await service.search_discoverable(searcher.id, "TWIN@test.local")

        assert {m.peer_id for m in matches} == {upper.id, lower.id}


class TestSearchByName:
    """The pre-existing branch, re-proven against the same scan."""

    async def test_accents_and_case_are_folded_away_for_a_name(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        target = await _user(async_session, email="jerome2@test.local", full_name="Jérôme Lefèvre")
        service = PeersService(async_session)

        matches = await service.search_discoverable(searcher.id, "jerome lefevre")

        assert [m.peer_id for m in matches] == [target.id]

    async def test_a_name_never_reaches_a_row_by_its_address(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        """The two folds never mix: a name is compared to names only."""
        await _user(async_session, email="beta@test.local", full_name="Peer Beta")
        service = PeersService(async_session)
        # No '@'-free spelling of the address can be a name match either.
        assert await service.search_discoverable(searcher.id, "beta test.local") == []

    async def test_a_substring_of_a_name_finds_nobody(
        self, async_session: AsyncSession, searcher: User
    ) -> None:
        await _user(async_session, email="long@test.local", full_name="Alexandra Martin")
        service = PeersService(async_session)
        assert await service.search_discoverable(searcher.id, "Alexandra") == []
        assert await service.search_discoverable(searcher.id, "Martin") == []
