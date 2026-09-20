"""LiveService (ADR-299): the refusals in order, a credential and a setup, a
fresh credential on reconnection, the trace and the closed books."""

from __future__ import annotations

import base64
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.constants import LIVE_DELEGATION_TOOL_NAME, LIVE_SESSION_RECORD_GRACE_SECONDS
from src.core.i18n_live import get_live_phrases
from src.domains.live.errors import LiveRefusedError
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import setup_inputs_from_dict, setup_inputs_to_dict
from src.domains.live.providers.protocol import (
    LiveCredential,
    LiveModelCapabilities,
    LiveSetupInputs,
)
from src.domains.live.schemas import (
    LiveConnectorActivateRequest,
    LiveConnectorSettings,
    LiveEndRequest,
    LiveModel,
    LiveModelCapabilitiesResponse,
    LiveTurnRequest,
    LiveUsage,
    LiveVoiceSampleRequest,
)
from src.domains.live.service import LiveService
from src.domains.live.session_store import LiveSessionRecord
from tests.unit.domains.live.conftest import CLOSING_ARCHIVE as _CLOSING_ARCHIVE


def record_fields(record: LiveSessionRecord) -> dict[str, object]:
    """The record as keyword arguments, for a copy with one field changed."""
    from dataclasses import asdict

    return asdict(record)


pytestmark = pytest.mark.unit

MODULE = "src.domains.live.service"
CLOSING = "src.infrastructure.scheduler.voice_session_closing"


CMODULE = "src.domains.live.connector_service"


def _now() -> datetime:
    """The instant of THIS call — never a module constant.

    The coverage run is sequential: this module's tests ran seven minutes after
    collection, and a record built from a constant taken at import time
    (``expires_at = _now() + 5 min``, ``nonce_until = _now() + 30 s``) was already
    expired — six refusals (`session_expired`, `credential_invalid`) the xdist
    run never sees because it finishes the module in seconds.
    """
    return datetime.now(UTC)


USER = SimpleNamespace(
    id=uuid.uuid4(),
    language="fr",
    timezone="Europe/Paris",
    full_name="Alex",
    email="a@x.y",
    live_preferences=None,
    memory_enabled=True,
)


def _connector(model: str = "gemini-3.8-live", voice: str = "Kore") -> SimpleNamespace:
    return SimpleNamespace(
        connector_type="gemini_live",
        status="active",
        connector_metadata={
            "model": model,
            "voice": voice,
            "thinking_level": None,
            "functionally_verified": True,
        },
    )


def _chosen(**overrides: object) -> LiveConnectorSettings:
    """A PUT payload: every field, the durations at the instance defaults unless said."""
    base: dict[str, object] = {
        "model": "gemini-3.8-live",
        "voice": "Kore",
        "thinking_level": None,
        "idle_timeout_seconds": settings.live_idle_timeout_seconds,
        "session_max_minutes": settings.live_session_max_minutes,
    }
    base.update(overrides)
    return LiveConnectorSettings.model_validate(base)


def _record(
    user_id: uuid.UUID, session_id: str = "s" * 32, token: str = "tok"
) -> LiveSessionRecord:
    inputs = LiveSetupInputs(
        model="gemini-3.8-live",
        voice="Kore",
        thinking_level=None,
        system_instruction="mandate",
        tool_declaration={
            "name": LIVE_DELEGATION_TOOL_NAME,
            "description": "d",
            "parameters": {},
            "behavior": "NON_BLOCKING",
        },
        preferences=LivePreferences(),
        trigger_tokens=1,
        target_tokens=1,
    )
    return LiveSessionRecord(
        session_id=session_id,
        user_id=user_id,
        provider="gemini",
        model="gemini-3.8-live",
        run_id=f"live_session_{session_id}",
        started_at=_now() - timedelta(minutes=5),
        expires_at=_now() + timedelta(minutes=5),
        token=token,
        setup_inputs=setup_inputs_to_dict(inputs),
    )


