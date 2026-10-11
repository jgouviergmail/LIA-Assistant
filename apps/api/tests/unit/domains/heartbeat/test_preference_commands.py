"""The UI and native proposals share canonical, row-locked heartbeat writes."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


def actor() -> User:
    return User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        heartbeat_enabled=True,
        heartbeat_notify_start_hour=8,
        heartbeat_notify_end_hour=22,
        heartbeat_disabled_sources=None,
        moment_kinds_disabled=None,
    )


async def test_explicit_null_is_an_omission_and_empty_lists_clear_refusals() -> None:
    owner = actor()
    owner.heartbeat_disabled_sources = ["calendar"]
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = owner
    commands = import_module("src.domains.heartbeat.preference_commands")
    await commands.update_heartbeat_preferences(
        db,
        owner.id,
        HeartbeatSettingsUpdate(heartbeat_enabled=None, heartbeat_disabled_sources=None),
    )
    assert owner.heartbeat_enabled is True
    assert owner.heartbeat_disabled_sources == ["calendar"]
    db.commit.assert_not_awaited()
    await commands.update_heartbeat_preferences(
        db, owner.id, HeartbeatSettingsUpdate(heartbeat_disabled_sources=[])
    )
    assert owner.heartbeat_disabled_sources == []
    db.commit.assert_awaited_once()


async def test_unknown_source_refuses_before_any_field_changes_or_commit() -> None:
    owner = actor()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = owner
    commands = import_module("src.domains.heartbeat.preference_commands")
    with pytest.raises(ValueError):
        await commands.update_heartbeat_preferences(
            db,
            owner.id,
            HeartbeatSettingsUpdate(heartbeat_enabled=False, heartbeat_disabled_sources=["forged"]),
        )
    assert owner.heartbeat_enabled is True
    db.commit.assert_not_awaited()


async def test_approved_list_snapshot_is_semantic_but_materialization_is_a_real_write() -> None:
    owner = actor()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = owner
    commands = import_module("src.domains.heartbeat.preference_commands")
    receipt = PreferenceWriteReceipt()
    await commands.update_heartbeat_preferences(
        db,
        owner.id,
        HeartbeatSettingsUpdate(heartbeat_disabled_sources=[]),
        expected={"heartbeat_disabled_sources": []},
        receipt=receipt,
    )
    assert owner.heartbeat_disabled_sources == []
    assert receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()


async def test_an_intervening_ui_save_refuses_stale_confirmation_under_the_lock() -> None:
    owner = actor()
    owner.heartbeat_disabled_sources = ["calendar"]
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = owner
    commands = import_module("src.domains.heartbeat.preference_commands")
    with pytest.raises(ResourceConflictError):
        await commands.update_heartbeat_preferences(
            db,
            owner.id,
            HeartbeatSettingsUpdate(heartbeat_disabled_sources=[]),
            expected={"heartbeat_disabled_sources": []},
        )
    assert owner.heartbeat_disabled_sources == ["calendar"]
    db.commit.assert_not_awaited()


async def test_overnight_hours_are_valid_and_duplicate_sources_are_canonical() -> None:
    owner = actor()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = owner
    commands = import_module("src.domains.heartbeat.preference_commands")
    await commands.update_heartbeat_preferences(
        db,
        owner.id,
        HeartbeatSettingsUpdate(
            heartbeat_notify_start_hour=22,
            heartbeat_notify_end_hour=6,
            heartbeat_disabled_sources=["calendar", "calendar"],
        ),
    )
    assert (owner.heartbeat_notify_start_hour, owner.heartbeat_notify_end_hour) == (22, 6)
    assert owner.heartbeat_disabled_sources == ["calendar"]
    db.commit.assert_awaited_once()


async def test_inactive_or_missing_account_is_never_a_write_target() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    commands = import_module("src.domains.heartbeat.preference_commands")
    with pytest.raises(BaseAPIException):
        await commands.update_heartbeat_preferences(
            db, uuid4(), HeartbeatSettingsUpdate(heartbeat_enabled=False)
        )
    db.commit.assert_not_awaited()
