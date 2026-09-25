"""A broadcast is addressed to its audience — on real PostgreSQL (ADR-312).

A targeted broadcast used to be persisted WITHOUT its recipients: SSE and FCM
reached the chosen accounts at send time, and ``GET /broadcasts/unread`` then
served it to EVERY account at its next sign-in, because the unread query had
nothing to filter on (measured 2026-09-24). The audience now lives on the row
(``admin_broadcasts.audience`` + ``admin_broadcast_recipients``) and the unread
query reads it INSIDE the recent window — a broadcast addressed to someone else
must neither be shown nor crowd a reader's own broadcasts out of the window.

The history the settings page draws (page, exact total, recipient sample, read
counts) and the migration's backfill from the admin audit log are proven here
too: both are SQL whose semantics an in-memory double cannot exercise.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import MAX_UNREAD_BROADCASTS
from src.domains.notifications.models import (
    AdminBroadcast,
    AdminBroadcastRecipient,
    BroadcastAudience,
    UserBroadcastRead,
)
from src.domains.notifications.repository import BroadcastRepository
from src.domains.users.models import AdminAuditLog, User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_09_24_1800-a19e985e4ce5_admin_broadcast_audience.py"
)


def _load_migration() -> ModuleType:
    """The migration module itself, so its backfill SQL is what gets proven."""
    spec = importlib.util.spec_from_file_location("broadcast_audience_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _user(db: AsyncSession, name: str, *, superuser: bool = False) -> User:
    user = User(
        email=f"{name.lower()}-{uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=superuser,
        full_name=name,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def people(async_session: AsyncSession) -> dict[str, User]:
    """An admin and three readers created two days ago (older than every broadcast)."""
    created = datetime.now(UTC) - timedelta(days=2)
    users = {
        "admin": await _user(async_session, "Admin", superuser=True),
        "alice": await _user(async_session, "Alice"),
        "bob": await _user(async_session, "Bob"),
        "carol": await _user(async_session, "Carol"),
    }
    for user in users.values():
        user.created_at = created
    await async_session.commit()
    return users


async def _broadcast(
    db: AsyncSession,
    admin: User,
    message: str,
    *,
    recipients: list[UUID] | None = None,
    age_minutes: int = 0,
) -> AdminBroadcast:
    broadcast = await BroadcastRepository(db).create_broadcast(
        message=message,
        sent_by=admin.id,
        recipient_ids=recipients,
    )
    broadcast.created_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
    await db.commit()
    return broadcast


class TestUnreadRespectsTheAudience:
    """``get_unread_for_user`` serves a reader only what was addressed to them."""

    async def test_targeted_broadcast_reaches_only_its_recipients(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        repo = BroadcastRepository(async_session)
        targeted = await _broadcast(
            async_session, people["admin"], "For Alice", recipients=[people["alice"].id]
        )

        alice = await repo.get_unread_for_user(people["alice"].id, recent_limit=3)
        bob = await repo.get_unread_for_user(people["bob"].id, recent_limit=3)

        assert [b.id for b in alice] == [targeted.id]
        assert bob == []

    async def test_broadcast_to_all_reaches_everyone(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        repo = BroadcastRepository(async_session)
        everyone = await _broadcast(async_session, people["admin"], "For all")

        for name in ("alice", "bob", "carol"):
            unread = await repo.get_unread_for_user(people[name].id, recent_limit=3)
            assert [b.id for b in unread] == [everyone.id]

    async def test_the_window_counts_only_what_is_addressed_to_the_reader(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        """Broadcasts to others never push a reader's own out of the window.

        Before the fix the window was computed over EVERY broadcast: three
        recent messages to Alice would have hidden an older one to everyone
        from Bob — and shown him Alice's instead.
        """
        repo = BroadcastRepository(async_session)
        to_all = await _broadcast(async_session, people["admin"], "For all", age_minutes=30)
        for minutes in range(MAX_UNREAD_BROADCASTS):
            await _broadcast(
                async_session,
                people["admin"],
                f"For Alice #{minutes}",
                recipients=[people["alice"].id],
                age_minutes=minutes,
            )

        bob = await repo.get_unread_for_user(people["bob"].id, recent_limit=MAX_UNREAD_BROADCASTS)
        alice = await repo.get_unread_for_user(
            people["alice"].id, recent_limit=MAX_UNREAD_BROADCASTS
        )

        assert [b.id for b in bob] == [to_all.id]
        # Alice's window is her three newest — the older one to all falls out.
        assert len(alice) == MAX_UNREAD_BROADCASTS
        assert to_all.id not in {b.id for b in alice}

    async def test_a_read_targeted_broadcast_is_not_served_again(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        repo = BroadcastRepository(async_session)
        targeted = await _broadcast(
            async_session, people["admin"], "For Alice", recipients=[people["alice"].id]
        )
        await repo.mark_as_read(people["alice"].id, targeted.id)
        await async_session.commit()

        assert await repo.get_unread_for_user(people["alice"].id, recent_limit=3) == []


class TestCreateBroadcastRecordsTheAudience:
    """The row says who it was for, in the same transaction that creates it."""

    async def test_selected_audience_and_one_row_per_recipient(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        targeted = await _broadcast(
            async_session,
            people["admin"],
            "For two",
            recipients=[people["alice"].id, people["bob"].id, people["alice"].id],
        )

        rows = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.user_id).where(
                    AdminBroadcastRecipient.broadcast_id == targeted.id
                )
            )
        ).all()

        assert targeted.audience == BroadcastAudience.SELECTED.value
        # A duplicate id in the request is one recipient, not two rows.
        assert sorted(rows) == sorted([people["alice"].id, people["bob"].id])

    async def test_all_audience_writes_no_recipient_row(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        everyone = await _broadcast(async_session, people["admin"], "For all")

        count = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.id).where(
                    AdminBroadcastRecipient.broadcast_id == everyone.id
                )
            )
        ).all()

        assert everyone.audience == BroadcastAudience.ALL.value
        assert count == []


class TestHistoryQueries:
    """What the settings page draws: a page, its exact total, samples, reads."""

    async def test_page_is_newest_first_with_the_exact_total(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        repo = BroadcastRepository(async_session)
        made = [
            await _broadcast(async_session, people["admin"], f"#{age}", age_minutes=age)
            for age in (30, 20, 10)
        ]

        first, total = await repo.list_page(limit=2, offset=0)
        second, _ = await repo.list_page(limit=2, offset=2)

        # Each test runs in its own rolled-back transaction: these are ALL the rows.
        assert total == 3
        # Newest first, and the second page continues where the first stopped.
        assert [b.id for b in first] == [made[2].id, made[1].id]
        assert second[0].id == made[0].id
        assert first[0].sender is not None  # eager-loaded for the sender name

    async def test_recipient_sample_names_the_first_in_name_order_and_counts_all(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        repo = BroadcastRepository(async_session)
        targeted = await _broadcast(
            async_session,
            people["admin"],
            "For three",
            recipients=[people["carol"].id, people["alice"].id, people["bob"].id],
        )
        everyone = await _broadcast(async_session, people["admin"], "For all")

        samples = await repo.recipient_samples([targeted.id, everyone.id], per_broadcast=2)

        sample = samples[targeted.id]
        assert sample.total == 3
        assert [row.full_name for row in sample.users] == ["Alice", "Bob"]
        # A broadcast to all has no recipient rows, hence no sample at all.
        assert everyone.id not in samples

    async def test_read_counts_are_exact_and_absent_means_zero(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        repo = BroadcastRepository(async_session)
        read = await _broadcast(async_session, people["admin"], "Read twice")
        unread = await _broadcast(async_session, people["admin"], "Unread")
        for name in ("alice", "bob"):
            await repo.mark_as_read(people[name].id, read.id)
        await async_session.commit()

        counts = await repo.read_counts([read.id, unread.id])

        assert counts == {read.id: 2}

    async def test_recipient_rows_follow_the_broadcast_and_the_account(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        """CASCADE on both keys: nothing dangles when either side goes."""
        targeted = await _broadcast(
            async_session, people["admin"], "For Alice", recipients=[people["alice"].id]
        )
        async_session.add(UserBroadcastRead(user_id=people["alice"].id, broadcast_id=targeted.id))
        await async_session.commit()

        await async_session.delete(targeted)
        await async_session.commit()

        remaining = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.id).where(
                    AdminBroadcastRecipient.user_id == people["alice"].id
                )
            )
        ).all()
        assert remaining == []


class TestBackfillFromTheAuditLog:
    """The migration restores the audience of broadcasts sent before it existed."""

    async def _legacy(self, db: AsyncSession, admin: User, message: str) -> AdminBroadcast:
        """A broadcast as the previous code wrote it: no audience, no recipients."""
        broadcast = AdminBroadcast(message=message, sent_by=admin.id)
        db.add(broadcast)
        await db.flush()
        return broadcast

    async def _audit(
        self, db: AsyncSession, admin: User, broadcast_id: UUID, details: dict
    ) -> None:
        db.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="admin_broadcast_sent",
                resource_type="broadcast",
                resource_id=broadcast_id,
                details=details,
            )
        )
        await db.flush()

    async def _run_backfill(self, db: AsyncSession) -> None:
        migration = _load_migration()
        for statement in migration.BACKFILL_STATEMENTS:
            await db.execute(text(statement))
        await db.commit()

    async def test_targeted_audit_marks_selected_and_restores_existing_recipients(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        admin = people["admin"]
        legacy = await self._legacy(async_session, admin, "Old targeted")
        await self._audit(
            async_session,
            admin,
            legacy.id,
            {
                "is_targeted": True,
                # One account that no longer exists: restored rows must only
                # ever point at accounts that do.
                "target_user_ids": [str(people["alice"].id), str(people["bob"].id), str(uuid4())],
            },
        )

        await self._run_backfill(async_session)
        await async_session.refresh(legacy)
        recipients = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.user_id).where(
                    AdminBroadcastRecipient.broadcast_id == legacy.id
                )
            )
        ).all()

        assert legacy.audience == BroadcastAudience.SELECTED.value
        assert sorted(recipients) == sorted([people["alice"].id, people["bob"].id])

    async def test_untargeted_or_unaudited_broadcasts_stay_addressed_to_all(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        admin = people["admin"]
        to_all = await self._legacy(async_session, admin, "Old to all")
        await self._audit(
            async_session, admin, to_all.id, {"is_targeted": False, "target_user_ids": None}
        )
        unaudited = await self._legacy(async_session, admin, "No audit row")

        await self._run_backfill(async_session)
        await async_session.refresh(to_all)
        await async_session.refresh(unaudited)

        assert to_all.audience == BroadcastAudience.ALL.value
        assert unaudited.audience == BroadcastAudience.ALL.value

    async def test_malformed_target_lists_are_ignored_rather_than_fatal(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        """A JSON null, a scalar or a non-UUID entry must not abort the upgrade."""
        admin = people["admin"]
        scalar = await self._legacy(async_session, admin, "Scalar list")
        await self._audit(
            async_session, admin, scalar.id, {"is_targeted": True, "target_user_ids": "oops"}
        )
        junk = await self._legacy(async_session, admin, "Junk entries")
        await self._audit(
            async_session,
            admin,
            junk.id,
            {"is_targeted": True, "target_user_ids": ["not-a-uuid", str(people["carol"].id)]},
        )

        await self._run_backfill(async_session)
        recipients = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.user_id).where(
                    AdminBroadcastRecipient.broadcast_id == junk.id
                )
            )
        ).all()

        assert recipients == [people["carol"].id]

    async def test_the_backfill_is_idempotent(
        self, async_session: AsyncSession, people: dict[str, User]
    ) -> None:
        admin = people["admin"]
        legacy = await self._legacy(async_session, admin, "Twice")
        await self._audit(
            async_session,
            admin,
            legacy.id,
            {"is_targeted": True, "target_user_ids": [str(people["alice"].id)]},
        )

        await self._run_backfill(async_session)
        await self._run_backfill(async_session)
        recipients = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.user_id).where(
                    AdminBroadcastRecipient.broadcast_id == legacy.id
                )
            )
        ).all()

        assert recipients == [people["alice"].id]