def _service(
    connector: SimpleNamespace | None,
    *,
    record: LiveSessionRecord | None = None,
    claimed: bool = True,
    active: int = 0,
    allowed: bool = True,
) -> tuple[LiveService, MagicMock, MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    service = LiveService(db)
    service.connectors.active_connectors = AsyncMock(  # type: ignore[method-assign]
        return_value=[connector] if connector else []
    )
    service.connectors.chosen_connector = AsyncMock(  # type: ignore[method-assign]
        return_value=connector
    )
    service.connectors.api_key_of = AsyncMock(return_value="k")  # type: ignore[method-assign]
    service._personality_of = AsyncMock(return_value="")  # type: ignore[method-assign]
    service._inner_state_of = AsyncMock(return_value="")  # type: ignore[method-assign]
    service._conversation_id = AsyncMock(return_value=uuid.uuid4())  # type: ignore[method-assign]
    archive = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    service._archive = archive  # type: ignore[method-assign]
    _CLOSING_ARCHIVE["mock"] = archive
    store = MagicMock()
    # The fake store HOLDS what a successful claim wrote, so `get` answers the
    # record the service just claimed (the service re-reads it after the mint).
    held: dict[str, LiveSessionRecord | None] = {"record": record}
    store.claim_answers = [claimed]

    async def _claim(new_record: LiveSessionRecord, *, ttl_seconds: int) -> bool:
        answer = (
            store.claim_answers.pop(0) if len(store.claim_answers) > 1 else store.claim_answers[0]
        )
        if answer:
            held["record"] = new_record
        return bool(answer)

    async def _extend(new_record: LiveSessionRecord, *, ttl_seconds: int) -> bool:
        current = held["record"]
        if current is None or current.token != new_record.token:
            return False
        held["record"] = new_record
        store.extend_ttl = ttl_seconds
        return True

    async def _rewrite(new_record: LiveSessionRecord, *, now: datetime) -> bool:
        return await _extend(new_record, ttl_seconds=new_record.remaining_life_seconds(now))

    store.claim = AsyncMock(side_effect=_claim)
    store.extend = AsyncMock(side_effect=_extend)
    store.rewrite = AsyncMock(side_effect=_rewrite)
    store.get = AsyncMock(side_effect=lambda _user_id: held["record"])
    store.count_active = AsyncMock(return_value=active)
    store.register_active = AsyncMock()
    store.unregister_active = AsyncMock()
    store.release = AsyncMock(return_value=True)
    # A DIRECT session keeps its turns in the record (ADR-301): the fake
    # holds them exactly as the Redis list does.
    kept_turns: list[tuple[str, str]] = []

    async def _append_turns(_user_id, rows, *, ttl_seconds, max_rows):  # noqa: ANN001
        room = max(0, max_rows - len(kept_turns))
        kept_turns.extend(rows[:room])
        return len(rows[:room])

    store.append_turns = AsyncMock(side_effect=_append_turns)
    store.turns = AsyncMock(side_effect=lambda _user_id: list(kept_turns))
    store.kept_turns = kept_turns
    service._store = AsyncMock(return_value=store)  # type: ignore[method-assign]
    limiter = MagicMock()
    limiter.acquire = AsyncMock(return_value=allowed)
    service._limiter = AsyncMock(return_value=limiter)  # type: ignore[method-assign]
    service.connectors._limiter = AsyncMock(return_value=limiter)  # type: ignore[method-assign]
    return service, store, archive


def _fake_provider(credential_name: str = "auth_tokens/t") -> MagicMock:
    provider = MagicMock()
    provider.provider_id = "gemini"
    provider.knows_voice = MagicMock(side_effect=lambda name: name == "Kore")
    provider.thinking_levels_of = MagicMock(
        side_effect=lambda model: ("low", "medium", "high") if "thinking" in model else ()
    )
    provider.probe = AsyncMock(return_value=(True, "ok"))
    provider.connector_type = "gemini_live"
    provider.connection = "token"
    provider.delegation_wire = "tool"
    provider.default_model = "gemini-3.8-live"
    # Priced by the platform's tariff table (Gemini, GPT-Live); a vendor-billed
    # provider (an ElevenLabs agent) is priced by nobody here.
    provider.billing = "tariff"
    provider.sample_rate = 24_000
    provider.sample_voice = AsyncMock(return_value=b"\x00\x01" * 4)
    provider.capabilities_of = MagicMock(
        side_effect=lambda model: LiveModelCapabilities(
            async_delegation="3.1" not in model,
            delivery_scheduling="thinking" not in model,
            reports_idle="thinking" in model,
            cancels_on_interruption=True,
            configurable_vad=True,
            resumes=True,
            thinking="thinking" in model,
        )
    )
    provider.mint = AsyncMock(
        return_value=LiveCredential(
            credential_name, _now() + timedelta(minutes=30), _now() + timedelta(minutes=1)
        )
    )
    provider.build_setup = MagicMock(return_value={"model": "models/gemini-3.8-live"})
    return provider


# -- start ---------------------------------------------------------------------


async def test_no_connector_refuses_409() -> None:
    service, _, _ = _service(None)
    with pytest.raises(LiveRefusedError) as raised:
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.status_code == 409 and raised.value.code == "connector_missing"


async def test_rate_limited_refuses_429() -> None:
    service, _, _ = _service(_connector(), allowed=False)
    with pytest.raises(LiveRefusedError) as raised:
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.status_code == 429


async def test_a_held_slot_with_no_readable_record_refuses_409() -> None:
    service, _, _ = _service(_connector(), claimed=False, record=None)
    with pytest.raises(LiveRefusedError) as raised:
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "session_in_progress"


async def test_a_held_slot_of_the_same_account_is_superseded_then_claimed() -> None:
    # A tab that died without closing its books must not lock the person out
    # until the record's TTL: the new start closes the previous session with
    # its own outcome and takes the slot.
    previous = _record(USER.id)
    service, store, archive = _service(_connector(), claimed=False, record=previous)
    store.claim_answers[:] = [False, True]
    provider = _fake_provider()
    with (
        patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}),
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()),
    ):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.session_id != previous.session_id
    assert archive.call_args.kwargs["metadata"]["live_summary"]["outcome"] == "superseded"
    store.release.assert_awaited_with(USER.id, previous.token)
    assert store.claim.await_count == 2


async def test_a_held_slot_whose_close_fails_refuses_409() -> None:
    previous = _record(USER.id)
    service, store, _ = _service(_connector(), claimed=False, record=previous)
    service._supersede = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with pytest.raises(LiveRefusedError) as raised:
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "session_in_progress"
    assert store.claim.await_count == 1


async def test_a_full_instance_refuses_503_and_releases_the_claim() -> None:
    service, store, _ = _service(_connector(), active=8)
    with pytest.raises(LiveRefusedError) as raised:
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.status_code == 503
    store.release.assert_awaited_once()


