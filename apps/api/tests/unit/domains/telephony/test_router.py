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

    async def set_call_mode(self, user_id, mode, *, language):  # noqa: ANN001
        from src.domains.telephony.identity import PhoneIdentity

        self.calls.append(("set_call_mode", mode))
        return PhoneIdentity(
            phone_number="+33612345678",
            verified=True,
            verified_at=None,
            rich_context_enabled=True,
            call_mode=mode,
            live_available=False,
            live_unavailable_reason="callback_not_public",
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


@pytest.mark.unit
async def test_patch_identity_chooses_the_call_mode_and_publishes_what_a_call_will_run(
    _identity_service,
):
    """ADR-301: the choice is stored; the EFFECTIVE mode and the reason travel with it."""
    from src.domains.telephony.schemas import TelephonyIdentityUpdateRequest

    resp = await rmod.update_identity(
        TelephonyIdentityUpdateRequest(call_mode="delegated"), user=_user(), db=None
    )
    assert resp.call_mode == "delegated"
    assert resp.live_available is False
    assert resp.live_unavailable_reason == "callback_not_public"
    assert resp.call_mode_effective == "direct"
    assert _identity_service[0].calls == [("set_call_mode", "delegated")]


@pytest.mark.unit
async def test_the_calls_list_sums_a_live_calls_delegated_runs(monkeypatch):
    """A Live call's bill is the SUM of its delegated turns and its own run —
    read in two batches for the page, never one query per call (ADR-301)."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from src.domains.telephony.models import CallKind, PhoneCallStatus

    live_id, direct_id = uuid4(), uuid4()

    def _row(call_id, kind, mode):  # noqa: ANN001
        return SimpleNamespace(
            id=call_id,
            callee_display="Alex",
            objective="o",
            status=PhoneCallStatus.COMPLETED,
            outcome=None,
            summary=None,
            debrief=None,
            structured_data=None,
            call_seconds=None,
            created_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
            completed_at=None,
            call_kind=kind,
            call_mode=mode,
            relay_outcome=None,
        )

    class _Repo:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def list_recent_for_user(self, _user_id, *, limit):  # noqa: ANN001
            return [
                _row(live_id, CallKind.SELF, "delegated"),
                _row(direct_id, CallKind.SELF, "direct"),
            ]

    class _Conversations:
        async def get_active_conversation(self, _user_id, _db):  # noqa: ANN001
            return SimpleNamespace(id=uuid4())

    async def _by_key(_db, *, conversation_id, live_session_ids):  # noqa: ANN001
        assert live_session_ids == [f"phone_call_{live_id.hex}"]
        return {f"phone_call_{live_id.hex}": ["run_1", "run_2"]}

    def _summary(prompt, cost):  # noqa: ANN001
        return SimpleNamespace(
            total_prompt_tokens=prompt,
            total_completion_tokens=1,
            total_cached_tokens=0,
            billed_cost_eur=Decimal(cost),
            google_api_requests=0,
        )

    class _Chat:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_token_summaries_by_run_ids(self, run_ids):  # noqa: ANN001
            assert set(run_ids) == {
                f"phone_call_{live_id.hex}",
                f"phone_call_{direct_id.hex}",
                "run_1",
                "run_2",
            }
            return {
                "run_1": _summary(100, "0.10"),
                "run_2": _summary(50, "0.05"),
                f"phone_call_{direct_id.hex}": _summary(7, "0.01"),
            }

    monkeypatch.setattr(rmod, "TelephonyRepository", _Repo)
    monkeypatch.setattr(rmod, "ConversationService", _Conversations)
    monkeypatch.setattr(rmod, "session_run_ids_by_key", _by_key)
    monkeypatch.setattr(rmod, "ChatRepository", _Chat)

    listed = await rmod.list_calls(user=_user(), db=None, limit=20)
    live, direct = listed
    assert live.call_mode == "delegated"
    assert live.usage is not None and live.usage.tokens_in == 150
    assert live.usage.cost_eur == 0.15
    assert direct.usage is not None and direct.usage.tokens_in == 7


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
