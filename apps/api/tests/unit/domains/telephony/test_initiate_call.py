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
from src.domains.telephony.availability import AvailabilityRead
from src.domains.telephony.client import ElevenLabsAgentsError
from src.domains.telephony.models import CallKind, PhoneCallStatus
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
    conversation_id: str | None = "conv_1",
    vendor_success: bool = True,
    vendor_message: str | None = None,
    client_error: bool = False,
    client_auth_error: bool = False,
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
    captured["connector"] = conn

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

    async def _fake_availability(*_args, **_kwargs) -> AvailabilityRead:
        captured["availability_read"] = True
        return AvailabilityRead(summary="BUSY: Tue 09:00 → 10:30", opened=True, failed=False)

    def _fake_record(**kwargs) -> None:  # noqa: ANN003
        captured.setdefault("consultations", []).append(kwargs)

    class _FakeClient:
        async def initiate_outbound_call(self, **kwargs) -> OutboundCallResult:
            captured["call_kwargs"] = kwargs
            if client_auth_error:
                raise ElevenLabsAgentsError(401, "invalid api key", auth_error=True)
            if client_error:
                raise ElevenLabsAgentsError(502, "bad gateway")
            return OutboundCallResult(
                success=vendor_success,
                conversation_id=conversation_id,
                call_sid="CA1",
                message=vendor_message,
            )

        async def update_agent(self, agent_id, **kwargs) -> None:  # noqa: ANN001
            if sync_error:
                raise ElevenLabsAgentsError(500, "sync boom")
            captured["updated_agent"] = agent_id
            captured["update_kwargs"] = kwargs

        async def set_agent_tool_ids(self, agent_id, tool_ids) -> None:  # noqa: ANN001
            captured.setdefault("tool_ids_patches", []).append((agent_id, list(tool_ids)))

        async def get_conversation_status(self, conversation_id: str) -> str:
            captured["probed_conversation"] = conversation_id
            if isinstance(vendor_conversation_status, Exception):
                raise vendor_conversation_status
            return str(vendor_conversation_status)

    monkeypatch.setattr(svc, "TelephonyConnectorService", _FakeConnSvc)
    monkeypatch.setattr(svc, "ConnectorService", _FakeConnectorService)
    monkeypatch.setattr(svc, "TelephonyRepository", _FakeRepo)
    monkeypatch.setattr(svc, "build_availability", _fake_availability)
    monkeypatch.setattr(svc, "record_surface_consultations", _fake_record)
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
async def test_the_dial_reads_the_assistant_s_personality_for_both_mandates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lot 9: the personality the person configured for LIA travels with every
    call — a dynamic variable for the baked third-party agent, the rendered
    block for the owner override — read at the dial, best-effort."""

    class _Personalities:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_prompt_instruction_for_user(self, _user_id):  # noqa: ANN001
            return "Warm and playful."

    monkeypatch.setattr(svc, "PersonalityService", _Personalities)
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["call_kwargs"]["dynamic_variables"]["personality_profile"] == (
        "Warm and playful."
    )

    captured, factory = _install_fakes(monkeypatch)
    result = await _owner_call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    override = captured["call_kwargs"]["conversation_config_override"]
    assert "Warm and playful." in override["agent"]["prompt"]["prompt"]


@pytest.mark.unit
async def test_a_personality_that_cannot_be_read_never_blocks_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Broken:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_prompt_instruction_for_user(self, _user_id):  # noqa: ANN001
            raise RuntimeError("personalities down")

    monkeypatch.setattr(svc, "PersonalityService", _Broken)
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["call_kwargs"]["dynamic_variables"]["personality_profile"] == ""


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
async def test_vendor_auth_error_maps_to_auth_failed_not_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authentication rejection is NOT transient: telling the user to
    "try again in a moment" is a lie — nothing changes until the connector
    key is replaced. Prod 2026-08-15: ElevenLabs stopped accepting the stored
    legacy credential ("API key ID used as API key") and every call died
    behind the generic retry message."""
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch, client_auth_error=True)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "auth_failed"
    assert db.committed is True
    assert "initiate_auth_failed" in captured["dial_failed_error"]


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
    from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config

    user = _user()
    from src.core.user_display import resolve_user_display_name

    cfg = build_agent_config("fr", resolve_user_display_name(user.full_name, user.email))
    current = agent_config_fingerprint(cfg)
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


# =============================================================================
# Vendor refusal — the 200 that means "no" (fix: silent DIALING zombie)
# =============================================================================