async def test_a_record_superseded_during_its_own_mint_is_refused_and_never_counted() -> None:
    # Two starts of one account in the same second: the second supersedes the
    # first while its credential is being minted. The first must not register
    # itself as active on a slot that is no longer its own.
    service, store, _ = _service(_connector())
    store.get = AsyncMock(return_value=_record(USER.id))  # another token holds the slot
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "session_in_progress"
    store.register_active.assert_not_awaited()


async def test_an_agent_bound_provider_prepares_the_agent_before_the_claim() -> None:
    # ADR-300 wave 4: what the provider holds on the person's agent is kept on
    # the connector (a NEW dict), and a vendor refusal is a start that never
    # happened — nothing claimed, nothing minted.
    # A fake provider becomes agent-bound by holding a real `sync_agent`: the
    # runtime protocol reads the instance statically, so the mock's magic
    # attributes do not count and only this one does.
    connector = _connector()
    connector.connector_metadata = {**connector.connector_metadata, "agent_id": "a1"}
    service, store, _ = _service(connector)
    provider = _fake_provider()
    seen: dict[str, object] = {}

    async def _sync(api_key: str, metadata: dict, inputs: object) -> dict:
        seen["metadata"] = metadata
        return {**metadata, "elevenlabs_live_tools": {"f1": ["t1"]}}

    provider.sync_agent = _sync
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.session_id
    assert seen["metadata"]["agent_id"] == "a1"
    assert connector.connector_metadata["elevenlabs_live_tools"] == {"f1": ["t1"]}
    service.db.commit.assert_awaited()

    failing = _fake_provider()

    async def _refuse(api_key: str, metadata: dict, inputs: object) -> dict:
        raise RuntimeError("vendor down")

    failing.sync_agent = _refuse
    service, store, _ = _service(_connector())
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": failing}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "provider_refused"
    store.claim.assert_not_awaited()
    failing.mint.assert_not_awaited()


async def test_start_mints_and_returns_the_setup() -> None:
    service, store, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.credential == "auth_tokens/t"
    assert response.run_id == f"live_session_{response.session_id}"
    assert response.setup["model"] == "models/gemini-3.8-live"
    assert response.delegation_tool_name == LIVE_DELEGATION_TOOL_NAME
    # The session's own cap travels with the start: the client arms its
    # dialog and its expiry from it — the instant the credential was minted to.
    assert response.expires_at == provider.mint.call_args.kwargs["expires_at"]
    # The client reads CAPABILITIES, never a provider id (spec A11).
    assert response.capabilities.async_delegation is True
    assert response.capabilities.reports_idle is False
    # The mandate was rendered for that capability.
    inputs = provider.mint.call_args.args[1]
    assert inputs.system_instruction
    inputs = provider.mint.call_args.args[1]
    assert "Alex" in inputs.system_instruction
    assert inputs.tool_declaration["behavior"] == "NON_BLOCKING"
    record = store.claim.call_args.args[0]
    assert record.setup_inputs["system_instruction"] == inputs.system_instruction
    # The record outlives the cap by the closing grace: a session that ran to
    # its cap must still find its record when it closes its books.
    assert (
        store.claim.call_args.kwargs["ttl_seconds"]
        == settings.live_session_max_minutes * 60 + LIVE_SESSION_RECORD_GRACE_SECONDS
    )
    store.register_active.assert_awaited_once()
    # The start says what THIS model runs under: the connector stored no
    # durations, so the instance defaults apply.
    assert response.session_max_minutes == settings.live_session_max_minutes
    assert response.idle_timeout_seconds == settings.live_idle_timeout_seconds


async def test_start_hands_the_mandate_lias_inner_state_when_the_engine_has_one() -> None:
    # Owner question 5 (2026-09-19): the psyche engine's own block colours the
    # voice's manner from the session's start — read for THIS person and clock,
    # and absent from the text when the engine answers nothing.
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    service._inner_state_of = AsyncMock(  # type: ignore[method-assign]
        return_value="<InnerVoice>\nRight now, inside, you are slightly serene.\n</InnerVoice>"
    )
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    service._inner_state_of.assert_awaited_once_with(USER.id, "Europe/Paris")
    mandate = provider.mint.call_args.args[1].system_instruction
    assert "<InnerVoice>" in mandate and "slightly serene" in mandate
    assert "\n\n\n" not in mandate


async def test_start_reads_the_models_own_cap_and_silence() -> None:
    # Per-model durations (owner decision 2026-09-19): the cap and the TTL follow
    # the MODEL's minutes, and the silence timeout travels to the client.
    connector = SimpleNamespace(
        connector_type="gemini_live",
        status="active",
        connector_metadata={
            "model": "gemini-3.8-live",
            "models": {
                "gemini-3.8-live": {
                    "voice": "Kore",
                    "thinking_level": None,
                    "idle_timeout_seconds": 120,
                    "session_max_minutes": 25,
                }
            },
        },
    )
    service, store, _ = _service(connector)
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.session_max_minutes == 25
    assert response.idle_timeout_seconds == 120
    minted_to = provider.mint.call_args.kwargs["expires_at"]
    started_at = store.claim.call_args.args[0].started_at
    assert (minted_to - started_at).total_seconds() == 25 * 60
    assert (
        store.claim.call_args.kwargs["ttl_seconds"] == 25 * 60 + LIVE_SESSION_RECORD_GRACE_SECONDS
    )


