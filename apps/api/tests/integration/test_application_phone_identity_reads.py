"""Phone identity consults actual owned state and Redis without spending or clearing codes."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.agents.application.phone_operations import read_phone_identity
from src.domains.telephony.identity_gateway import SavedPhoneIdentity
from src.domains.telephony.verification import TelephonyVerificationService
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.phone_identity import configure_phone_identity

pytestmark = pytest.mark.integration


async def test_phone_read_preserves_bound_code_and_reports_readability_and_effective_mode(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(settings, "telephony_callback_base_url", "http://localhost:8000")
    test_user.phone_number_encrypted = encrypt_data("+33612345678")
    test_user.phone_number_verified_at = datetime.now(UTC)
    test_user.phone_rich_context_enabled = False
    test_user.phone_call_mode = "delegated"
    await async_session.commit()
    redis = await get_redis_cache()
    key = TelephonyVerificationService._code_key(test_user.id)
    await redis.set(key, "+33612345678|654321", ex=120)
    previous = configure_phone_identity(SavedPhoneIdentity())
    try:
        available = await read_phone_identity(async_session, test_user.id)
        assert (
            available.number_status == "available"
            and available.identity.phone_number == "+33612345678"
        )
        assert available.identity.verification_pending is True
        assert (
            available.identity.call_mode == "delegated"
            and available.identity.call_mode_effective == "direct"
        )
        assert available.identity.rich_context_enabled is False
        assert available.identity.verified is True
        public = available.model_dump_json()
        assert "654321" not in public and test_user.phone_number_encrypted not in public
        test_user.phone_number_encrypted = encrypt_data("+33600000000")
        await async_session.commit()
        assert (
            await read_phone_identity(async_session, test_user.id)
        ).identity.verification_pending is False
        assert await redis.get(key) == "+33612345678|654321"
        test_user.phone_number_encrypted = "private-corrupt-ciphertext"
        await async_session.commit()
        unreadable = await read_phone_identity(async_session, test_user.id)
        assert unreadable.number_status == "unreadable" and unreadable.identity.phone_number is None
        assert "private-corrupt" not in unreadable.model_dump_json()
        assert await redis.get(key) == "+33612345678|654321"
    finally:
        configure_phone_identity(previous)
        await redis.delete(key)
