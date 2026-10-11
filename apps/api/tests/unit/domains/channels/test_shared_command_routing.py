"""HTTP channel mutations cannot retain the old unlocked mutation path."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.channels.service import ChannelService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("delete", [False, True])
async def test_http_mutation_uses_the_current_owner_command(delete: bool) -> None:
    db = AsyncMock(spec=AsyncSession)
    actor_id, binding_id = uuid4(), uuid4()
    method = "unlink_owned_channel_binding" if delete else "toggle_owned_channel_binding"
    command = AsyncMock()
    with patch(f"src.domains.channels.preference_commands.{method}", command):
        if delete:
            await ChannelService(db).delete_binding(binding_id, actor_id)
        else:
            result = await ChannelService(db).toggle_binding(binding_id, actor_id)
            assert result is command.return_value
    command.assert_awaited_once_with(db, actor_id, binding_id)
