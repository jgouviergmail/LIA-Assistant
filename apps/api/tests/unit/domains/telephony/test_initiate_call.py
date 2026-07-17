"""Unit tests for TelephonyService.initiate_call (P3.4), collaborators mocked.

No DB: the connector guard, repository, credentials, availability pre-fetch and
the ElevenLabs client are all faked. Verifies the orchestration contract — the
call_id reaches the vendor as a dynamic variable, the number is encrypted at
rest but sent in clear, the conversation id is persisted, and the one-active-call
guard short-circuits without dialing.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    sync_error: bool = False,
    vendor_conversation_status: str | object = "in-progress",
    close_zombie_result: bool = True,
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

        async def close_zombie(self, call_id, error):  # noqa: ANN001
            captured["zombie_closed"] = (call_id, error)
            return close_zombie_result

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

        async def update_agent(self, agent_id, **kwargs) -> None:  # noqa: ANN001
            if sync_error:
                raise ElevenLabsAgentsError(500, "sync boom")
            captured["updated_agent"] = agent_id
            captured["update_kwargs"] = kwargs

        async def get_conversation_status(self, conversation_id: str) -> str:
            captured["probed_conversation"] = conversation_id
            if isinstance(vendor_conversation_status, Exception):
                raise vendor_conversation_status
            return str(vendor_conversation_status)

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
    # Temporal anchor for the voice agent: localized, non-empty, current year —
    # without it a callee's "tomorrow" is unresolvable on the call.
    current_dt = kwargs["dynamic_variables"]["current_datetime"]
    assert str(datetime.now(UTC).year) in current_dt
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
    existing = _zombie(minutes_old=1)  # young + vendor default "in-progress" = live
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


@pytest.mark.unit
async def test_drifted_agent_config_is_synced_before_dialing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No stored fingerprint (or a stale one) → the agent is PATCHed in place
    and the new fingerprint lands in connector_metadata — the deactivate/
    reactivate cycle is no longer needed for prompt/settings changes."""
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)  # default connector: no hash stored
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["updated_agent"] == "ag_1"
    assert captured["update_kwargs"]["system_prompt"]  # real prompt content sent


@pytest.mark.unit
async def test_matching_fingerprint_skips_the_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import settings as app_settings
    from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config

    user = _user()
    from src.core.user_display import resolve_user_display_name

    cfg = build_agent_config("fr", resolve_user_display_name(user.full_name, user.email))
    current = agent_config_fingerprint(
        cfg,
        llm_model=app_settings.telephony_agent_llm_model or None,
        tts_model_id=app_settings.telephony_agent_tts_model_id,
        voice_id=app_settings.telephony_agent_voice_id or None,
        audio_format=app_settings.telephony_agent_audio_format or None,
        max_duration_seconds=app_settings.telephony_max_call_duration_seconds,
    )
    connector = SimpleNamespace(
        connector_metadata={
            "agent_id": "ag_1",
            "agent_phone_number_id": "pn_1",
            "agent_config_hash": current,
        }
    )
    db = _FakeDB(user)
    captured, factory = _install_fakes(monkeypatch, connector=connector)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert "updated_agent" not in captured  # no vendor sync when nothing drifted


@pytest.mark.unit
async def test_sync_failure_never_blocks_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch, sync_error=True)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"  # best-effort: the call went out on the old config
    assert "call_kwargs" in captured


def _zombie(
    *, minutes_old: int = 0, seconds_old: int = 0, conversation_id: str | None = "conv_old"
) -> SimpleNamespace:
    from datetime import UTC, datetime, timedelta

    return SimpleNamespace(
        id=uuid4(),
        elevenlabs_conversation_id=conversation_id,
        initiated_at=datetime.now(UTC) - timedelta(minutes=minutes_old, seconds=seconds_old),
    )


@pytest.mark.unit
async def test_guard_self_heals_when_vendor_says_conversation_ended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real incident: a DIALING row whose webhook never arrived blocked the next
    call until the reaper's 5-minute tick (refusal observed 5 s before the
    sweep). The guard now probes the vendor and closes the row itself."""
    zombie = _zombie(minutes_old=2)  # young row — only the vendor probe can clear it
    db = _FakeDB(_user())
    captured, factory = _install_fakes(
        monkeypatch, active_existing=zombie, vendor_conversation_status="done"
    )
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["probed_conversation"] == "conv_old"
    assert captured["zombie_closed"] == (zombie.id, "ended_no_webhook")


@pytest.mark.unit
async def test_guard_keeps_refusing_a_genuinely_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zombie = _zombie(minutes_old=2)
    db = _FakeDB(_user())
    captured, factory = _install_fakes(
        monkeypatch, active_existing=zombie, vendor_conversation_status="in-progress"
    )
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "already_active"
    assert "zombie_closed" not in captured
    assert "call_kwargs" not in captured  # never dialed


@pytest.mark.unit
async def test_guard_falls_back_to_stale_threshold_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings as app_settings

    stale_minutes = app_settings.telephony_stale_call_timeout_minutes + 1
    zombie = _zombie(minutes_old=stale_minutes)
    db = _FakeDB(_user())
    captured, factory = _install_fakes(
        monkeypatch,
        active_existing=zombie,
        vendor_conversation_status=ElevenLabsAgentsError(503, "vendor down"),
    )
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["zombie_closed"] == (zombie.id, "stale_no_webhook")


@pytest.mark.unit
async def test_guard_closes_gone_conversation_past_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real incident: a mid-call connector deactivation deleted the vendor agent
    (and its conversation) — the probe 404'd and the row blocked calls for the
    full 15-minute stale threshold. A 404 past the grace window is terminal."""
    from src.core.config import settings as app_settings

    grace = app_settings.telephony_probe_not_found_grace_seconds
    zombie = _zombie(seconds_old=grace + 30)
    db = _FakeDB(_user())
    captured, factory = _install_fakes(
        monkeypatch,
        active_existing=zombie,
        vendor_conversation_status=ElevenLabsAgentsError(404, "document_not_found"),
    )
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["zombie_closed"] == (zombie.id, "conversation_gone")


@pytest.mark.unit
async def test_guard_keeps_refusing_young_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 404 within the grace window must NOT close the row: a freshly dialed
    conversation may not be readable vendor-side yet, and closing a LIVE call
    would allow a concurrent second one (the exact F12 violation)."""
    from src.core.config import settings as app_settings

    grace = app_settings.telephony_probe_not_found_grace_seconds
    zombie = _zombie(seconds_old=max(grace - 30, 1))
    db = _FakeDB(_user())
    captured, factory = _install_fakes(
        monkeypatch,
        active_existing=zombie,
        vendor_conversation_status=ElevenLabsAgentsError(404, "document_not_found"),
    )
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "already_active"
    assert "zombie_closed" not in captured
    assert "call_kwargs" not in captured  # never dialed


@pytest.mark.unit
async def test_guard_refuses_when_close_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    """close_zombie returning False (e.g. a RECEIVED row the return reaper owns)
    keeps the already_active refusal — the return is seconds from landing."""
    zombie = _zombie(minutes_old=2)
    db = _FakeDB(_user())
    captured, factory = _install_fakes(
        monkeypatch,
        active_existing=zombie,
        vendor_conversation_status="done",
        close_zombie_result=False,
    )
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "already_active"
    assert "call_kwargs" not in captured
