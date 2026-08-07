"""The nightly purge must run on an instance that has no administrator.

The terms a visitor accepts say everything is deleted every night. That
sentence is the whole contract of a demonstrator, and it was false: the sweep
credits a superuser in the admin audit trail and fell back to a nil UUID when
the instance had none — `admin_audit_log.admin_user_id` is a NOT NULL foreign
key to `users.id`, so the insert raised, the transaction rolled back, and
NOTHING was deleted.

Measured 2026-08-06 on the first real bring-up: one visitor account, one
connector and eleven messages survived a purge that reported no error to
anyone but the log. A fresh demonstrator has no superuser at all — nobody
creates an admin on a throwaway instance — so this was the NOMINAL path.

An automatic sweep has no administrator behind it. When there is none, the
accounts still go; only the admin audit line, which exists to record what a
human did, is skipped. The structured log keeps the trace.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.unit


class TestOperatorResolution:
    async def test_no_superuser_yields_no_operator(self) -> None:
        from src.infrastructure.scheduler.demo_account_purge import _operator_id

        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        # A nil UUID is not "anonymous", it is a row that does not exist —
        # and the foreign key says so by refusing the whole deletion.
        assert await _operator_id(db) is None

    async def test_a_superuser_is_credited_when_there_is_one(self) -> None:
        from src.infrastructure.scheduler.demo_account_purge import _operator_id

        admin = uuid4()
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: admin))

        assert await _operator_id(db) == admin


class TestAuditIsSkippedNotFaked:
    async def test_deletion_without_an_admin_writes_no_admin_audit_line(self) -> None:
        from src.domains.users.account_deletion_service import AccountDeletionService

        db = MagicMock()
        service = AccountDeletionService(db)
        user = MagicMock(id=uuid4(), email="visitor@example.org", full_name="Visitor")

        added: list[object] = []
        db.add = added.append

        await service._create_audit_log(user, None, "demo_nightly_purge", {}, None)

        assert added == [], (
            "an admin audit line with no admin is a foreign key violation, "
            "and it takes the whole purge down with it"
        )

    async def test_deletion_by_an_admin_still_records_it(self) -> None:
        from src.domains.users.account_deletion_service import AccountDeletionService

        service = AccountDeletionService(MagicMock())
        user = MagicMock(id=uuid4(), email="visitor@example.org", full_name="Visitor")
        admin_id = uuid4()

        write = AsyncMock()
        with patch("src.domains.users.repository.UserRepository.create_audit_log", write):
            await service._create_audit_log(user, admin_id, "admin_request", {}, None)

        # A real administrative deletion stays auditable, with a name on it.
        write.assert_awaited_once()
        assert write.await_args.kwargs["admin_user_id"] == admin_id


class TestTheSweepStillDeletes:
    async def test_a_visitor_is_swept_on_an_instance_without_any_admin(self) -> None:
        """The property the terms promise: the account goes, admin or not."""
        from src.infrastructure.scheduler import demo_account_purge as sweep

        db = MagicMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock()
        user = MagicMock(id=uuid4(), is_active=True)

        deleted = AsyncMock(return_value=(user, {}))
        with (
            patch(
                "src.domains.users.account_deletion_service.AccountDeletionService.delete_account",
                deleted,
            ),
            patch.object(sweep, "delete_user_row", AsyncMock()) as drop_row,
        ):
            await sweep._sweep_one(db, user, None)

        deleted.assert_awaited_once()
        assert deleted.await_args.kwargs["admin_user_id"] is None
        drop_row.assert_awaited_once()


def test_the_nil_uuid_never_appears_as_an_operator() -> None:
    """No caller may resurrect the fallback that caused the failure."""
    from pathlib import Path

    source = Path("src/infrastructure/scheduler/demo_account_purge.py").read_text(encoding="utf-8")
    assert "UUID(int=0)" not in source, (
        "a nil UUID is a users.id that does not exist; the audit insert fails "
        "and the sweep deletes nothing"
    )
    assert str(UUID(int=0)) not in source
