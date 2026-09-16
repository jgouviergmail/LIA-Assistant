"""Unit tests for the telephony connector router logic (P2.3, service mocked)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.router as rmod
from src.domains.telephony.schemas import (
    KeyValidationResult,
    PhoneNumberInfo,
    TelephonyActivateRequest,
    TelephonyKeyValidateRequest,
)


class _FakeService:
    def __init__(self, db) -> None:  # noqa: ANN001 — db unused in the fake
        self.db = db

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        return KeyValidationResult(is_valid=True, message="valid")

    async def list_numbers(self, api_key: str):
        return [
            PhoneNumberInfo(phone_number_id="pn_1", phone_number="+33600000000", provider="twilio")
        ]

    async def activate(self, **kwargs):
        return SimpleNamespace(
            connector_metadata={"agent_id": "ag_1", "agent_phone_number_id": "pn_1"}
        )

    async def deactivate(self, user_id) -> None:  # noqa: ANN001
        return None


def _user():
    return SimpleNamespace(id=uuid4(), full_name="Jean", email="jean@example.com", language="fr")


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch):
    monkeypatch.setattr(rmod, "TelephonyConnectorService", _FakeService)


@pytest.mark.unit
async def test_validate_key_endpoint_returns_numbers_when_valid():
    resp = await rmod.validate_key(
        TelephonyKeyValidateRequest(api_key="sk-testkey"), user=_user(), db=None
    )
    assert resp.is_valid is True
    assert len(resp.numbers) == 1
    assert resp.numbers[0].phone_number_id == "pn_1"


@pytest.mark.unit
async def test_activate_endpoint_maps_metadata_to_response():
    resp = await rmod.activate(
        TelephonyActivateRequest(
            api_key="sk-testkey", agent_phone_number_id="pn_1", webhook_secret="whsec"
        ),
        user=_user(),
        db=None,
    )
    assert resp.status == "active"
    assert resp.agent_id == "ag_1"
    assert resp.agent_phone_number_id == "pn_1"


@pytest.mark.unit
async def test_deactivate_endpoint_runs():
    # Should not raise; returns None (204).
    assert await rmod.deactivate(user=_user(), db=None) is None


# ---------------------------------------------------------------------------
# Identity routes (lot 1): the person's own number, verified
# ---------------------------------------------------------------------------


class _FakeIdentityService:
    def __init__(self, db) -> None:  # noqa: ANN001 — db unused in the fake
        self.db = db
        self.calls: list[tuple[str, object]] = []

    async def get_identity(self, user_id):  # noqa: ANN001
        from src.domains.telephony.identity import PhoneIdentity

        return PhoneIdentity(
            phone_number="+33612345678",
            verified=False,
            verified_at=None,
            rich_context_enabled=True,
        )

    async def set_number(self, user_id, raw, *, language="en"):  # noqa: ANN001
        from src.domains.telephony.identity import PhoneIdentity

        self.calls.append(("set_number", raw))
        return PhoneIdentity(
            phone_number="+33612345678",
            verified=False,
            verified_at=None,
            rich_context_enabled=True,
        )

    async def clear_number(self, user_id) -> None:  # noqa: ANN001
        self.calls.append(("clear_number", None))

    async def set_rich_context(self, user_id, enabled):  # noqa: ANN001
        from src.domains.telephony.identity import PhoneIdentity

        self.calls.append(("set_rich_context", enabled))
        return PhoneIdentity(
            phone_number="+33612345678",
            verified=True,
            verified_at=None,
            rich_context_enabled=enabled,
        )


@pytest.fixture
def _identity_service(monkeypatch):
    instances: list[_FakeIdentityService] = []

    def factory(db):  # noqa: ANN001
        service = _FakeIdentityService(db)
        instances.append(service)
        return service

    monkeypatch.setattr(rmod, "TelephonyIdentityService", factory)
    return instances


@pytest.mark.unit
async def test_get_identity_publishes_the_declared_number(_identity_service, _verification_service):
    from src.domains.telephony.schemas import TelephonyIdentityResponse

    resp = await rmod.get_identity(user=_user(), db=None)
    assert isinstance(resp, TelephonyIdentityResponse)
    assert resp.phone_number == "+33612345678"
    assert resp.verified is False
    assert resp.rich_context_enabled is True


@pytest.mark.unit
async def test_set_identity_number_passes_the_raw_input_and_the_language(_identity_service):
    from src.domains.telephony.schemas import TelephonyIdentityNumberRequest

    resp = await rmod.set_identity_number(
        TelephonyIdentityNumberRequest(phone_number="06 12 34 56 78"), user=_user(), db=None
    )
    assert resp.phone_number == "+33612345678"
    assert _identity_service[0].calls == [("set_number", "06 12 34 56 78")]


@pytest.mark.unit
async def test_clear_identity_number_runs(_identity_service):
    assert await rmod.clear_identity_number(user=_user(), db=None) is None
    assert _identity_service[0].calls == [("clear_number", None)]


@pytest.mark.unit
async def test_patch_identity_switches_rich_context(_identity_service):
    from src.domains.telephony.schemas import TelephonyIdentityUpdateRequest

    resp = await rmod.update_identity(
        TelephonyIdentityUpdateRequest(rich_context_enabled=False), user=_user(), db=None
    )
    assert resp.rich_context_enabled is False
    assert _identity_service[0].calls == [("set_rich_context", False)]


class _FakeVerification:
    def __init__(self, db, *, redis=None) -> None:  # noqa: ANN001
        self.db = db
        self.calls: list[tuple[str, object]] = []

    async def start(self, user_id, *, language, display_name):  # noqa: ANN001
        from src.domains.telephony.verification import VerificationStart

        self.calls.append(("start", (language, display_name)))
        return VerificationStart(call_id=uuid4(), expires_in_seconds=600)

    async def confirm(self, user_id, typed, *, language):  # noqa: ANN001
        from src.domains.telephony.identity import PhoneIdentity

        self.calls.append(("confirm", typed))
        return PhoneIdentity(
            phone_number="+33612345678", verified=True, verified_at=None, rich_context_enabled=True
        )

    async def pending(self, user_id) -> bool:  # noqa: ANN001
        return True


@pytest.fixture
def _verification_service(monkeypatch):
    instances: list[_FakeVerification] = []

    def factory(db, *, redis=None):  # noqa: ANN001
        service = _FakeVerification(db, redis=redis)
        instances.append(service)
        return service

    monkeypatch.setattr(rmod, "TelephonyVerificationService", factory)

    async def _redis():
        return object()

    monkeypatch.setattr(rmod, "get_redis_cache", _redis)
    return instances


@pytest.mark.unit
async def test_get_identity_says_whether_a_verification_is_pending(
    _identity_service, _verification_service
):
    resp = await rmod.get_identity(user=_user(), db=None)
    assert resp.verification_pending is True


@pytest.mark.unit
async def test_start_verification_places_the_call_in_the_users_language(_verification_service):
    resp = await rmod.start_identity_verification(user=_user(), db=None)
    assert resp.expires_in_seconds == 600
    assert resp.call_id is not None
    assert _verification_service[0].calls == [("start", ("fr", "Jean"))]


@pytest.mark.unit
async def test_confirm_verification_returns_the_verified_identity(_verification_service):
    from src.domains.telephony.schemas import TelephonyIdentityConfirmRequest

    resp = await rmod.confirm_identity_verification(
        TelephonyIdentityConfirmRequest(code="4719"), user=_user(), db=None
    )
    assert resp.verified is True
    assert _verification_service[0].calls == [("confirm", "4719")]