@pytest.mark.unit
async def test_vendor_refusal_marks_the_row_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `success: false` body must close the row, not leave it dialing.

    The vendor answers HTTP 200 even when it declines (unverified number,
    exhausted credit). Treating that as a placed call left a DIALING row that
    nothing would ever end: with no conversation id the self-healing probe
    cannot ask about it either, so it blocked EVERY further call until the
    15-minute stale threshold — observed in dev.
    """
    captured, factory = _install_fakes(
        monkeypatch,
        vendor_success=False,
        conversation_id=None,
        vendor_message="number not verified",
    )
    result = await _call(TelephonyService(_FakeDB(_user()), client_factory=factory))

    assert result.status == "rejected"
    assert "initiate_rejected" in captured["dial_failed_error"]
    assert "number not verified" in captured["dial_failed_error"]
    # And no conversation id was persisted for a call that never happened.
    assert "conversation_id" not in captured


@pytest.mark.unit
async def test_accepted_call_without_conversation_id_stays_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted but unidentifiable: the row must NOT be closed.

    The call may well be ringing. Closing it would let a second one start in
    parallel — the one thing the active-call guard exists to prevent. It is
    simply unprobeable, and the stale threshold remains the way out.
    """
    captured, factory = _install_fakes(monkeypatch, vendor_success=True, conversation_id=None)
    result = await _call(TelephonyService(_FakeDB(_user()), client_factory=factory))

    assert result.status == "placed"
    assert "dial_failed_error" not in captured


@pytest.mark.unit
async def test_successful_call_is_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The nominal path keeps persisting the conversation id."""
    captured, factory = _install_fakes(monkeypatch, vendor_success=True, conversation_id="conv_9")
    result = await _call(TelephonyService(_FakeDB(_user()), client_factory=factory))

    assert result.status == "placed"
    assert captured["conversation_id"] == "conv_9"
    assert "dial_failed_error" not in captured


# =============================================================================
# Status → phrase completeness (a status with no phrase raises KeyError at the
# worst moment: in front of the user, after they confirmed the call)
# =============================================================================


@pytest.mark.unit
def test_every_failure_status_has_a_phrase_in_every_language() -> None:
    """Each non-placed status maps to a phrase that exists in all 6 languages.

    `_STATUS_TO_PHRASE[result.status]` is an unguarded lookup, and the phrase is
    then read from the locale table. A status added without its phrase would
    raise KeyError right after the user confirmed — the least forgiving moment.
    """
    from typing import get_args

    # The real objects, not a copy and not a re-parse of the source: the table
    # is a module constant precisely so this test binds to what runs.
    from src.core.i18n_telephony import TOOL_PHRASES
    from src.domains.agents.tools.telephony_tools import _STATUS_TO_PHRASE
    from src.domains.telephony.service import _InitiateStatus

    non_placed = {s for s in get_args(_InitiateStatus) if s != "placed"}
    assert non_placed == set(
        _STATUS_TO_PHRASE
    ), f"status/phrase mismatch: {non_placed ^ set(_STATUS_TO_PHRASE)}"

    for language, phrases in TOOL_PHRASES.items():
        for status, phrase_key in _STATUS_TO_PHRASE.items():
            assert phrase_key in phrases, f"{language}: {status} → {phrase_key} missing"
            assert phrases[phrase_key].strip(), f"{language}: {phrase_key} is empty"


# ---------------------------------------------------------------------------
# One agent, two mandates (lot 2)
# ---------------------------------------------------------------------------


async def _owner_call(service: TelephonyService, **kwargs: object) -> object:
    return await service.initiate_call(
        user_id=uuid4(),
        callee_display="Alex",
        callee_phone="+33612345678",
        objective="go over the week",
        date_window=None,
        user_language="fr",
        kind=CallKind.SELF,
        user_context="## Agenda - 10:00 dentist",
        **kwargs,
    )


@pytest.mark.unit
async def test_owner_call_sends_the_rendered_override_and_records_its_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await _owner_call(TelephonyService(db, client_factory=factory))

    assert result.status == "placed"
    override = captured["call_kwargs"]["conversation_config_override"]
    assert "10:00 dentist" in override["agent"]["prompt"]["prompt"]
    assert "BUSY: Tue 09:00 → 10:30" in override["agent"]["prompt"]["prompt"]
    assert set(override["agent"]) == {"prompt", "first_message"}
    assert captured["create_data"]["call_kind"] is CallKind.SELF
    # The permission is part of the fingerprint, so a connector provisioned
    # before lot 2 is re-synced before the owner is dialled.
    assert captured["updated_agent"] == "ag_1"


@pytest.mark.unit
async def test_owner_call_refuses_when_the_agent_cannot_be_synced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed PATCH must not serve the owner the stranger's mandate."""
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch, sync_error=True)
    result = await _owner_call(TelephonyService(db, client_factory=factory))

    assert result.status == "agent_sync_failed"
    assert "call_kwargs" not in captured  # never dialled
    assert "create_data" not in captured  # no row left behind


