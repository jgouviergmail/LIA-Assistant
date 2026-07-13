"""Unit tests for TelephonyService.initiate_call (P3.4), collaborators mocked.

No DB: the connector guard, repository, credentials, availability pre-fetch and
the ElevenLabs client are all faked. Verifies the orchestration contract — the
call_id reaches the vendor as a dynamic variable, the number is encrypted at
rest but sent in clear, the conversation id is persisted, and the one-active-call
guard short-circuits without dialing.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.service as svc
from src.core.security import decrypt_data
from src.domains.telephony.client import ElevenLabsAgentsError
from src.domains.telephony.models import PhoneCallStatus
from src.domains.telephony.schemas import OutboundCallResult
from src.domains.telephony.service import TelephonyService


class _FakeDB:
    def __init__(self, user: object) -> None:
        self._user = user
        self.committed = False
        self.rolled_back = False

    async def get(self, _model, _pk):  # noqa: ANN001 — signature mirror of AsyncSession.get
        return self._user

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    connector: object | None = "default",
    active_existing: object | None = None,
    conversation_id: str = "conv_1",
    client_error: bool = False,
) -> tuple[dict, object]:
    captured: dict = {}
    conn = (
        SimpleNamespace(connector_metadata={"agent_id": "ag_1", "agent_phone_number_id": "pn_1"})
        if connector == "default"
        else connector
    )

    class _FakeConnSvc:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def get_active(self, _user_id):
            return conn

    class _FakeConnectorService:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def get_api_key_credentials(self, _user_id, _ctype):
            return SimpleNamespace(api_key="sk-xxx")

    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def get_active_for_user(self, _user_id):
            return active_existing

        async def create(self, data: dict):
            captured["create_data"] = data
            return SimpleNamespace(
                id=uuid4(),
                elevenlabs_conversation_id=None,
                status=data["status"],
                error=None,
            )

        async def set_conversation_id(self, call_id, conversation_id):  # noqa: ANN001
            captured["conversation_id"] = conversation_id

        async def mark_dial_failed(self, call_id, error):  # noqa: ANN001
            captured["dial_failed_error"] = error

    async def _fake_availability(*_args, **_kwargs) -> str:
        return "BUSY: Tue 09:00 → 10:30"

    class _FakeClient:
        async def initiate_outbound_call(self, **kwargs) -> OutboundCallResult:
            captured["call_kwargs"] = kwargs
            if client_error:
                raise ElevenLabsAgentsError(502, "bad gateway")
            return OutboundCallResult(success=True, conversation_id=conversation_id, call_sid="CA1")

    monkeypatch.setattr(svc, "TelephonyConnectorService", _FakeConnSvc)
    monkeypatch.setattr(svc, "ConnectorService", _FakeConnectorService)
    monkeypatch.setattr(svc, "TelephonyRepository", _FakeRepo)
    monkeypatch.setattr(svc, "build_availability_summary", _fake_availability)
    return captured, (lambda _api_key: _FakeClient())


def _user() -> SimpleNamespace:
    return SimpleNamespace(full_name="Jean Test", email="jean@example.com", timezone="Europe/Paris")


async def _call(service: TelephonyService) -> object:
    return await service.initiate_call(
        user_id=uuid4(),
        callee_display="Marie",
        callee_phone="+33612345678",
        objective="Lui demander si elle est libre mardi",
        date_window="cette semaine",
        user_language="fr",
    )


@pytest.mark.unit
async def test_placed_call_wires_dynamic_variables_and_encrypts_phone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await _call(TelephonyService(db, client_factory=factory))

    assert result.status == "placed"
    kwargs = captured["call_kwargs"]
    # The vendor receives the plaintext number and our correlation call_id.
    assert kwargs["to_number"] == "+33612345678"
    assert kwargs["dynamic_variables"]["call_id"] == str(result.call_id)
    assert kwargs["dynamic_variables"]["availability_summary"] == "BUSY: Tue 09:00 → 10:30"
    assert kwargs["dynamic_variables"]["recording_disclosure"] == ""  # D-8
    # The stored number is encrypted at rest (never the plaintext).
    stored = captured["create_data"]["callee_phone"]
    assert stored != "+33612345678"
    assert decrypt_data(stored) == "+33612345678"
    assert captured["create_data"]["status"] == PhoneCallStatus.DIALING
    assert db.committed is True  # the dialing row is committed BEFORE the vendor call
    # The conversation id is persisted after the (out-of-transaction) dial succeeds.
    assert captured["conversation_id"] == "conv_1"


@pytest.mark.unit
async def test_already_active_short_circuits_without_dialing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(id=uuid4())
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch, active_existing=existing)
    result = await _call(TelephonyService(db, client_factory=factory))

    assert result.status == "already_active"
    assert result.call_id == existing.id
    assert "call_kwargs" not in captured  # never dialed


@pytest.mark.unit
async def test_not_configured_when_connector_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(_user())
    _captured, factory = _install_fakes(monkeypatch, connector=None)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "not_configured"


@pytest.mark.unit
async def test_client_error_marks_failed_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch, client_error=True)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "failed"
    assert db.committed is True  # the dialing row was committed before the failed dial
    assert "initiate_failed" in captured["dial_failed_error"]  # transitioned to failed
