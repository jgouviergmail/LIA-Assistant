"""Leader-elected push channel sync job (lot H, 2026-08).

Contract: flag OFF means strictly nothing happens (polling is the behavior);
phase 2 (Gmail) only joins when its own flag is on; one user's failure never
stops the sweep (push is an optimization — the fallback is bounded staleness,
not an outage).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.push_channels import sync as sync_module

pytestmark = pytest.mark.unit


class TestSyncPushChannels:
    async def test_flag_off_is_a_strict_noop(self) -> None:
        with (
            patch.object(sync_module, "settings") as mock_settings,
            patch.object(sync_module, "_list_user_ids", new=AsyncMock()) as list_users,
            patch.object(sync_module, "_purge_orphan_channels", new=AsyncMock()) as purge,
        ):
            mock_settings.push_channels_enabled = False
            result = await sync_module.sync_push_channels()
        assert result == {"ensured": 0, "errors": 0, "purged": 0}
        list_users.assert_not_awaited()
        purge.assert_not_awaited()

    async def test_phase1_syncs_calendar_and_drive_but_not_gmail(self) -> None:
        user_id = uuid4()
        with (
            patch.object(sync_module, "settings") as mock_settings,
            patch.object(sync_module, "_list_user_ids", new=AsyncMock(return_value=[user_id])),
            patch.object(sync_module, "_ensure_user_calendar", new=AsyncMock()) as ensure_calendar,
            patch.object(sync_module, "_ensure_user_drive", new=AsyncMock()) as ensure_drive,
            patch.object(sync_module, "_ensure_user_gmail", new=AsyncMock()) as ensure_gmail,
            patch.object(
                sync_module, "_purge_orphan_channels", new=AsyncMock(return_value=0)
            ) as purge,
        ):
            mock_settings.push_channels_enabled = True
            mock_settings.gmail_push_enabled = False
            result = await sync_module.sync_push_channels()
        assert result == {"ensured": 2, "errors": 0, "purged": 0}
        ensure_calendar.assert_awaited_once_with(user_id)
        ensure_drive.assert_awaited_once_with(user_id)
        ensure_gmail.assert_not_awaited()
        # Orphan purge covers exactly the swept providers (gmail is out of
        # scope while phase 2 is off — its dedup ledger must survive).
        purge.assert_awaited_once_with({"google_calendar": {user_id}, "google_drive": {user_id}})

    async def test_gmail_joins_when_phase2_is_enabled(self) -> None:
        user_id = uuid4()
        with (
            patch.object(sync_module, "settings") as mock_settings,
            patch.object(sync_module, "_list_user_ids", new=AsyncMock(return_value=[user_id])),
            patch.object(sync_module, "_ensure_user_calendar", new=AsyncMock()),
            patch.object(sync_module, "_ensure_user_drive", new=AsyncMock()),
            patch.object(sync_module, "_ensure_user_gmail", new=AsyncMock()) as ensure_gmail,
            patch.object(sync_module, "_purge_orphan_channels", new=AsyncMock(return_value=0)),
        ):
            mock_settings.push_channels_enabled = True
            mock_settings.gmail_push_enabled = True
            result = await sync_module.sync_push_channels()
        assert result == {"ensured": 3, "errors": 0, "purged": 0}
        ensure_gmail.assert_awaited_once_with(user_id)

    async def test_one_users_failure_does_not_stop_the_sweep(self) -> None:
        failing, healthy = uuid4(), uuid4()
        with (
            patch.object(sync_module, "settings") as mock_settings,
            patch.object(
                sync_module,
                "_list_user_ids",
                new=AsyncMock(return_value=[failing, healthy]),
            ),
            patch.object(
                sync_module,
                "_ensure_user_calendar",
                new=AsyncMock(side_effect=[RuntimeError("api down"), None]),
            ) as ensure_calendar,
            patch.object(sync_module, "_ensure_user_drive", new=AsyncMock()),
            patch.object(sync_module, "_ensure_user_gmail", new=AsyncMock()),
            patch.object(sync_module, "_purge_orphan_channels", new=AsyncMock(return_value=0)),
        ):
            mock_settings.push_channels_enabled = True
            mock_settings.gmail_push_enabled = False
            result = await sync_module.sync_push_channels()
        assert ensure_calendar.await_count == 2
        assert result["errors"] == 1
        assert result["ensured"] == 3  # 1 calendar + 2 drive

    async def test_orphan_purge_deletes_channels_without_an_active_connector(self) -> None:
        kept_user, orphan_user = uuid4(), uuid4()
        repo = MagicMock()
        repo.delete_channels_not_in = AsyncMock(side_effect=[1, 0])
        db = MagicMock()
        db.commit = AsyncMock()

        class _Ctx:
            async def __aenter__(self) -> MagicMock:
                return db

            async def __aexit__(self, *args: object) -> None:
                return None

        with (
            patch.object(sync_module, "get_db_context", new=lambda: _Ctx()),
            patch.object(sync_module, "PushChannelRepository", return_value=repo),
        ):
            purged = await sync_module._purge_orphan_channels(
                {"google_calendar": {kept_user}, "google_drive": {kept_user, orphan_user}}
            )

        assert purged == 1
        calls = {call.args[0]: call.args[1] for call in repo.delete_channels_not_in.await_args_list}
        assert calls["google_calendar"] == {kept_user}
        assert calls["google_drive"] == {kept_user, orphan_user}
        db.commit.assert_awaited()
