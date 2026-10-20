"""Single-device public seam never fans out or holds a database session."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.notifications.service import FCMNotificationService, FCMSendResult


@pytest.mark.asyncio
async def test_public_single_device_send_is_explicit_and_preserves_occurrence():
    service = FCMNotificationService(MagicMock())
    service._send_to_token = AsyncMock(return_value=FCMSendResult(success=True))
    occurrence = str(uuid4())
    result = await service.send_to_device(
        token="opaque",
        title="New SMS",
        body="Available",
        data={"type": "sms_received"},
        occurrence_key=occurrence,
    )
    assert result.success
    service._send_to_token.assert_awaited_once_with(
        token="opaque",
        title="New SMS",
        body="Available",
        data={"type": "sms_received"},
        occurrence_key=occurrence,
    )
    service.db.execute.assert_not_called()