async def test_an_unlimited_cap_rolls_by_extension_slices_never_for_ever() -> None:
    # 0 = unlimited: the credential and the record still carry a cap (the
    # extension slice) that the client renews silently — a key with no TTL is
    # never written, and a provider's token cannot outlive its own expiry.
    connector = SimpleNamespace(
        connector_type="gemini_live",
        status="active",
        connector_metadata={
            "model": "gemini-3.8-live",
            "models": {
                "gemini-3.8-live": {
                    "voice": "Kore",
                    "idle_timeout_seconds": 0,
                    "session_max_minutes": 0,
                }
            },
        },
    )
    service, store, _ = _service(connector)
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.session_max_minutes == 0 and response.idle_timeout_seconds == 0
    slice_seconds = settings.live_extension_minutes * 60
    assert (
        store.claim.call_args.kwargs["ttl_seconds"]
        == slice_seconds + LIVE_SESSION_RECORD_GRACE_SECONDS
    )
    minted_to = provider.mint.call_args.kwargs["expires_at"]
    started_at = store.claim.call_args.args[0].started_at
    assert (minted_to - started_at).total_seconds() == slice_seconds
    # The record says its cap rolls: a renewal will never read as an extension.
    assert store.claim.call_args.args[0].unlimited_cap is True


async def test_a_rolling_renewal_is_not_the_persons_extension() -> None:
    # The client renews an unlimited cap in silence: the cap moves, the
    # credential is re-minted, but nobody prolonged anything — the summary
    # must not say « extended 5 times », and the metric names the kind.
    record = LiveSessionRecord(**{**record_fields(_record(USER.id)), "unlimited_cap": True})
    service, store, _ = _service(_connector(), record=record)
    provider = _fake_provider()
    with (
        patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}),
        patch(f"{MODULE}.settings") as cfg,
        patch(f"{MODULE}.live_session_extensions_total") as metric,
    ):
        cfg.live_extension_minutes = 10
        cfg.live_mint_rate_limit_max_calls = 12
        cfg.live_mint_rate_limit_window_seconds = 60
        cfg.live_connect_window_seconds = 60
        response = await service.extend(USER, "s" * 32, language="fr")
    assert response.expires_at == record.expires_at + timedelta(minutes=10)
    assert response.extensions == 0
    assert response.credential is not None
    assert store.extend.call_args.args[0].extensions == 0
    metric.labels.assert_called_once_with(provider="gemini", kind="rolling")


async def test_a_provider_mint_failure_releases_the_claim_and_answers_422() -> None:
    service, store, _ = _service(_connector())
    provider = _fake_provider()
    provider.mint = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}),
        pytest.raises(LiveRefusedError) as raised,
    ):
        await service.start(USER, language="fr", timezone="Europe/Paris", display_name="Alex")
    assert raised.value.code == "provider_refused"
    store.release.assert_awaited_once()


# -- renewal -------------------------------------------------------------------


async def test_renew_mints_a_fresh_credential_for_the_same_setup() -> None:
    record = _record(USER.id)
    service, _, _ = _service(_connector(), record=record)
    provider = _fake_provider("auth_tokens/fresh")
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        renewed = await service.renew_credential(USER, "s" * 32, language="fr")
    assert renewed.credential == "auth_tokens/fresh"
    inputs = provider.mint.call_args.args[1]
    assert inputs.system_instruction == "mandate"
    # The session's expiry does not move with a reconnection — and it is the
    # RECORD's (an extension moved it; the cap alone would mint a dead token).
    assert provider.mint.call_args.kwargs["expires_at"] == record.expires_at


async def test_extend_adds_the_extension_from_the_current_expiry() -> None:
    record = _record(USER.id)
    service, store, _ = _service(_connector(), record=record)
    provider = _fake_provider()
    with (
        patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}),
        patch(f"{MODULE}.settings") as cfg,
    ):
        cfg.live_extension_minutes = 10
        cfg.live_mint_rate_limit_max_calls = 12
        cfg.live_mint_rate_limit_window_seconds = 60
        cfg.live_connect_window_seconds = 60
        response = await service.extend(USER, "s" * 32, language="fr")
    # From the CURRENT expiry, never from now: « ten more minutes » means ten.
    assert response.expires_at == record.expires_at + timedelta(minutes=10)
    assert response.extensions == 1
    # Measured 2026-09-19: an OPEN socket is closed at the token's expiry
    # (1011 « auth token has expired »), so an extension mints a FRESH
    # credential with the new expiry and the client reconnects on it.
    assert response.credential is not None
    assert response.credential.credential == "auth_tokens/t"
    assert provider.mint.call_args.kwargs["expires_at"] == response.expires_at
    extended = store.extend.call_args.args[0]
    assert extended.token == record.token and extended.extensions == 1
    # The record and the claim outlive the new expiry by the grace, as at the claim.
    assert store.extend_ttl >= 10 * 60 + LIVE_SESSION_RECORD_GRACE_SECONDS - 5
    store.register_active.assert_awaited_once_with("s" * 32, response.expires_at)
    # A second extension stacks: unlimited, each explicit (owner decision).
    with (
        patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}),
        patch(f"{MODULE}.settings") as cfg,
    ):
        cfg.live_extension_minutes = 10
        cfg.live_mint_rate_limit_max_calls = 12
        cfg.live_mint_rate_limit_window_seconds = 60
        cfg.live_connect_window_seconds = 60
        again = await service.extend(USER, "s" * 32, language="fr")
    assert again.extensions == 2
    assert again.expires_at == record.expires_at + timedelta(minutes=20)


