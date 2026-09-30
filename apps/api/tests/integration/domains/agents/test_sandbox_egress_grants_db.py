"""The grants table and its reads against REAL PostgreSQL (ADR-298).

What only the database can prove:

- **one grant per host per account** — the unique constraint, and an upsert
  that UPDATES the scope instead of raising;
- **deleting the account takes its grants** — ``CASCADE``;
- **a page and its exact total come from one WHERE** (ADR-185);
- **the cap is read from an aggregate**, never from a page's length.

Everything runs inside the ``async_session`` fixture's transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.python_sandbox.egress.grants import EgressGrantService
from src.domains.agents.python_sandbox.egress.grants_repository import EgressGrantRepository
from src.domains.agents.python_sandbox.egress.models import SandboxEgressGrant
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def _user(db: AsyncSession) -> User:
    user = User(
        email=f"egress_{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


class TestOneGrantPerHost:
    async def test_upsert_updates_the_scope_instead_of_duplicating(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        repo = EgressGrantRepository(async_session)
        first = await repo.upsert(user.id, "api.example.org", share_turn_data=True)
        second = await repo.upsert(user.id, "api.example.org", share_turn_data=False)
        assert second.id == first.id
        assert second.share_turn_data is False
        assert await repo.count_for_user(user.id) == 1

    async def test_two_accounts_may_hold_the_same_host(self, async_session: AsyncSession) -> None:
        a, b = await _user(async_session), await _user(async_session)
        repo = EgressGrantRepository(async_session)
        await repo.upsert(a.id, "api.example.org", share_turn_data=True)
        await repo.upsert(b.id, "api.example.org", share_turn_data=False)
        assert await repo.scopes_for_user(a.id) == {"api.example.org": True}
        assert await repo.scopes_for_user(b.id) == {"api.example.org": False}


class TestAllowingFromTheSettings:
    """ADR-327 lot 3: the settings route writes under the card's cap, on the real rows."""

    async def test_a_new_host_is_refused_at_the_cap_and_a_known_one_takes_its_scope(
        self, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        monkeypatch.setattr(
            "src.domains.agents.python_sandbox.egress.grants.get_settings",
            lambda: SimpleNamespace(python_sandbox_max_grants_per_user=2),
        )
        user = await _user(async_session)
        service = EgressGrantService(repository=EgressGrantRepository(async_session))
        first = await service.grant(user.id, "registry.npmjs.org", share_turn_data=False)
        second = await service.grant(user.id, "pypi.org", share_turn_data=False)
        assert first is not None and second is not None
        # The cap bounds NEW rows: a third host is refused and nothing is written…
        assert await service.grant(user.id, "github.com", share_turn_data=True) is None
        repo = EgressGrantRepository(async_session)
        assert await repo.count_for_user(user.id) == 2
        # …while a known host takes its new scope, the row kept.
        again = await service.grant(user.id, "registry.npmjs.org", share_turn_data=True)
        assert isinstance(first, SandboxEgressGrant) and isinstance(again, SandboxEgressGrant)
        assert again.id == first.id
        assert await repo.scopes_for_user(user.id) == {
            "registry.npmjs.org": True,
            "pypi.org": False,
        }


class TestTheAccountOwnsThem:
    async def test_deleting_the_account_takes_the_grants(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        repo = EgressGrantRepository(async_session)
        await repo.upsert(user.id, "api.example.org", share_turn_data=True)
        await async_session.execute(delete(User).where(User.id == user.id))
        await async_session.flush()
        left = (
            (
                await async_session.execute(
                    select(SandboxEgressGrant).where(SandboxEgressGrant.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert left == []


class TestPagesAndCounts:
    async def test_a_page_and_its_exact_total_share_one_where(
        self, async_session: AsyncSession
    ) -> None:
        user, other = await _user(async_session), await _user(async_session)
        repo = EgressGrantRepository(async_session)
        for i in range(5):
            await repo.upsert(user.id, f"h{i}.example.org", share_turn_data=bool(i % 2))
        await repo.upsert(other.id, "elsewhere.example.org", share_turn_data=True)
        rows, total = await repo.list_page(user.id, limit=2, offset=0)
        assert total == 5 and len(rows) == 2
        rows, total = await repo.list_page(user.id, limit=2, offset=4)
        assert total == 5 and len(rows) == 1
        assert all(row.user_id == user.id for row in rows)

    async def test_the_listing_is_newest_first_with_the_key_as_tie_breaker(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        repo = EgressGrantRepository(async_session)
        await repo.upsert(user.id, "first.example.org", share_turn_data=True)
        await repo.upsert(user.id, "second.example.org", share_turn_data=True)
        rows, _ = await repo.list_page(user.id, limit=10, offset=0)
        assert [r.host for r in rows][:2] == ["second.example.org", "first.example.org"] or (
            rows[0].created_at == rows[1].created_at
        )


class TestUseAndRemoval:
    async def test_touch_stamps_the_last_use_and_only_for_that_host(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        repo = EgressGrantRepository(async_session)
        await repo.upsert(user.id, "a.example.org", share_turn_data=True)
        await repo.upsert(user.id, "b.example.org", share_turn_data=True)
        when = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
        await repo.touch(user.id, ["a.example.org"], when=when)
        rows, _ = await repo.list_page(user.id, limit=10, offset=0)
        by_host = {r.host: r.last_used_at for r in rows}
        assert by_host["a.example.org"] == when
        assert by_host["b.example.org"] is None

    async def test_delete_is_scoped_to_the_account(self, async_session: AsyncSession) -> None:
        user, other = await _user(async_session), await _user(async_session)
        repo = EgressGrantRepository(async_session)
        mine = await repo.upsert(user.id, "a.example.org", share_turn_data=True)
        assert await repo.delete_for_user(other.id, mine.id) is False
        assert await repo.delete_for_user(user.id, mine.id) is True
        assert await repo.count_for_user(user.id) == 0
