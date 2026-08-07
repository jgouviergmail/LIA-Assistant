"""Nightly wipe of visitor accounts on a demonstrator instance.

The owner's rule: everything resets each night, so the next day starts from
zero. That is what makes an open demonstrator sustainable — no data
accumulates, no account survives, nothing to leak later.

Why the row itself must go, not just its data: the production deletion path
KEEPS the users row with its email (billing contact, ADR-067). On a
demonstrator that would lock the address forever — the same visitor could
never come back the next day, which is precisely the journey we advertise.

What must hold:
- it never runs unless the instance is a demonstrator, and that requires TWO
  independent conditions: the environment flag AND a marker stored in the
  database it would empty. Measured the hard way on 2026-08-06: a proof
  script that forced the flag on a dev database deleted seven real accounts.
  An environment variable describes a PROCESS and can be set by anything
  pointed at the wrong database; the marker travels with the DATA;
- superusers are never touched: the operator must still be able to log in
  tomorrow morning;
- each account is purged through the AUDITED production path, then its row is
  removed — no hand-rolled DELETE cascade that would drift from it;
- one failing account does not abort the sweep;
- the outcome is reported (counts), so a silent no-op is visible.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _settings(demo: bool) -> MagicMock:
    fake = MagicMock()
    fake.demo_mode_enabled = demo
    return fake


def _marker(present: bool) -> object:
    """Patch the database-side demonstrator marker."""
    return patch(
        "src.domains.system_settings.registry.read_setting",
        AsyncMock(return_value=present),
    )


def _user(*, superuser: bool = False) -> MagicMock:
    return MagicMock(id=uuid4(), email="visitor@example.com", is_superuser=superuser)


def _db(users: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = users
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    # The error path rolls back; a double that omits it would let a real
    # unawaited coroutine slip through.
    db.rollback = AsyncMock()
    return db


def _context(db: MagicMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context)


async def test_the_purge_refuses_to_run_outside_demo_mode() -> None:
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    db = _db([_user()])
    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=False)),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
    ):
        report = await purge_demo_accounts()

    # A private instance must not lose its users to a misconfigured schedule.
    assert report.purged == 0
    assert report.skipped_reason == "demo_mode_disabled"
    db.execute.assert_not_awaited()


async def test_every_visitor_account_is_purged_then_removed() -> None:
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    visitors = [_user(), _user()]
    db = _db(visitors)
    deletion = MagicMock()
    deletion.return_value.delete_account = AsyncMock(return_value=(MagicMock(), {}))

    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=True)),
        _marker(True),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
        patch("src.domains.users.account_deletion_service.AccountDeletionService", deletion),
        patch(
            "src.infrastructure.scheduler.demo_account_purge.delete_user_row",
            new_callable=AsyncMock,
        ) as drop_row,
    ):
        report = await purge_demo_accounts()

    assert report.purged == 2
    # The audited production path does the data purge...
    assert deletion.return_value.delete_account.await_count == 2
    # ...and only then does the row go, so the address is free again tomorrow.
    assert drop_row.await_count == 2


async def test_a_superuser_is_never_swept() -> None:
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    db = _db([])
    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=True)),
        _marker(True),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
    ):
        await purge_demo_accounts()

    # The exclusion is in the QUERY, not in a later filter: an operator
    # locked out of their own demonstrator has no way back in.
    compiled = str(db.execute.await_args.args[0]).lower()
    assert "is_superuser" in compiled


async def test_one_failing_account_does_not_abort_the_sweep() -> None:
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    visitors = [_user(), _user(), _user()]
    db = _db(visitors)
    deletion = MagicMock()
    deletion.return_value.delete_account = AsyncMock(
        side_effect=[RuntimeError("locked"), (MagicMock(), {}), (MagicMock(), {})]
    )

    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=True)),
        _marker(True),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
        patch("src.domains.users.account_deletion_service.AccountDeletionService", deletion),
        patch(
            "src.infrastructure.scheduler.demo_account_purge.delete_user_row",
            new_callable=AsyncMock,
        ),
    ):
        report = await purge_demo_accounts()

    # Two survivors is better than a whole night skipped.
    assert report.purged == 2
    assert report.failed == 1


async def test_an_account_is_deactivated_before_deletion() -> None:
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    visitor = _user()
    visitor.is_active = True
    db = _db([visitor])
    deletion = MagicMock()
    deletion.return_value.delete_account = AsyncMock(return_value=(MagicMock(), {}))

    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=True)),
        _marker(True),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
        patch("src.domains.users.account_deletion_service.AccountDeletionService", deletion),
        patch(
            "src.infrastructure.scheduler.demo_account_purge.delete_user_row",
            new_callable=AsyncMock,
        ),
    ):
        await purge_demo_accounts()

    # The production deletion path refuses an active account (409), so the
    # sweep must deactivate first — the visitor's session dies here, which is
    # exactly the announced nightly reset.
    assert visitor.is_active is False


async def test_an_empty_instance_reports_zero_rather_than_failing() -> None:
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    db = _db([])
    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=True)),
        _marker(True),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
    ):
        report = await purge_demo_accounts()

    assert report.purged == 0
    assert report.failed == 0
    assert report.skipped_reason is None


async def test_the_flag_alone_never_authorizes_deleting_accounts() -> None:
    """The incident of 2026-08-06, turned into a permanent guard.

    A proof script set DEMO_MODE_ENABLED on a process pointed at the dev
    database and the sweep deleted seven real accounts. The flag describes the
    process; only a marker stored in the database can vouch for the database.
    """
    from src.infrastructure.scheduler.demo_account_purge import purge_demo_accounts

    db = _db([_user(), _user()])
    with (
        patch("src.infrastructure.scheduler.demo_account_purge.settings", _settings(demo=True)),
        _marker(True),
        _marker(False),
        patch("src.infrastructure.scheduler.demo_account_purge.get_db_context", _context(db)),
    ):
        report = await purge_demo_accounts()

    assert report.purged == 0
    assert report.skipped_reason == "instance_marker_absent"
    # Not one query against the accounts it was about to delete.
    db.execute.assert_not_awaited()


async def test_the_marker_is_read_from_the_database_never_from_a_cache() -> None:
    from src.domains.system_settings.models import SystemSettingKey
    from src.domains.system_settings.registry import get_setting_spec

    spec = get_setting_spec(SystemSettingKey.DEMO_INSTANCE_MARKER)
    # A cached authorization to delete every account could outlive the truth
    # by a whole TTL — and a stale "true" is unrecoverable.
    assert spec.redis_key is None
    assert spec.default is False