async def test_extend_past_the_cap_is_refused_as_expired() -> None:
    # The client's own timer ends the session at the cap; a request that
    # lands after it is told the truth, never « not found » (which the client
    # reads as superseded).
    record = LiveSessionRecord(
        **{**record_fields(_record(USER.id)), "expires_at": _now() - timedelta(seconds=1)}
    )
    service, store, _ = _service(_connector(), record=record)
    with pytest.raises(LiveRefusedError) as refusal:
        await service.extend(USER, "s" * 32, language="fr")
    assert refusal.value.status_code == 409 and refusal.value.code == "session_expired"
    store.extend.assert_not_awaited()


async def test_extend_of_another_session_is_not_found() -> None:
    service, store, _ = _service(_connector(), record=_record(USER.id))
    with pytest.raises(LiveRefusedError) as refusal:
        await service.extend(USER, "z" * 32, language="fr")
    assert refusal.value.code == "session_not_found"
    store.extend.assert_not_awaited()


async def test_extend_lost_to_a_newer_session_is_not_found() -> None:
    # The store refused (the owner token no longer holds the claim): this tab
    # was superseded meanwhile, and 404 is what it reads as such.
    service, store, _ = _service(_connector(), record=_record(USER.id))
    store.extend = AsyncMock(return_value=False)
    with pytest.raises(LiveRefusedError) as refusal:
        await service.extend(USER, "s" * 32, language="fr")
    assert refusal.value.code == "session_not_found"


async def test_renew_of_another_session_is_not_found() -> None:
    service, _, _ = _service(_connector(), record=_record(USER.id))
    with pytest.raises(LiveRefusedError) as refusal:
        await service.renew_credential(USER, "z" * 32, language="fr")
    assert refusal.value.status_code == 404 and refusal.value.code == "session_not_found"


def test_setup_inputs_round_trip() -> None:
    inputs = setup_inputs_from_dict(_record(USER.id).setup_inputs)
    assert inputs.model == "gemini-3.8-live" and inputs.preferences == LivePreferences()


def test_setup_inputs_round_trip_is_equality_over_every_field() -> None:
    # A field added on one side only is lost after every credential renewal
    # (the record is what a reconnection re-mints from). Both shapes: the
    # delegated one and the DIRECT one, whose declaration is None.
    delegated = setup_inputs_from_dict(_record(USER.id).setup_inputs)
    assert setup_inputs_from_dict(setup_inputs_to_dict(delegated)) == delegated
    direct = replace(
        delegated,
        tool_declaration=None,
        direct_tools=({"name": "get_calendar_events", "description": "d", "parameters": {}},),
    )
    assert setup_inputs_from_dict(setup_inputs_to_dict(direct)) == direct


# -- voice sample ----------------------------------------------------------------


async def test_sample_speaks_the_sentence_of_the_language_on_the_stored_key_as_wav() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.connectors.sample_voice(
            USER, LiveVoiceSampleRequest(voice="Kore"), language="fr"
        )
    provider.sample_voice.assert_awaited_once_with(
        "k", "Kore", get_live_phrases("fr")["voice_sample"]
    )
    wav = base64.b64decode(response.audio_base64)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and wav[44:] == b"\x00\x01" * 4
    assert response.sample_rate == 24_000 and response.format == "wav"


async def test_sample_uses_the_forms_key_before_the_connector_exists() -> None:
    service, _, _ = _service(None)
    service.connectors.api_key_of = AsyncMock(return_value="")  # type: ignore[method-assign]
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        await service.connectors.sample_voice(
            USER, LiveVoiceSampleRequest(voice="Kore", api_key="AIza-form-key"), language="en"
        )
    assert provider.sample_voice.call_args.args[0] == "AIza-form-key"


async def test_sample_refuses_a_voice_off_the_list_before_any_call() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.sample_voice(
                USER, LiveVoiceSampleRequest(voice="Nope"), language="fr"
            )
    assert raised.value.code == "voice_unknown"
    provider.sample_voice.assert_not_awaited()


async def test_sample_without_any_key_names_the_missing_connector() -> None:
    service, _, _ = _service(None)
    service.connectors.api_key_of = AsyncMock(return_value="")  # type: ignore[method-assign]
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.sample_voice(
                USER, LiveVoiceSampleRequest(voice="Kore"), language="fr"
            )
    assert raised.value.code == "connector_missing"


async def test_sample_is_bounded_by_its_own_limiter() -> None:
    service, _, _ = _service(_connector(), allowed=False)
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.sample_voice(
                USER, LiveVoiceSampleRequest(voice="Kore"), language="fr"
            )
    assert raised.value.code == "mint_rate_limited"
    provider.sample_voice.assert_not_awaited()


async def test_a_provider_failure_on_a_sample_is_a_refusal_in_its_words() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    provider.sample_voice = AsyncMock(side_effect=ValueError("the provider returned no audio"))
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.sample_voice(
                USER, LiveVoiceSampleRequest(voice="Kore"), language="fr"
            )
    assert raised.value.code == "provider_refused"


# -- connector -----------------------------------------------------------------


async def test_activation_refuses_a_voice_the_provider_does_not_know() -> None:
    service, _, _ = _service(None)
    provider = _fake_provider()
    with (
        patch(f"{CMODULE}.ConnectorService") as connectors,
        patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}),
    ):
        connectors.return_value.validate_api_key = AsyncMock(return_value=(True, "ok"))
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.activate_connector(
                USER,
                LiveConnectorActivateRequest(
                    api_key="AIza-test-key", model="gemini-3.8-live", voice="Nope"
                ),
                language="fr",
            )
    assert raised.value.code == "voice_unknown"
    provider.probe.assert_not_awaited()


