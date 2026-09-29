"""The global switch validates effective choices, not unrelated inactive slots."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from src.domains.llm_config import jev_admin as module
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevToggleUpdate

pytestmark = pytest.mark.unit


async def test_inactive_broken_slot_does_not_block_an_enabled_valid_usage() -> None:
    async def readiness(db, usage):
        return ("ready" if usage == JevUsage.MEETING_TEMPLATE else "unavailable_model", None)

    with (
        patch.object(
            module,
            "read_flags",
            AsyncMock(
                return_value={
                    "global": False,
                    **{usage.value: usage == JevUsage.MEETING_TEMPLATE for usage in JevUsage},
                }
            ),
        ),
        patch.object(module, "read_configuration", side_effect=readiness),
        patch.object(module, "write_setting", AsyncMock()) as write,
        patch.object(module, "get_jev_settings", AsyncMock()),
    ):
        await module.update_jev_setting(
            AsyncMock(),
            JevToggleUpdate(enabled=True),
            admin_user_id=uuid4(),
            request=Request({"type": "http", "headers": []}),
        )
    write.assert_awaited_once()


async def test_global_switch_refuses_any_broken_enabled_slot() -> None:
    async def readiness(db, usage):
        return ("ready" if usage == JevUsage.MEETING_TEMPLATE else "missing_key", None)

    with (
        patch.object(
            module,
            "read_flags",
            AsyncMock(return_value={"global": False, **{usage.value: True for usage in JevUsage}}),
        ),
        patch.object(module, "read_configuration", side_effect=readiness),
        patch.object(module, "write_setting", AsyncMock()) as write,
        patch.object(module, "get_jev_settings", AsyncMock()),
    ):
        with pytest.raises(HTTPException):
            await module.update_jev_setting(
                AsyncMock(),
                JevToggleUpdate(enabled=True),
                admin_user_id=uuid4(),
                request=Request({"type": "http", "headers": []}),
            )
    write.assert_not_awaited()
