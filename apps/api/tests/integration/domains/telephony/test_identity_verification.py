"""The person's number, declared and verified — on real PostgreSQL and Redis (ADR-290).

The unit tests fake the repository and the cache; this file drives the two
services on the real ``users`` row and the real Redis keys, because the
guarantee at stake — an owner call skips its confirmation card ONLY on a
line LIA heard the person answer — rests on what is actually persisted:
the encrypted number, the verification stamp, and the code bound to the
number it was spoken to.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.i18n_api_messages import APIMessages
from src.domains.telephony.identity import TelephonyIdentityService
from src.domains.telephony.models import CallKind
from src.domains.telephony.service import InitiateCallResult
from src.domains.telephony.verification import TelephonyVerificationService
from src.infrastructure.cache.redis import get_redis_cache


class _FakeCalls:
    """The dial path, faked at its door: the code that would be read aloud."""

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    async def initiate_call(self, **kwargs: Any) -> InitiateCallResult:
        assert kwargs["kind"] is CallKind.VERIFICATION
        self.spoken.append((kwargs["callee_phone"], kwargs["verification_code"]))
        return InitiateCallResult(status="placed", call_id=uuid4())


@pytest.fixture
async def _services(async_session, test_user, monkeypatch):  # noqa: ANN001, ANN202
    # National numbers below are French; CI has no root .env to say so.
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33")
    redis = await get_redis_cache()
    identity = TelephonyIdentityService(async_session)
    calls = _FakeCalls()
    verification = TelephonyVerificationService(
        async_session, redis=redis, identity=identity, calls=calls
    )
    yield identity, verification, calls, test_user
    await redis.delete(
        f"telephony_verify:{test_user.id}",
        f"telephony_verify_attempts:{test_user.id}",
        f"telephony_verify_starts:{test_user.id}",
    )


@pytest.mark.integration
async def test_the_number_is_stored_encrypted_and_verified_by_the_spoken_code(
    _services, async_session
) -> None:
    identity, verification, calls, user = _services

    declared = await identity.set_number(user.id, "06 12 34 56 78", language="fr")
    assert declared.phone_number == "+33612345678" and declared.verified is False
    await async_session.refresh(user)
    assert user.phone_number_encrypted and "+33612345678" not in user.phone_number_encrypted

    started = await verification.start(user.id, language="fr", display_name="Alex")
    assert started.call_id is not None
    ((number, code),) = calls.spoken
    assert number == "+33612345678"
    assert await verification.pending(user.id) is True

    verified = await verification.confirm(user.id, f"{code[:2]} {code[2:]}", language="fr")
    assert verified.verified is True and verified.verified_at is not None
    assert await verification.pending(user.id) is False
    assert await identity.verified_number(user.id) == "+33612345678"


@pytest.mark.integration
async def test_a_code_heard_on_one_number_cannot_verify_another(_services) -> None:
    """The cold-review defect: declare A, hear the code on A, switch to B, type
    the code — B stays unverified, on the real row and the real key."""
    identity, verification, calls, user = _services

    await identity.set_number(user.id, "+33612345678", language="fr")
    await verification.start(user.id, language="fr", display_name="Alex")
    ((_, code),) = calls.spoken

    switched = await identity.set_number(user.id, "+33699999999", language="fr")
    assert switched.verified is False
    assert await verification.pending(user.id) is False
    with pytest.raises(ResourceConflictError) as refused:
        await verification.confirm(user.id, code, language="fr")
    assert refused.value.detail == APIMessages.phone_verification_not_pending("fr")
    assert await identity.verified_number(user.id) is None


@pytest.mark.integration
async def test_redeclaring_the_same_number_keeps_the_verification(_services) -> None:
    identity, verification, calls, user = _services
    await identity.set_number(user.id, "+33612345678", language="fr")
    await verification.start(user.id, language="fr", display_name="Alex")
    ((_, code),) = calls.spoken
    await verification.confirm(user.id, code, language="fr")

    again = await identity.set_number(user.id, "0612345678", language="fr")
    assert again.verified is True

    changed = await identity.set_number(user.id, "0699999999", language="fr")
    assert changed.verified is False and changed.phone_number == "+33699999999"


@pytest.mark.integration
async def test_clearing_the_number_forgets_everything(_services) -> None:
    identity, verification, _, user = _services
    await identity.set_number(user.id, "+33612345678", language="fr")
    await verification.start(user.id, language="fr", display_name="Alex")

    await identity.clear_number(user.id)
    assert (await identity.get_identity(user.id)).phone_number is None
    assert await verification.pending(user.id) is False
    with pytest.raises(ResourceConflictError):
        await verification.start(user.id, language="fr", display_name="Alex")