async def test_a_level_off_the_models_ladder_is_refused_before_the_probe() -> None:
    # ADR-245: the UI is offered exactly what the API accepts — the ladder the
    # listing publishes per model is the one the write path enforces.
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.update_connector_settings(
                USER,
                "gemini",
                _chosen(model="gemini-3.8-live", thinking_level="high"),
                language="fr",
            )
    assert raised.value.code == "thinking_level_unknown"
    provider.probe.assert_not_awaited()


async def test_a_model_that_requires_a_level_refuses_none_before_the_probe() -> None:
    # Extended Thinking requires a thinking level (documented): a choice
    # without one is refused by LIA in the person's language, not by the
    # provider's 1007 after a paid probe.
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.connectors.update_connector_settings(
                USER,
                "gemini",
                _chosen(model="gemini-3.8-live-extended-thinking"),
                language="fr",
            )
    assert raised.value.code == "thinking_level_unknown"
    provider.probe.assert_not_awaited()


async def test_update_settings_probes_the_model_and_stores_a_new_dict() -> None:
    connector = _connector()
    old_metadata = connector.connector_metadata
    service, _, _ = _service(connector)
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.connectors.update_connector_settings(
            USER,
            "gemini",
            _chosen(model="gemini-3.8-live-extended-thinking", thinking_level="high"),
            language="fr",
        )
    assert response.settings.thinking_level == "high"
    assert connector.connector_metadata is not old_metadata
    provider.probe.assert_awaited_once()
    # The model switched to is remembered BESIDE the previous one: its voice
    # is not forgotten by the switch (owner decision 2026-09-19).
    assert set(response.model_settings) == {"gemini-3.8-live", "gemini-3.8-live-extended-thinking"}
    assert response.model_settings["gemini-3.8-live"].voice == "Kore"
    assert "voice" not in connector.connector_metadata
    assert (
        connector.connector_metadata["models"]["gemini-3.8-live-extended-thinking"][
            "idle_timeout_seconds"
        ]
        == settings.live_idle_timeout_seconds
    )
    # Saving a connector makes it the provider the sessions open on (a NEW dict).
    assert USER.live_preferences["provider"] == "gemini"
    assert response.active is True
    # The probe replays the real setup: the chosen model and level, the tool.
    inputs = provider.probe.call_args.args[1]
    assert inputs.model == "gemini-3.8-live-extended-thinking"
    assert inputs.thinking_level == "high"
    assert inputs.tool_declaration["name"] == "send_to_lia"
    assert inputs.system_instruction


async def test_the_chosen_connector_follows_the_choice_and_falls_back_to_the_first() -> None:
    # Two active keys (the category is additive): the sessions open on the
    # one the person last saved; a choice whose connector is gone falls back
    # rather than refusing — one key disconnected of two still leaves a live mode.
    gemini = _connector()
    other = SimpleNamespace(
        connector_type="gemini_live", status="active", connector_metadata={"model": "m"}
    )
    service = LiveService(MagicMock())
    service.connectors.active_connectors = AsyncMock(  # type: ignore[method-assign]
        return_value=[gemini, other]
    )
    picked = SimpleNamespace(**{**USER.__dict__, "live_preferences": {"provider": "gemini"}})
    assert await service.connectors.chosen_connector(picked) is gemini
    gone = SimpleNamespace(**{**USER.__dict__, "live_preferences": {"provider": "nowhere"}})
    assert await service.connectors.chosen_connector(gone) is gemini
    service.connectors.active_connectors = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert await service.connectors.chosen_connector(picked) is None


async def test_the_reflexes_put_keeps_the_provider_choice() -> None:
    # The four reflexes and the provider share one column; the settings panel
    # PUTs the reflexes alone and must not silently reset the choice.
    service, _, _ = _service(_connector())
    user = SimpleNamespace(**{**USER.__dict__, "live_preferences": {"provider": "gemini"}})
    saved = await service.connectors.update_preferences(user, LivePreferences(end_of_speech="calm"))
    assert saved.provider == "gemini" and saved.end_of_speech == "calm"
    assert user.live_preferences["provider"] == "gemini"


async def test_list_models_is_the_union_of_every_active_key_each_naming_its_provider() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    provider.list_models = AsyncMock(
        return_value=[
            LiveModel(
                provider="gemini",
                name="gemini-3.8-live",
                thinking_levels=[],
                capabilities=LiveModelCapabilitiesResponse(
                    **dict.fromkeys(LiveModelCapabilitiesResponse.model_fields, True)
                ),
            )
        ]
    )
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        listing = await service.connectors.list_models(USER, language="fr")
    assert [m.provider for m in listing.models] == ["gemini"]


def _offer_provider() -> MagicMock:
    """GPT-Live's shape: an `offer` connection whose credential is LIA's own nonce."""
    provider = _fake_provider(credential_name="nonce-" + "n" * 40)
    provider.provider_id = "openai"
    provider.connector_type = "gpt_live"
    provider.connection = "offer"
    provider.delegation_wire = "native"
    provider.default_model = "gpt-live-1"
    provider.knows_voice = MagicMock(side_effect=lambda name: name == "quartz")
    provider.exchange_offer = AsyncMock(return_value="v=0 answer")
    provider.build_setup = MagicMock(return_value={"model": "gpt-live-1"})
    return provider


def _openai_connector() -> SimpleNamespace:
    return SimpleNamespace(
        connector_type="gpt_live",
        status="active",
        connector_metadata={
            "model": "gpt-live-1",
            "voice": "quartz",
            "thinking_level": None,
            "functionally_verified": True,
        },
    )


