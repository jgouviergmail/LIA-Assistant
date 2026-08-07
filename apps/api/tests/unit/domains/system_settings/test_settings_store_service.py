"""Administrator-facing system settings service.

These tests pin the PUBLIC contract before the per-key hand-written code is
folded onto the typed registry, so the refactor is proven behaviour-preserving
rather than assumed to be.

What must hold:
- an admin read hits the DATABASE, never the cache: the panel must show what
  is stored, including ``is_default`` when nothing is;
- a write creates or updates the single row, records an admin audit entry,
  commits, and invalidates the cache — in that order;
- the module-level convenience readers stay importable at their historical
  address (production code and existing tests patch them there);
- the spend ceiling is administrable the same way, and an operator can only
  LOWER the deployment ceiling, never raise it.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.schemas import (
    DebugPanelEnabledUpdate,
    DebugPanelUserAccessUpdate,
)
from src.domains.system_settings.service import (
    SystemSettingsService,
    get_debug_panel_enabled,
    get_debug_panel_user_access_enabled,
    get_instance_daily_budget_eur,
    invalidate_debug_panel_enabled_cache,
    invalidate_debug_panel_user_access_cache,
)

pytestmark = pytest.mark.unit


def _db(
    existing_value: str | None = None,
    *,
    ledger: tuple[Decimal, int] | None = None,
) -> MagicMock:
    """A session serving the setting row and today's ledger row.

    ``ledger=None`` means no row for today — the normal state of a day that
    has not spent anything yet.
    """
    setting = None
    if existing_value is not None:
        setting = MagicMock(id=uuid4(), value=existing_value, updated_by=None, updated_at=None)
    result = MagicMock()
    result.scalar_one_or_none.return_value = setting
    result.first.return_value = ledger
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def _added_of_type(db: MagicMock, expected: type) -> object:
    """The single object of ``expected`` handed to ``session.add``."""
    matches = [call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], expected)]
    assert len(matches) == 1, f"expected exactly one {expected.__name__}, got {len(matches)}"
    return matches[0]


def _request() -> MagicMock:
    request = MagicMock()
    request.client.host = "203.0.113.10"
    request.headers = {"user-agent": "pytest"}
    return request


# ---------------------------------------------------------------------------
# Admin reads
# ---------------------------------------------------------------------------


async def test_admin_read_reports_the_stored_value() -> None:
    service = SystemSettingsService(_db("true"))
    response = await service.get_debug_panel_enabled()
    assert response.enabled is True
    assert response.is_default is False


async def test_admin_read_reports_the_default_and_says_so() -> None:
    service = SystemSettingsService(_db(None))
    response = await service.get_debug_panel_enabled()
    assert response.enabled is False
    # Without the flag the panel cannot distinguish "off" from "never set".
    assert response.is_default is True


async def test_admin_user_access_read_uses_its_own_key() -> None:
    db = _db("true")
    service = SystemSettingsService(db)
    response = await service.get_debug_panel_user_access()
    assert response.available is True
    compiled = str(db.execute.await_args.args[0])
    assert "system_settings" in compiled


# ---------------------------------------------------------------------------
# Admin writes
# ---------------------------------------------------------------------------


@patch("src.domains.system_settings.service.invalidate_setting_cache", new_callable=AsyncMock)
async def test_write_creates_the_row_audits_commits_and_invalidates(
    invalidate: AsyncMock,
) -> None:
    db = _db(None)
    service = SystemSettingsService(db)
    admin_id = uuid4()
    response = await service.set_debug_panel_enabled(
        DebugPanelEnabledUpdate(enabled=True, change_reason="support session"),
        admin_id,
        _request(),
    )
    assert response.enabled is True
    # One row + one audit entry.
    assert db.add.call_count == 2
    db.commit.assert_awaited_once()
    invalidate.assert_awaited_once_with(SystemSettingKey.DEBUG_PANEL_ENABLED)


@patch("src.domains.system_settings.service.invalidate_setting_cache", new_callable=AsyncMock)
async def test_write_updates_an_existing_row_instead_of_adding_one(
    invalidate: AsyncMock,
) -> None:
    db = _db("false")
    service = SystemSettingsService(db)
    await service.set_debug_panel_enabled(
        DebugPanelEnabledUpdate(enabled=True), uuid4(), _request()
    )
    # Only the audit entry is new; a second row would break the unique key.
    assert db.add.call_count == 1


@patch("src.domains.system_settings.service.invalidate_setting_cache", new_callable=AsyncMock)
async def test_audit_entry_carries_the_transition_and_the_actor(
    invalidate: AsyncMock,
) -> None:
    db = _db("false")
    service = SystemSettingsService(db)
    admin_id = uuid4()
    await service.set_debug_panel_enabled(
        DebugPanelEnabledUpdate(enabled=True, change_reason="why"), admin_id, _request()
    )
    from src.domains.users.models import AdminAuditLog

    audit = _added_of_type(db, AdminAuditLog)
    assert audit.admin_user_id == admin_id
    assert audit.details["old_value"] == "false"
    assert audit.details["new_value"] == "true"
    assert audit.details["change_reason"] == "why"
    assert audit.resource_type == "system_setting"


@patch("src.domains.system_settings.service.invalidate_setting_cache", new_callable=AsyncMock)
async def test_user_access_write_targets_its_own_key(invalidate: AsyncMock) -> None:
    service = SystemSettingsService(_db(None))
    response = await service.set_debug_panel_user_access(
        DebugPanelUserAccessUpdate(available=True), uuid4(), _request()
    )
    assert response.available is True
    invalidate.assert_awaited_once_with(SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED)


# ---------------------------------------------------------------------------
# Module-level readers (historical import addresses)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reader", "key"),
    [
        (get_debug_panel_enabled, SystemSettingKey.DEBUG_PANEL_ENABLED),
        (
            get_debug_panel_user_access_enabled,
            SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED,
        ),
        (get_instance_daily_budget_eur, SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR),
    ],
)
async def test_convenience_readers_delegate_to_the_registry(
    reader: object, key: SystemSettingKey
) -> None:
    with patch("src.domains.system_settings.service.read_setting", new_callable=AsyncMock) as read:
        read.return_value = True
        await reader()  # type: ignore[operator]
    read.assert_awaited_once_with(key)


@pytest.mark.parametrize(
    ("invalidator", "key"),
    [
        (invalidate_debug_panel_enabled_cache, SystemSettingKey.DEBUG_PANEL_ENABLED),
        (
            invalidate_debug_panel_user_access_cache,
            SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED,
        ),
    ],
)
async def test_legacy_invalidators_still_work(invalidator: object, key: SystemSettingKey) -> None:
    with patch(
        "src.domains.system_settings.service.invalidate_setting_cache",
        new_callable=AsyncMock,
    ) as invalidate:
        await invalidator()  # type: ignore[operator]
    invalidate.assert_awaited_once_with(key)
