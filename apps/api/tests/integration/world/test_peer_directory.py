"""Bounded native connections, never an unbounded world read or a private graph broadcast."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.peers.models import PeerBlock, PeerConnection, canonical_pair
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_directory_pages_active_unblocked_accepted_people_without_email(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    from src.domains.peers.directory import page_connected_people

    async with async_sessionmaker(async_engine, expire_on_commit=False)() as db:
        people = [
            User(
                email=f"world-directory-{uuid4().hex}@example.invalid",
                full_name=f"Person {i}",
                is_active=True,
            )
            for i in range(19)
        ]
        db.add_all(people)
        await db.flush()
        committed_user_ids.extend(person.id for person in people)
        owner = people[0]
        for index, person in enumerate(people[1:], 1):
            a, b = canonical_pair(owner.id, person.id)
            db.add(
                PeerConnection(
                    user_a_id=a,
                    user_b_id=b,
                    requested_by_id=owner.id,
                    status="pending" if index == 18 else "accepted",
                )
            )
        db.add(PeerBlock(blocker_id=people[1].id, blocked_id=owner.id))
        db.add(PeerBlock(blocker_id=owner.id, blocked_id=people[2].id))
        people[3].is_active = False
        people[4].full_name = ""
        await db.commit()
        first = await page_connected_people(db, owner.id, after=None, limit=12)
        assert len(first.items) == 12 and first.next_cursor is not None
        second = await page_connected_people(db, owner.id, after=first.next_cursor, limit=12)
        assert len(second.items) == 1 and second.next_cursor is None
        identities = {item.peer_id for item in (*first.items, *second.items)}
        assert len(identities) == 13
        assert not identities & {person.id for person in people[:5] + people[18:]}
        assert all(item.peer_email is None for item in (*first.items, *second.items))
        with pytest.raises(ValueError):
            await page_connected_people(db, owner.id, after=None, limit=1000)