async def test_start_on_an_offer_provider_keeps_the_nonce_on_the_record() -> None:
    # No provider token exists for GPT-Live: the credential is LIA's nonce,
    # written on the record under its claim, and the browser is told how to connect.
    service, store, _ = _service(_openai_connector())
    provider = _offer_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}):
        started = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert started.connection == "offer"
    assert started.credential.startswith("nonce-")
    kept = await store.get(USER.id)
    assert kept is not None and kept.nonce == started.credential
    assert kept.nonce_until == started.connect_deadline_at
    store.rewrite.assert_awaited_once()


async def test_start_on_a_token_provider_writes_no_nonce() -> None:
    service, store, _ = _service(_connector())
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": _fake_provider()}):
        started = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert started.connection == "token"
    kept = await store.get(USER.id)
    assert kept is not None and kept.nonce is None
    store.rewrite.assert_not_awaited()


async def test_exchange_offer_consumes_the_nonce_once_and_hands_the_answer() -> None:
    from src.domains.live.schemas import LiveOfferRequest

    record = replace(
        _record(USER.id),
        provider="openai",
        model="gpt-live-1",
        nonce="nonce-" + "n" * 40,
        nonce_until=_now() + timedelta(seconds=30),
    )
    service, store, _ = _service(_openai_connector(), record=record)
    provider = _offer_provider()
    payload = LiveOfferRequest(credential="nonce-" + "n" * 40, sdp="v=0 " + "o" * 20)
    with patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}):
        answer = await service.exchange_offer(USER, record.session_id, payload, language="fr")
        assert answer.sdp == "v=0 answer"
        provider.exchange_offer.assert_awaited_once()
        assert provider.exchange_offer.call_args.args[2] == payload.sdp
        assert (
            provider.exchange_offer.call_args.kwargs["timeout"]
            == settings.live_probe_timeout_seconds
        )
        # One credential, one exchange: the same nonce is refused the second time.
        with pytest.raises(LiveRefusedError) as refused:
            await service.exchange_offer(USER, record.session_id, payload, language="fr")
    assert refused.value.code == "credential_invalid"
    kept = await store.get(USER.id)
    assert kept is not None and kept.nonce is None and kept.nonce_until is None


async def test_exchange_offer_refuses_a_stale_nonce_a_foreign_one_and_a_token_provider() -> None:
    from src.domains.live.schemas import LiveOfferRequest

    stale = replace(
        _record(USER.id),
        provider="openai",
        model="gpt-live-1",
        nonce="nonce-" + "n" * 40,
        nonce_until=_now() - timedelta(seconds=1),
    )
    service, _, _ = _service(_openai_connector(), record=stale)
    provider = _offer_provider()
    good = LiveOfferRequest(credential="nonce-" + "n" * 40, sdp="v=0 " + "o" * 20)
    with patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}):
        with pytest.raises(LiveRefusedError) as expired:
            await service.exchange_offer(USER, stale.session_id, good, language="fr")
        assert expired.value.code == "credential_invalid"
    fresh = replace(stale, nonce_until=_now() + timedelta(seconds=30))
    service, _, _ = _service(_openai_connector(), record=fresh)
    with patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}):
        with pytest.raises(LiveRefusedError) as foreign:
            await service.exchange_offer(
                USER,
                fresh.session_id,
                LiveOfferRequest(credential="nonce-" + "x" * 40, sdp=good.sdp),
                language="fr",
            )
        assert foreign.value.code == "credential_invalid"
    provider.exchange_offer.assert_not_awaited()
    # A Gemini session has no offer to exchange: the browser opened its socket itself.
    service, _, _ = _service(_connector(), record=_record(USER.id))
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": _fake_provider()}):
        with pytest.raises(LiveRefusedError) as wrong:
            await service.exchange_offer(USER, "s" * 32, good, language="fr")
    assert wrong.value.code == "provider_refused"


async def test_exchange_offer_reports_the_providers_refusal_and_burns_the_nonce() -> None:
    from src.domains.live.providers.openai_live_socket import OpenAiLiveRefused
    from src.domains.live.schemas import LiveOfferRequest

    record = replace(
        _record(USER.id),
        provider="openai",
        model="gpt-live-1",
        nonce="nonce-" + "n" * 40,
        nonce_until=_now() + timedelta(seconds=30),
    )
    service, store, _ = _service(_openai_connector(), record=record)
    provider = _offer_provider()
    provider.exchange_offer = AsyncMock(
        side_effect=OpenAiLiveRefused("forbidden", "Voice session access denied.")
    )
    payload = LiveOfferRequest(credential="nonce-" + "n" * 40, sdp="v=0 " + "o" * 20)
    with patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}):
        with pytest.raises(LiveRefusedError) as refused:
            await service.exchange_offer(USER, record.session_id, payload, language="fr")
    assert refused.value.code == "provider_refused"
    assert "forbidden" in str(refused.value.detail)
    kept = await store.get(USER.id)
    assert kept is not None and kept.nonce is None


async def test_an_extension_on_an_offer_provider_moves_the_cap_and_mints_nothing() -> None:
    # No expiring credential on WebRTC: the browser keeps its connection; a
    # reconnection would open a NEW provider session (measured 2026-09-19).
    record = replace(_record(USER.id), provider="openai", model="gpt-live-1")
    service, store, _ = _service(_openai_connector(), record=record)
    provider = _offer_provider()
    with (
        patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}),
        patch(f"{MODULE}.provider_by_id", lambda _pid: provider),
    ):
        extended = await service.extend(USER, record.session_id, language="fr")
    assert extended.credential is None
    assert extended.extensions == 1
    assert extended.expires_at > record.expires_at
    provider.mint.assert_not_awaited()
    kept = await store.get(USER.id)
    assert kept is not None and kept.expires_at == extended.expires_at


