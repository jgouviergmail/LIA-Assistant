"""Unit tests for the number verification — a code spoken, a code typed (lot 2).

Redis, the identity service and the dial path are faked at their doors; what
is exercised is the bookkeeping: a code drawn and stored with a TTL, a call
placed under the VERIFICATION mandate, a typed code compared in constant time
with a bounded number of tries, and the verification stamped only on a match.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ValidationError
from src.domains.telephony.errors import PhoneVerificationLockedError
from src.domains.telephony.identity import PhoneIdentity
from src.domains.telephony.models import CallKind
from src.domains.telephony.service import InitiateCallResult
from src.domains.telephony.verification import TelephonyVerificationService


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)
            self.ttls.pop(key, None)

    async def incr(self, key: str) -> int:
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def exists(self, key: str) -> int:
        return int(key in self.store)


class _FakeIdentity:
    def __init__(self, number: str | None) -> None:
        self.number = number
        self.verified = False

    async def get_identity(self, user_id):  # noqa: ANN001
        return PhoneIdentity(
            phone_number=self.number,
            verified=self.verified,
            verified_at=None,
            rich_context_enabled=True,
        )

    async def mark_verified(self, user_id, *, language: str = "en"):  # noqa: ANN001
        self.verified = True
        return await self.get_identity(user_id)


class _FakeCalls:
    def __init__(self, status: str = "placed") -> None:
        self.status = status
        self.kwargs: dict[str, Any] | None = None

    async def initiate_call(self, **kwargs: Any) -> InitiateCallResult:
        self.kwargs = kwargs
        return InitiateCallResult(status=self.status, call_id=uuid4())  # type: ignore[arg-type]


def _service(
    *, number: str | None = "+33612345678", call_status: str = "placed"
) -> tuple[TelephonyVerificationService, _FakeRedis, _FakeIdentity, _FakeCalls]:
    redis = _FakeRedis()
    identity = _FakeIdentity(number)
    calls = _FakeCalls(call_status)
    service = TelephonyVerificationService(
        SimpleNamespace(),  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        identity=identity,  # type: ignore[arg-type]
        calls=calls,  # type: ignore[arg-type]
    )
    return service, redis, identity, calls


@pytest.mark.unit
async def test_start_draws_a_code_stores_it_with_a_ttl_and_places_the_call() -> None:
    service, redis, _, calls = _service()
    user_id = uuid4()

    started = await service.start(user_id, language="fr", display_name="Alex")

    assert calls.kwargs is not None
    assert calls.kwargs["kind"] is CallKind.VERIFICATION
    assert calls.kwargs["callee_phone"] == "+33612345678"
    code = calls.kwargs["verification_code"]
    assert len(code) == settings.telephony_verification_code_length
    assert code.isdigit()
    (key,) = [k for k in redis.store if k.startswith("telephony_verify:")]
    assert redis.store[key] == f"+33612345678|{code}"
    assert redis.ttls[key] == settings.telephony_verification_code_ttl_seconds
    assert started.expires_in_seconds == settings.telephony_verification_code_ttl_seconds
    assert await service.pending(user_id) is True


@pytest.mark.unit
async def test_start_refuses_without_a_declared_number() -> None:
    service, redis, _, calls = _service(number=None)
    with pytest.raises(ResourceConflictError):
        await service.start(uuid4(), language="fr", display_name="Alex")
    assert calls.kwargs is None
    assert redis.store == {}


@pytest.mark.unit
async def test_start_forgets_the_code_when_the_call_is_not_placed() -> None:
    service, redis, _, _ = _service(call_status="already_active")
    with pytest.raises(ResourceConflictError):
        await service.start(uuid4(), language="fr", display_name="Alex")
    assert redis.store == {}


@pytest.mark.unit
async def test_confirm_with_the_right_code_marks_verified_and_forgets_the_code() -> None:
    service, redis, identity, calls = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    code = calls.kwargs["verification_code"]  # type: ignore[index]

    result = await service.confirm(user_id, code, language="fr")

    assert result.verified is True
    assert identity.verified is True
    assert redis.store == {}
    assert await service.pending(user_id) is False


@pytest.mark.unit
async def test_confirm_without_a_pending_verification_is_refused() -> None:
    service, _, identity, _ = _service()
    with pytest.raises(ResourceConflictError):
        await service.confirm(uuid4(), "0000", language="fr")
    assert identity.verified is False


@pytest.mark.unit
async def test_wrong_code_counts_an_attempt_and_keeps_the_code() -> None:
    service, redis, identity, calls = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    code = calls.kwargs["verification_code"]  # type: ignore[index]
    wrong = "0000" if code != "0000" else "1111"

    with pytest.raises(ValidationError):
        await service.confirm(user_id, wrong, language="fr")

    assert identity.verified is False
    assert await service.pending(user_id) is True
    (attempts_key,) = [k for k in redis.store if k.startswith("telephony_verify_attempts:")]
    assert redis.store[attempts_key] == "1"
    assert redis.ttls[attempts_key] == settings.telephony_verification_code_ttl_seconds


@pytest.mark.unit
async def test_too_many_wrong_codes_voids_the_verification() -> None:
    service, redis, identity, calls = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    code = calls.kwargs["verification_code"]  # type: ignore[index]
    wrong = "0000" if code != "0000" else "1111"

    for _ in range(settings.telephony_verification_max_attempts - 1):
        with pytest.raises(ValidationError):
            await service.confirm(user_id, wrong, language="fr")
    with pytest.raises(PhoneVerificationLockedError):
        await service.confirm(user_id, wrong, language="fr")

    assert redis.store == {}  # both keys gone: the code cannot be brute-forced further
    assert identity.verified is False
    # The right code is now useless too: a new call is needed.
    with pytest.raises(ResourceConflictError):
        await service.confirm(user_id, code, language="fr")


@pytest.mark.unit
async def test_a_typed_code_with_spaces_or_dashes_still_matches() -> None:
    service, _, identity, calls = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    code = calls.kwargs["verification_code"]  # type: ignore[index]

    await service.confirm(user_id, f" {code[:2]}-{code[2:]} ", language="fr")

    assert identity.verified is True


# ---------------------------------------------------------------------------
# The code is bound to the number it was spoken to (cold review, 2026-09-16)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_a_code_spoken_to_one_number_never_verifies_another() -> None:
    """Declare A, hear the code on A, switch to B, type the code: B must NOT be
    verified — the whole exception to the confirmation card rests on the line
    having been HEARD."""
    service, redis, identity, calls = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    code = calls.kwargs["verification_code"]  # type: ignore[index]

    identity.number = "+33699999999"  # the person changed the number meanwhile

    assert await service.pending(user_id) is False  # the page stops asking for a code
    with pytest.raises(ResourceConflictError):
        await service.confirm(user_id, code, language="fr")
    assert identity.verified is False
    assert redis.store == {}  # the stale code is gone for good


@pytest.mark.unit
async def test_a_cleared_number_voids_the_pending_code() -> None:
    service, redis, identity, _ = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    identity.number = None
    assert await service.pending(user_id) is False
    assert redis.store == {}


@pytest.mark.unit
async def test_a_non_ascii_code_is_wrong_not_an_error() -> None:
    """Arabic-Indic digits from a mobile keyboard must read as a wrong code,
    never as a 500 from the constant-time comparison."""
    service, _, identity, _ = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    with pytest.raises(ValidationError):
        await service.confirm(user_id, "٤٧١٩", language="fr")
    assert identity.verified is False


@pytest.mark.unit
async def test_verification_calls_are_bounded_per_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same hourly cap as the paid call tools: a session that could place
    unlimited verification calls could make LIA ring any number it declares."""
    import src.domains.telephony.verification as vmod

    class _Limiter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int, int]] = []
            self.allow = True

        async def acquire(self, key: str, max_calls: int, window_seconds: int) -> bool:
            self.calls.append((key, max_calls, window_seconds))
            return self.allow

    limiter = _Limiter()

    async def _get_limiter() -> _Limiter:
        return limiter

    monkeypatch.setattr(vmod, "get_rate_limiter", _get_limiter)
    service, redis, _, calls = _service()
    user_id = uuid4()

    await service.start(user_id, language="fr", display_name="Alex")
    key, max_calls, window = limiter.calls[0]
    assert key == f"telephony_verify_starts:{user_id}"
    assert max_calls == settings.telephony_rate_limit_per_hour and window == 3600
    first_code = calls.kwargs["verification_code"]  # type: ignore[index]

    limiter.allow = False
    calls.kwargs = None
    with pytest.raises(PhoneVerificationLockedError):
        await service.start(user_id, language="fr", display_name="Alex")
    assert calls.kwargs is None  # no call left
    # The code already spoken stays typeable: the refusal is about a NEW call.
    (key,) = [k for k in redis.store if k.startswith("telephony_verify:")]
    assert redis.store[key].endswith(first_code)


@pytest.mark.unit
async def test_a_refused_second_call_keeps_the_code_of_the_first() -> None:
    """« Call again » pressed while the first call still rings: the dial path
    refuses (one active call). The code being read on THAT call must stay
    typeable — forgetting it would strand the person mid-call."""
    service, redis, _, calls = _service()
    user_id = uuid4()
    await service.start(user_id, language="fr", display_name="Alex")
    first_code = calls.kwargs["verification_code"]  # type: ignore[index]

    calls.status = "already_active"
    with pytest.raises(ResourceConflictError):
        await service.start(user_id, language="fr", display_name="Alex")

    assert await service.pending(user_id) is True
    (key,) = [k for k in redis.store if k.startswith("telephony_verify:")]
    assert redis.store[key].endswith(first_code)
