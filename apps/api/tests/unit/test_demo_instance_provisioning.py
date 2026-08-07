"""Provisioning a demonstrator database: the marker, and nothing implicit.

Two switches decide whether an instance behaves as a demonstrator, and they
live in different places on purpose (incident of 2026-08-06):

- ``DEMO_MODE_ENABLED`` describes the PROCESS — it can be set by a script, a
  shell, a test harness pointed at the wrong database;
- ``DEMO_INSTANCE_MARKER`` lives in the DATABASE the nightly purge would
  empty. Without it, the purge refuses.

So provisioning is the deliberate act of saying "this database is a
demonstrator's". It must be explicit, idempotent, and it must refuse to run
against a database that already holds real accounts.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.system_settings.models import SystemSettingKey

pytestmark = pytest.mark.unit


def _db(*, existing_marker: str | None = None, account_count: int = 0) -> MagicMock:
    marker_row = MagicMock(value=existing_marker) if existing_marker is not None else None
    result = MagicMock()
    result.scalar_one_or_none.return_value = marker_row
    result.scalar_one.return_value = account_count
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _context(db: MagicMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context)


async def test_provisioning_writes_the_marker() -> None:
    from src.infrastructure.provisioning.demo_instance import provision_demo_instance

    db = _db()
    with (
        patch("src.infrastructure.provisioning.demo_instance.get_db_context", _context(db)),
        patch(
            "src.infrastructure.provisioning.demo_instance.invalidate_setting_cache",
            new_callable=AsyncMock,
        ),
    ):
        report = await provision_demo_instance(force=False)

    assert report.marker_written is True
    # Pick the marker out of the recorded calls rather than reading the LAST
    # one: provisioning also writes the demonstrator's initial settings, so a
    # positional oracle breaks the day another default is added — and it did.
    markers = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args and call.args[0].key is SystemSettingKey.DEMO_INSTANCE_MARKER
    ]
    assert len(markers) == 1
    assert markers[0].value == "true"
    db.commit.assert_awaited()


async def test_provisioning_is_idempotent() -> None:
    from src.infrastructure.provisioning.demo_instance import provision_demo_instance

    db = _db(existing_marker="true")
    with (
        patch("src.infrastructure.provisioning.demo_instance.get_db_context", _context(db)),
        patch(
            "src.infrastructure.provisioning.demo_instance.invalidate_setting_cache",
            new_callable=AsyncMock,
        ),
    ):
        report = await provision_demo_instance(force=False)

    # Re-running the ceremony must not fail nor duplicate the row. The
    # assertion names the marker: re-provisioning legitimately re-applies the
    # LLM configuration and may fill in a demonstrator default that is still
    # undecided, so "nothing was added at all" is the wrong contract.
    assert report.marker_written is False
    assert report.already_provisioned is True
    assert not [
        call
        for call in db.add.call_args_list
        if call.args and call.args[0].key is SystemSettingKey.DEMO_INSTANCE_MARKER
    ]


async def test_provisioning_refuses_a_database_that_holds_accounts() -> None:
    from src.infrastructure.provisioning.demo_instance import provision_demo_instance

    db = _db(account_count=7)
    with patch("src.infrastructure.provisioning.demo_instance.get_db_context", _context(db)):
        report = await provision_demo_instance(force=False)

    # Marking a populated database as a demonstrator arms a nightly purge on
    # somebody's real accounts. Exactly what happened on 2026-08-06.
    assert report.marker_written is False
    assert report.refused_reason == "database_not_empty"
    db.add.assert_not_called()


async def test_force_is_the_only_way_past_a_populated_database() -> None:
    from src.infrastructure.provisioning.demo_instance import provision_demo_instance

    db = _db(account_count=7)
    with (
        patch("src.infrastructure.provisioning.demo_instance.get_db_context", _context(db)),
        patch(
            "src.infrastructure.provisioning.demo_instance.invalidate_setting_cache",
            new_callable=AsyncMock,
        ),
    ):
        report = await provision_demo_instance(force=True)

    # Deliberate, explicit, and loud — never a default.
    assert report.marker_written is True
    assert report.refused_reason is None


async def test_the_marker_cache_is_invalidated_after_writing() -> None:
    from src.infrastructure.provisioning.demo_instance import provision_demo_instance

    db = _db()
    with (
        patch("src.infrastructure.provisioning.demo_instance.get_db_context", _context(db)),
        patch(
            "src.infrastructure.provisioning.demo_instance.invalidate_setting_cache",
            new_callable=AsyncMock,
        ) as invalidate,
    ):
        await provision_demo_instance(force=False)

    invalidate.assert_awaited_once_with(SystemSettingKey.DEMO_INSTANCE_MARKER)


async def test_the_report_states_what_it_did() -> None:
    from src.infrastructure.provisioning.demo_instance import ProvisionReport

    # A provisioning step that prints nothing leaves an operator guessing
    # whether the nightly purge is armed.
    report = ProvisionReport(marker_written=True)
    assert "marker" in report.summary().lower()
    refused = ProvisionReport(refused_reason="database_not_empty")
    assert "database_not_empty" in refused.summary()