async def test_a_reconnection_on_an_offer_provider_writes_a_fresh_nonce() -> None:
    record = replace(_record(USER.id), provider="openai", model="gpt-live-1")
    service, store, _ = _service(_openai_connector(), record=record)
    provider = _offer_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gpt_live": provider}):
        minted = await service.renew_credential(USER, record.session_id, language="fr")
    assert minted.connection == "offer"
    kept = await store.get(USER.id)
    assert kept is not None and kept.nonce == minted.credential


async def test_a_reconnection_mints_on_the_sessions_provider_not_the_current_choice() -> None:
    # A switch made mid-session must not reconnect elsewhere.
    service, _, _ = _service(_connector(), record=_record(USER.id))
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        await service.renew_credential(USER, "s" * 32, language="fr")
    provider.mint.assert_awaited_once()


# -- trace ---------------------------------------------------------------------


async def test_a_turn_of_another_session_is_not_found() -> None:
    service, _, _ = _service(_connector(), record=_record(USER.id))
    with pytest.raises(LiveRefusedError) as refusal:
        await service.archive_turn(
            USER,
            "z" * 32,
            LiveTurnRequest(user_text="hi", started_at=_now(), ended_at=_now()),
            language="fr",
        )
    assert refusal.value.status_code == 404 and refusal.value.code == "session_not_found"


async def test_a_turn_archives_one_row_per_role_bounded() -> None:
    service, _, archive = _service(_connector(), record=_record(USER.id))
    response = await service.archive_turn(
        USER,
        "s" * 32,
        LiveTurnRequest(
            user_text="x" * 9000, assistant_text="ok", started_at=_now(), ended_at=_now()
        ),
        language="fr",
    )
    assert response.user_message_id and response.assistant_message_id
    roles = [call.kwargs["role"] for call in archive.call_args_list]
    assert roles == ["user", "assistant"]
    assert len(archive.call_args_list[0].kwargs["content"]) <= 4000
    assert archive.call_args_list[0].kwargs["metadata"]["type"] == "live_turn"


async def test_end_archives_a_summary_releases_records_and_learns() -> None:
    record = _record(USER.id)
    service, store, archive = _service(_connector(), record=record)
    usage = LiveUsage(
        tokens_in=1, tokens_out=2, tokens_cache=0, cost_eur=0.5, google_api_requests=0
    )
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=["r1", "r2"])),
        patch(
            f"{CLOSING}.session_voice_rows",
            AsyncMock(return_value=[("user", "a"), ("assistant", "b")]),
        ),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=3)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=usage)),
        patch(f"{CLOSING}.record_decision", AsyncMock()) as decision,
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()) as learning,
    ):
        response = await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    assert response.usage and response.usage.cost_eur == 0.5
    assert response.duration_seconds >= 290
    # The card's figures are the ROWS' (two delegated runs, three exchanges),
    # never a claim of the client (ADR-185).
    assert (response.delegations, response.voice_turns) == (2, 3)
    assert archive.call_args.kwargs["metadata"]["live_summary"]["delegations"] == 2
    assert archive.call_args.kwargs["role"] == "assistant"
    assert archive.call_args.kwargs["metadata"]["type"] == "live_session_summary"
    content = archive.call_args.kwargs["content"]
    assert "0.5000" in content
    # The Markdown fallback names how the session ended, in the person's language.
    assert content.startswith("**Session live** — terminée par toi · ")
    store.release.assert_awaited_once_with(USER.id, "tok")
    store.unregister_active.assert_awaited_once_with("s" * 32)
    recorded = decision.call_args.args[0]
    assert recorded.route == "live_session" and recorded.outcome.value == "answered"
    assert learning.call_args.kwargs["rows"] == [("user", "a"), ("assistant", "b")]
    assert learning.call_args.kwargs["run_id"] == record.run_id


async def test_end_on_an_error_records_an_interrupted_decision() -> None:
    service, _, _ = _service(_connector(), record=_record(USER.id))
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{CLOSING}.record_decision", AsyncMock()) as decision,
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()),
    ):
        response = await service.end(USER, "s" * 32, LiveEndRequest(outcome="error"), language="fr")
    assert response.usage is None
    assert decision.call_args.args[0].outcome.value == "interrupted"


async def test_end_reports_the_extensions_on_the_card() -> None:
    record = LiveSessionRecord(**{**record_fields(_record(USER.id)), "extensions": 2})
    service, _, archive = _service(_connector(), record=record)
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()),
    ):
        response = await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    assert response.extensions == 2
    metadata = archive.call_args.kwargs["metadata"]
    assert metadata["live_summary"]["extensions"] == 2
    # The Markdown fallback says it too, in the person's language.
    assert (
        get_live_phrases("fr")["summary_extended"].format(count=2)
        in archive.call_args.kwargs["content"]
    )


async def test_end_twice_is_not_found_the_second_time() -> None:
    service, _, _ = _service(_connector(), record=None)
    with pytest.raises(LiveRefusedError) as refusal:
        await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    # Coded and translated like every other refusal: the client reads the code.
    assert refusal.value.status_code == 404 and refusal.value.code == "session_not_found"
    assert refusal.value.detail["message"] == get_live_phrases("fr")["session_not_found"]