@pytest.mark.unit
async def test_third_party_call_keeps_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await _call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert captured["call_kwargs"].get("conversation_config_override") is None
    assert captured["create_data"]["call_kind"] is CallKind.THIRD_PARTY


@pytest.mark.unit
async def test_verification_call_reads_no_calendar_and_speaks_the_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await TelephonyService(db, client_factory=factory).initiate_call(
        user_id=uuid4(),
        callee_display="Alex",
        callee_phone="+33612345678",
        objective="",
        date_window=None,
        user_language="fr",
        kind=CallKind.VERIFICATION,
        verification_code="4719",
    )
    assert result.status == "placed"
    assert "availability_read" not in captured
    override = captured["call_kwargs"]["conversation_config_override"]
    assert "4 7 1 9" in override["agent"]["prompt"]["prompt"]
    assert captured["create_data"]["call_kind"] is CallKind.VERIFICATION
    assert "consultations" not in captured


@pytest.mark.unit
async def test_availability_read_is_recorded_on_the_phone_call_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The calendar is opened from the dial path, not from a tool: the gate
    never sees it, so the service records it itself (ADR-263)."""
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    await _call(TelephonyService(db, client_factory=factory))
    (recorded,) = captured["consultations"]
    assert recorded["surface"] == "phone_call"
    assert list(recorded["opened"]) == ["availability"]
    assert list(recorded["failed"]) == []


@pytest.mark.unit
async def test_a_calendar_that_could_not_be_read_records_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)

    async def _failed(*_args, **_kwargs) -> AvailabilityRead:
        return AvailabilityRead(summary="unavailable", opened=True, failed=True)

    monkeypatch.setattr(svc, "build_availability", _failed)
    await _call(TelephonyService(db, client_factory=factory))
    (recorded,) = captured["consultations"]
    assert list(recorded["failed"]) == ["availability"]


@pytest.mark.unit
async def test_no_calendar_connected_records_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)

    async def _none(*_args, **_kwargs) -> AvailabilityRead:
        return AvailabilityRead(summary="unavailable", opened=False, failed=False)

    monkeypatch.setattr(svc, "build_availability", _none)
    await _call(TelephonyService(db, client_factory=factory))
    assert "consultations" not in captured


@pytest.mark.unit
async def test_owner_call_attaches_the_live_tools_to_the_agent_before_dialing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lot 7, measured on a real call 2026-09-16: the vendor refuses ``tool_ids``
    inside a per-call override (« Tool IDs not attached to this agent », the
    call dies at pickup). The ids are attached to the AGENT for the owner call
    — one PATCH before the dial, remembered on the connector — and the prompt
    names the tools; the override carries no ids."""
    from src.domains.telephony.live_tools import LiveToolBinding

    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    service = TelephonyService(db, client_factory=factory)
    result = await _owner_call(
        service, live_tools=(LiveToolBinding("get_events_tool", "tool_a", "event"),)
    )

    assert result.status == "placed"
    assert captured["tool_ids_patches"] == [("ag_1", ["tool_a"])]
    override = captured["call_kwargs"]["conversation_config_override"]
    assert "tool_ids" not in override["agent"]["prompt"]
    assert "Calendar" in override["agent"]["prompt"]["prompt"]
    assert captured["connector"].connector_metadata["live_tools_attached"] is True


@pytest.mark.unit
async def test_a_third_party_call_detaches_the_live_tools_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stranger's agent never dials with the owner's tools attached: a
    connector still marked attached (a webhook that never came) is detached
    BEFORE a third-party or verification call leaves."""
    connector = SimpleNamespace(
        connector_metadata={
            "agent_id": "ag_1",
            "agent_phone_number_id": "pn_1",
            "live_tools_attached": True,
        }
    )
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch, connector=connector)
    result = await _call(TelephonyService(db, client_factory=factory))

    assert result.status == "placed"
    assert captured["tool_ids_patches"] == [("ag_1", [])]
    assert connector.connector_metadata["live_tools_attached"] is False


@pytest.mark.unit
async def test_an_owner_call_without_tools_leaves_a_detached_agent_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDB(_user())
    captured, factory = _install_fakes(monkeypatch)
    result = await _owner_call(TelephonyService(db, client_factory=factory))
    assert result.status == "placed"
    assert "tool_ids_patches" not in captured
