"""Secure confirmations must not trust another owner, future dates or a lost write."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.config import settings
from src.core.session_dependencies import require_recent_step_up
from src.domains.auth.step_up_router import _record_step_up, step_up_status
from src.domains.users.models import User
from src.infrastructure.cache.session_store import UserSession

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fault", ["future", "naive", "foreign_owner"])
async def test_source_step_up_dependency_refuses_invalid_current_authority(fault: str) -> None:
    actor = User(id=uuid4(), is_active=True, hashed_password="configured")
    now = datetime.now(UTC)
    timestamp = (
        now + timedelta(minutes=1)
        if fault == "future"
        else now.replace(tzinfo=None) if fault == "naive" else now
    )
    session = UserSession(
        session_id="private-session",
        user_id=str(uuid4() if fault == "foreign_owner" else actor.id),
        step_up_at=timestamp,
    )
    store = AsyncMock()
    store.get_session.return_value = session
    with pytest.raises(HTTPException) as refusal:
        await require_recent_step_up(
            lia_session=session.session_id, user=actor, session_store=store
        )
    assert refusal.value.status_code == 403


async def test_source_status_does_not_offer_another_owners_freshness() -> None:
    actor = User(id=uuid4(), is_active=True, hashed_password="configured")
    session = UserSession(
        session_id="private-session", user_id=str(uuid4()), step_up_at=datetime.now(UTC)
    )
    store = AsyncMock()
    store.get_session.return_value = session
    with patch.object(settings, "mfa_enabled", False):
        result = await step_up_status(
            user=actor, db=AsyncMock(), store=store, lia_session=session.session_id
        )
    assert result.step_up_valid_until is None


async def test_verified_credential_does_not_claim_freshness_if_session_disappeared() -> None:
    store = AsyncMock()
    store.mark_step_up.return_value = False
    with pytest.raises(HTTPException) as refusal:
        await _record_step_up("private-session", store)
    assert refusal.value.status_code == 403
