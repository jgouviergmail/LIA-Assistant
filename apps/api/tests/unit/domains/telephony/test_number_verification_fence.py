"""A code read on line A cannot authorize line B after a number-change race."""

from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.telephony.errors import PhoneVerificationLockedError
from src.domains.telephony.verification import TelephonyVerificationService
from tests.unit.domains.telephony.test_identity_service import _service, _user
from tests.unit.domains.telephony.test_verification_service import _FakeRedis
from tests.unit.domains.telephony.test_verification_service import _service as verification_service

pytestmark = pytest.mark.unit


async def test_pending_cleanup_cannot_delete_a_new_code_created_during_identity_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, redis, identity, _ = verification_service()
    actor_id = uuid4()
    key = service._code_key(actor_id)
    redis.store[key] = "+33600000000|123456"
    original = identity.get_identity

    async def replace_during_read(user_id):
        redis.store[key] = "+33612345678|999999"
        return await original(user_id)

    monkeypatch.setattr(identity, "get_identity", replace_during_read)
    assert await service.pending(actor_id) is False
    assert redis.store.get(key) == "+33612345678|999999"


async def test_old_attempt_limit_cannot_delete_a_replacement_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, redis, _, _ = verification_service()
    actor_id = uuid4()
    key = service._code_key(actor_id)
    attempts = service._attempts_key(actor_id)
    redis.store[key] = "+33612345678|123456"
    redis.store[attempts] = str(settings.telephony_verification_max_attempts)
    original = redis.incr

    async def replace_during_attempt(counter_key: str) -> int:
        count = await original(counter_key)
        redis.store[key] = "+33612345678|999999"
        redis.store[attempts] = "0"
        return count

    monkeypatch.setattr(redis, "incr", replace_during_attempt)
    with pytest.raises(PhoneVerificationLockedError):
        await service.confirm(actor_id, "000000", language="fr")
    assert redis.store.get(key) == "+33612345678|999999"
    assert redis.store.get(attempts) == "0"


async def test_replaced_code_before_attempt_does_not_charge_its_new_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, redis, identity, _ = verification_service()
    actor_id = uuid4()
    key = service._code_key(actor_id)
    attempts_key = service._attempts_key(actor_id)
    redis.store[key] = "+33612345678|123456"
    original = identity.get_identity

    async def replace_during_read(user_id):
        redis.store[key] = "+33612345678|999999"
        redis.store[attempts_key] = "0"
        return await original(user_id)

    monkeypatch.setattr(identity, "get_identity", replace_during_read)
    with pytest.raises(ResourceConflictError):
        await service.confirm(actor_id, "123456", language="fr")
    assert redis.store.get(key) == "+33612345678|999999"
    assert redis.store.get(attempts_key) == "0"


async def test_number_change_after_code_read_cannot_mark_the_new_line_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _user(phone_number_encrypted=encrypt_data("+33612345678"))
    identity, users, db = _service(actor)
    redis = _FakeRedis()
    verification = TelephonyVerificationService(db, redis=redis, identity=identity)
    code_key = verification._code_key(actor.id)
    redis.store[code_key] = "+33612345678|123456"
    original_incr = redis.incr

    async def change_number_after_validated_code(key: str) -> int:
        actor.phone_number_encrypted = encrypt_data("+33698765432")
        return await original_incr(key)

    monkeypatch.setattr(redis, "incr", change_number_after_validated_code)
    with pytest.raises(ResourceConflictError):
        await verification.confirm(actor.id, "123456", language="fr")
    assert actor.phone_number_verified_at is None
    assert users.updates == [] and db.commits == 0


@pytest.mark.parametrize("replacement", [None, "+33612345678|999999"])
async def test_expired_or_replaced_code_cannot_be_spent_after_a_lock_wait(
    monkeypatch: pytest.MonkeyPatch, replacement: str | None
) -> None:
    actor = _user(phone_number_encrypted=encrypt_data("+33612345678"))
    identity, users, db = _service(actor)
    redis = _FakeRedis()
    verification = TelephonyVerificationService(db, redis=redis, identity=identity)
    code_key = verification._code_key(actor.id)
    redis.store[code_key] = "+33612345678|123456"
    original_incr = redis.incr

    async def invalidate_after_read(key: str) -> int:
        if replacement is None:
            redis.store.pop(code_key, None)
        else:
            redis.store[code_key] = replacement
        return await original_incr(key)

    monkeypatch.setattr(redis, "incr", invalidate_after_read)
    with pytest.raises(ResourceConflictError):
        await verification.confirm(actor.id, "123456", language="fr")
    assert actor.phone_number_verified_at is None and users.updates == []
    assert redis.store.get(code_key) == replacement
