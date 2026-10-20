"""An unavailable authority must not be confused with withdrawn permission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.sms.notifications import notice_for

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_authority_outage_does_not_permanently_cancel_a_notice(monkeypatch):
    db = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(is_active=True, deleted_at=None, sms_preferences=None)
        )
    )
    monkeypatch.setattr(
        "src.domains.sms.notifications.require_capability_fresh",
        AsyncMock(side_effect=AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})),
    )
    with pytest.raises(AuthorizationError):
        await notice_for(db, uuid4(), uuid4())


@pytest.mark.asyncio
async def test_explicit_disabled_capability_refuses_the_notice(monkeypatch):
    db = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(is_active=True, deleted_at=None, sms_preferences=None)
        )
    )
    monkeypatch.setattr(
        "src.domains.sms.notifications.require_capability_fresh",
        AsyncMock(side_effect=AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})),
    )
    assert await notice_for(db, uuid4(), uuid4()) is None
