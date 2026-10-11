"""Real number/CAS and verification-code locks protect the declared line, not a stale read."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import ResourceConflictError
from src.core.security.utils import decrypt_data
from src.domains.telephony.identity import PhoneIdentity, TelephonyIdentityService
from src.domains.telephony.number_commands import phone_number_snapshot, update_phone_number
from src.domains.telephony.verification import TelephonyVerificationService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.phone_number_preferences import PhoneNumberWriteCheck

pytestmark = pytest.mark.integration


async def test_changed_number_during_real_user_lock_wait_cannot_be_marked_verified(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(id=uuid4(), email=f"number-lock-{uuid4()}@example.test", is_active=True)
    async with maker() as setup:
        setup.add(actor)
        await setup.commit()
        await TelephonyIdentityService(setup).set_number(actor.id, "+33612345678")
    redis = await get_redis_cache()
    key = TelephonyVerificationService._code_key(actor.id)
    attempts_key = TelephonyVerificationService._attempts_key(actor.id)
    await redis.set(key, "+33612345678|123456", ex=60)
    at_lock = asyncio.Event()

    async def confirm() -> None:
        async with maker() as db:
            users = UserRepository(db)
            original = users.get_by_id_for_preference_update

            async def observed_lock(user_id: UUID) -> User | None:
                at_lock.set()
                return await original(user_id)

            monkeypatch.setattr(users, "get_by_id_for_preference_update", observed_lock)
            identity = TelephonyIdentityService(db, users=users)
            await TelephonyVerificationService(db, redis=redis, identity=identity).confirm(
                actor.id, "123456", language="fr"
            )

    try:
        async with maker() as blocker:
            await blocker.scalar(select(User).where(User.id == actor.id).with_for_update())
            confirming = asyncio.create_task(confirm())
            try:
                await asyncio.wait_for(at_lock.wait(), timeout=5)
                await asyncio.sleep(0.05)
                assert not confirming.done()
                await TelephonyIdentityService(blocker).set_number(actor.id, "+33698765432")
                with pytest.raises(ResourceConflictError):
                    await asyncio.wait_for(confirming, timeout=5)
            finally:
                if not confirming.done():
                    confirming.cancel()
                await asyncio.gather(confirming, return_exceptions=True)
        async with maker() as verify:
            saved = await verify.get(User, actor.id)
            assert saved is not None
            assert decrypt_data(saved.phone_number_encrypted) == "+33698765432"
            assert saved.phone_number_verified_at is None
        assert await redis.get(key) == "+33612345678|123456"
    finally:
        await redis.delete(key, attempts_key)
        async with maker() as cleanup:
            await cleanup.execute(delete(User).where(User.id == actor.id))
            await cleanup.commit()


async def test_source_and_native_number_owner_share_encryption_noop_and_stale_fences(
    async_session: AsyncSession, test_user: User
) -> None:
    source = TelephonyIdentityService(async_session)
    await source.set_number(test_user.id, "+33612345678")
    await async_session.refresh(test_user)
    saved_cipher = test_user.phone_number_encrypted
    snapshot = phone_number_snapshot(test_user)
    receipt = PreferenceWriteReceipt()
    await update_phone_number(
        async_session, test_user.id, "+33612345678", expected=snapshot, receipt=receipt
    )
    assert receipt.committed and receipt.no_op
    await async_session.refresh(test_user)
    assert test_user.phone_number_encrypted == saved_cipher
    await source.set_number(test_user.id, "+33698765432")
    with pytest.raises(ResourceConflictError):
        await update_phone_number(async_session, test_user.id, None, expected=snapshot)
    await async_session.refresh(test_user)
    assert decrypt_data(test_user.phone_number_encrypted) == "+33698765432"


@pytest.mark.parametrize("replacement", [None, "+33612345678|999999"])
async def test_actual_redis_code_replacement_while_waiting_for_identity_lock_is_refused(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str | None,
) -> None:
    identity = TelephonyIdentityService(async_session)
    await identity.set_number(test_user.id, "+33612345678")
    redis = await get_redis_cache()
    verification = TelephonyVerificationService(async_session, redis=redis, identity=identity)
    key = verification._code_key(test_user.id)
    attempts_key = verification._attempts_key(test_user.id)
    await redis.set(key, "+33612345678|123456", ex=60)
    original = identity.mark_verified

    async def change_before_lock(
        user_id: UUID,
        *,
        language: str | None = None,
        expected_number: str | None = None,
        check: PhoneNumberWriteCheck | None = None,
    ) -> PhoneIdentity:
        if replacement is None:
            await redis.delete(key)
        else:
            await redis.set(key, replacement, ex=60)
        return await original(
            user_id, language=language, expected_number=expected_number, check=check
        )

    monkeypatch.setattr(identity, "mark_verified", change_before_lock)
    try:
        with pytest.raises(ResourceConflictError):
            await verification.confirm(test_user.id, "123456", language="fr")
        await async_session.refresh(test_user)
        assert test_user.phone_number_verified_at is None
        stored = await redis.get(key)
        assert stored == replacement
    finally:
        await redis.delete(key, attempts_key)


async def test_actual_redis_code_is_consumed_once_and_verified_state_is_committed(
    async_session: AsyncSession, test_user: User
) -> None:
    identity = TelephonyIdentityService(async_session)
    await identity.set_number(test_user.id, "+33612345678")
    redis = await get_redis_cache()
    verification = TelephonyVerificationService(async_session, redis=redis, identity=identity)
    key = verification._code_key(test_user.id)
    attempts_key = verification._attempts_key(test_user.id)
    await redis.set(key, "+33612345678|123456", ex=60)
    try:
        result = await verification.confirm(test_user.id, "123456", language="fr")
        assert result.verified is True
        assert await redis.exists(key, attempts_key) == 0
        with pytest.raises(ResourceConflictError):
            await verification.confirm(test_user.id, "123456", language="fr")
        await async_session.refresh(test_user)
        assert test_user.phone_number_verified_at is not None
    finally:
        await redis.delete(key, attempts_key)


@pytest.mark.parametrize("stale_number", [True, False])
async def test_actual_redis_replacement_survives_stale_read_without_counter_debit(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    stale_number: bool,
) -> None:
    identity = TelephonyIdentityService(async_session)
    await identity.set_number(test_user.id, "+33612345678")
    redis = await get_redis_cache()
    service = TelephonyVerificationService(async_session, redis=redis, identity=identity)
    key, attempts = service._code_key(test_user.id), service._attempts_key(test_user.id)
    await redis.set(key, f"{'+33600000000' if stale_number else '+33612345678'}|123456", ex=60)
    original = identity.get_identity

    async def replace_during_identity_read(user_id: UUID) -> PhoneIdentity:
        await redis.set(key, "+33612345678|999999", ex=60)
        await redis.set(attempts, "0", ex=60)
        return await original(user_id)

    monkeypatch.setattr(identity, "get_identity", replace_during_identity_read)
    try:
        if stale_number:
            assert await service.pending(test_user.id) is False
        else:
            with pytest.raises(ResourceConflictError):
                await service.confirm(test_user.id, "123456", language="fr")
        assert await redis.get(key) == "+33612345678|999999"
        assert await redis.get(attempts) == "0"
        await async_session.refresh(test_user)
        assert test_user.phone_number_verified_at is None
    finally:
        await redis.delete(key, attempts)
