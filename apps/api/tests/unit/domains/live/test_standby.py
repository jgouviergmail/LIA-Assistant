"""The live standby (ADR-329): asleep, nothing is connected nor billed; a wake reopens it.

Run against the REAL session store on a fake Redis — the atomic drain, the
lives of the keys and the instance count are what these tests are about — with
the provider, the connector and the relay scheduling as doubles.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.domains.live.errors import LiveRefusedError
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import setup_inputs_to_dict
from src.domains.live.providers.protocol import (
    LiveCredential,
    LiveModelCapabilities,
    LiveSetupInputs,
)
from src.domains.live.schemas import (
    LiveEndRequest,
    LiveOfferRequest,
    LiveStandbyRequest,
    LiveToolCallRequest,
    LiveTurnRequest,
    LiveWakeRequest,
)
from src.domains.live.service import LiveService
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from tests.unit.domains.live.conftest import CLOSING_ARCHIVE
from tests.unit.domains.live.fakes import FakeRedis

pytestmark = pytest.mark.unit

STANDBY = "src.domains.live.standby"
CLOSING = "src.infrastructure.scheduler.voice_session_closing"
SERVICE = "src.domains.live.service"
END = "src.domains.live.session_end"

USER = SimpleNamespace(
    id=uuid.uuid4(),
    language="fr",
    timezone="Europe/Paris",
    full_name="Alex",
    email="a@x.y",
    live_preferences=None,
    memory_enabled=True,
    phone_disabled_domains=[],
)


def _now() -> datetime:
    return datetime.now(UTC)


def _inputs() -> LiveSetupInputs:
    return LiveSetupInputs(
        model="gemini-3.8-live",
        voice="Kore",
        thinking_level=None,
        system_instruction="mandate rendered at the start",
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


def _record(*, mode: str = "delegated", minutes_left: int = 5) -> LiveSessionRecord:
    started = _now() - timedelta(minutes=5)
    return LiveSessionRecord(
        session_id="s" * 32,
        user_id=USER.id,
        provider="gemini",
        model="gemini-3.8-live",
        run_id="live_session_" + "s" * 32,
        started_at=started,
        expires_at=_now() + timedelta(minutes=minutes_left),
        token="tok",
        setup_inputs=setup_inputs_to_dict(_inputs()),
        mode=mode,
        awake_since=started,
    )


def _provider(*, connection: str = "token", fails: bool = False) -> MagicMock:
    provider = MagicMock()
    provider.provider_id = "gemini"
    provider.connector_type = "gemini_live"
    provider.connection = connection
    provider.delegation_wire = "tool"
    provider.default_model = "gemini-3.8-live"
    provider.billing = "tariff"
    provider.capabilities_of = MagicMock(
        return_value=LiveModelCapabilities(
            async_delegation=True,
            delivery_scheduling=True,
            reports_idle=False,
            cancels_on_interruption=True,
            configurable_vad=True,
            resumes=True,
            thinking=False,
        )
    )
    provider.thinking_levels_of = MagicMock(return_value=())
    provider.knows_voice = MagicMock(return_value=True)
    if fails:
        provider.mint = AsyncMock(side_effect=RuntimeError("vendor down"))
    else:
        provider.mint = AsyncMock(
            side_effect=lambda key, inputs, *, expires_at, connect_deadline_at: LiveCredential(
                "auth_tokens/woken", expires_at, connect_deadline_at
            )
        )
    provider.build_setup = MagicMock(
        side_effect=lambda inputs: {"rendered": inputs.system_instruction}
    )
    return provider


class Harness:
    """A service over the real store, and what the standby handed the relay."""

    def __init__(self, record: LiveSessionRecord | None, *, allowed: bool = True) -> None:
        self.redis = FakeRedis()
        self.store = LiveSessionStore(self.redis)
        db = MagicMock()
        db.commit = AsyncMock()
        self.service = LiveService(db)
        self.service._store = AsyncMock(return_value=self.store)  # type: ignore[method-assign]
        limiter = MagicMock()
        limiter.acquire = AsyncMock(return_value=allowed)
        self.service._limiter = AsyncMock(return_value=limiter)  # type: ignore[method-assign]
        self.service._personality_of = AsyncMock(return_value="")  # type: ignore[method-assign]
        self.service._inner_state_of = AsyncMock(  # type: ignore[method-assign]
            return_value="psyche at the wake"
        )
        self.service._conversation_id = AsyncMock(  # type: ignore[method-assign]
            return_value=uuid.uuid4()
        )
        connector = SimpleNamespace(
            connector_type="gemini_live",
            status="active",
            connector_metadata={"model": "gemini-3.8-live", "voice": "Kore"},
        )
        self.service.connectors.connector_of = AsyncMock(  # type: ignore[method-assign]
            return_value=connector
        )
        self.service.connectors.api_key_of = AsyncMock(  # type: ignore[method-assign]
            return_value="k"
        )
        archive = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
        CLOSING_ARCHIVE["mock"] = archive
        self.relayed: list[Any] = []
        self.record = record

    async def claim(self) -> None:
        assert self.record is not None
        assert await self.store.claim(self.record, ttl_seconds=600)
        await self.store.register_active(self.record.session_id, self.record.expires_at)

    async def standby(self, reason: str = "idle", conversation: str | None = None) -> Any:
        with patch(f"{STANDBY}.schedule_standby_relay", side_effect=self._capture):
            return await self.service.standby(
                USER,
                "s" * 32,
                LiveStandbyRequest(reason=reason, provider_conversation_id=conversation),
                language="fr",
            )

    async def wake(self, provider: MagicMock, reason: str = "wake_word") -> Any:
        with patch(f"{STANDBY}.PROVIDERS", {"gemini_live": provider}):
            return await self.service.wake(
                USER,
                "s" * 32,
                LiveWakeRequest(reason=reason),
                language="fr",
                timezone="Europe/Paris",
                display_name="Alex",
            )

    def _capture(self, session: Any, transcript: Any, *, keep_fate: Any) -> None:
        self.relayed.append((session, transcript, keep_fate))


# -- standby --------------------------------------------------------------------


async def test_a_standby_banks_the_awake_time_and_frees_the_instance_slot() -> None:
    harness = Harness(_record())
    await harness.claim()
    response = await harness.standby("idle", conversation="conv_1")
    asleep = await harness.store.get(USER.id)
    assert asleep is not None and asleep.in_standby and asleep.standbys == 1
    assert asleep.provider_conversation_ids == ("conv_1",)
    assert 299 <= response.awake_seconds <= 301
    assert response.standby_deadline_at == response.standby_since + timedelta(
        seconds=settings.live_standby_max_seconds
    )
    # The slot it does not use is someone else's; the sleep is counted apart.
    assert await harness.store.count_active() == 0
    assert await harness.store.count_standby() == 1
    # The record now lives to the standby bound, not to the frozen cap.
    ttl = harness.redis.ttls[f"live:session:{USER.id}:record"]
    assert ttl >= settings.live_standby_max_seconds
    assert response.relay is None  # a delegated session owes nothing


async def test_a_second_standby_answers_the_same_figures_and_counts_nothing() -> None:
    harness = Harness(_record())
    await harness.claim()
    first = await harness.standby()
    again = await harness.standby("manual")
    assert again.standby_since == first.standby_since
    assert again.awake_seconds == first.awake_seconds
    read = await harness.store.get(USER.id)
    assert read is not None and read.standbys == 1


async def test_a_direct_standby_relays_its_kept_words_once() -> None:
    harness = Harness(_record(mode="direct"))
    await harness.claim()
    await harness.store.append_turns(
        USER.id, [("user", "quelle heure"), ("assistant", "midi")], ttl_seconds=600, max_rows=9
    )
    response = await harness.standby()
    assert response.relay == "scheduled"
    assert len(harness.relayed) == 1
    session, transcript, keep_fate = harness.relayed[0]
    assert session.run_id == "live_session_" + "s" * 32
    assert [turn.text for turn in transcript.turns] == ["quelle heure", "midi"]
    # The rows left the store with the drain: the end will not relay them again.
    assert await harness.store.turns(USER.id) == []
    # The relay's fate is kept for the closing card, in order.
    await keep_fate("answered", None)
    assert await harness.store.relays(USER.id) == [("answered", None)]


async def test_a_direct_standby_with_nothing_said_relays_nothing() -> None:
    harness = Harness(_record(mode="direct"))
    await harness.claim()
    assert (await harness.standby()).relay == "empty"
    assert harness.relayed == []


async def test_a_standby_of_a_session_that_is_not_the_persons_is_not_found() -> None:
    harness = Harness(None)
    with pytest.raises(LiveRefusedError) as raised:
        await harness.standby()
    assert raised.value.status_code == 404


# -- what a sleeping session refuses -----------------------------------------------


async def test_nothing_that_opens_a_connection_is_served_asleep() -> None:
    # A credential, an offer, a lookup or a turn would open — or feed — a
    # provider connection that bills: the wake is the one door back.
    harness = Harness(_record(mode="direct"))
    await harness.claim()
    await harness.standby()
    calls = [
        harness.service.renew_credential(USER, "s" * 32, language="fr"),
        harness.service.exchange_offer(
            USER,
            "s" * 32,
            LiveOfferRequest(credential="c" * 40, sdp="v=0 o=- 1 1 IN IP4 0.0.0.0"),
            language="fr",
        ),
        harness.service.run_tool(
            USER,
            "s" * 32,
            LiveToolCallRequest(name="t", arguments={}),
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
        ),
        harness.service.archive_turn(
            USER,
            "s" * 32,
            LiveTurnRequest(user_text="a", assistant_text="b", started_at=_now(), ended_at=_now()),
            language="fr",
        ),
    ]
    for call in calls:
        with pytest.raises(LiveRefusedError) as raised:
            await call
        assert raised.value.code == "session_standby"


async def test_an_extension_asleep_moves_the_cap_and_mints_nothing() -> None:
    harness = Harness(_record())
    await harness.claim()
    await harness.standby()
    before = await harness.store.get(USER.id)
    assert before is not None
    with patch(f"{SERVICE}.provider_by_id", return_value=_provider()) as provider:
        response = await harness.service.extend(USER, "s" * 32, language="fr")
    assert response.credential is None
    provider.return_value.mint.assert_not_called()
    assert response.expires_at == before.expires_at + timedelta(
        minutes=settings.live_extension_minutes
    )
    # Still asleep: the record keeps living to the standby bound.
    after = await harness.store.get(USER.id)
    assert after is not None and after.in_standby
    assert harness.redis.ttls[f"live:session:{USER.id}:record"] >= settings.live_standby_max_seconds


# -- wake -------------------------------------------------------------------------


async def test_a_wake_shifts_the_cap_and_mints_on_a_setup_rendered_now() -> None:
    harness = Harness(_record())
    await harness.claim()
    await harness.standby()
    asleep = await harness.store.get(USER.id)
    assert asleep is not None
    provider = _provider()
    response = await harness.wake(provider)
    awake = await harness.store.get(USER.id)
    assert awake is not None and not awake.in_standby
    slept = awake.awake_since - asleep.standby_since  # type: ignore[operator]
    assert awake.expires_at == asleep.expires_at + slept
    assert response.expires_at == awake.expires_at
    # The credential lives to the shifted cap, on a setup rendered at the wake.
    assert provider.mint.await_args.kwargs["expires_at"] == awake.expires_at
    assert response.credential.credential == "auth_tokens/woken"
    harness.service._inner_state_of.assert_awaited_with(USER.id, "Europe/Paris")
    assert "psyche at the wake" in str(awake.setup_inputs)
    # Back among the open sessions, out of the sleeping ones.
    assert await harness.store.count_active() == 1
    assert await harness.store.count_standby() == 0


async def test_waking_a_session_that_is_awake_is_refused() -> None:
    harness = Harness(_record())
    await harness.claim()
    with pytest.raises(LiveRefusedError) as raised:
        await harness.wake(_provider())
    assert raised.value.status_code == 409 and raised.value.code == "session_awake"


@pytest.mark.parametrize(
    ("allowed", "busy", "fails", "code"),
    [
        (False, False, False, "mint_rate_limited"),
        (True, True, False, "instance_busy"),
        (True, False, True, "provider_refused"),
    ],
)
async def test_a_refused_wake_leaves_the_session_asleep(
    allowed: bool, busy: bool, fails: bool, code: str
) -> None:
    harness = Harness(_record(), allowed=allowed)
    await harness.claim()
    await harness.standby()
    if busy:
        for index in range(settings.live_max_concurrent_sessions):
            await harness.store.register_active(f"other{index}", _now() + timedelta(minutes=5))
    with pytest.raises(LiveRefusedError) as raised:
        await harness.wake(_provider(fails=fails))
    assert raised.value.code == code
    read = await harness.store.get(USER.id)
    assert read is not None and read.in_standby
    assert await harness.store.count_standby() == 1


async def test_a_wake_past_the_cap_asks_for_the_extension() -> None:
    # A session that went to sleep after its cap (a slow client): the wake is
    # refused as expired, the browser offers the extension and wakes again.
    harness = Harness(_record(minutes_left=-1))
    await harness.claim()
    await harness.standby()
    with pytest.raises(LiveRefusedError) as raised:
        await harness.wake(_provider())
    assert raised.value.code == "session_expired"


async def test_an_offer_wake_keeps_its_single_use_nonce_on_the_record() -> None:
    harness = Harness(_record())
    await harness.claim()
    await harness.standby()
    response = await harness.wake(_provider(connection="offer"))
    read = await harness.store.get(USER.id)
    assert read is not None and read.nonce == response.credential.credential


# -- end --------------------------------------------------------------------------


async def test_the_end_measures_the_time_awake_and_names_the_sleeps() -> None:
    harness = Harness(_record())
    await harness.claim()
    await harness.standby(conversation="conv_1")
    # Three hours asleep.
    asleep = await harness.store.get(USER.id)
    assert asleep is not None
    earlier = replace(
        asleep,
        standby_since=asleep.standby_since - timedelta(hours=3),  # type: ignore[operator]
        started_at=asleep.started_at - timedelta(hours=3),
        awake_since=asleep.started_at - timedelta(hours=3),
    )
    assert await harness.store.extend(earlier, ttl_seconds=600)
    bill = AsyncMock(return_value=None)
    with (
        patch(f"{END}.fetch_vendor_bill", bill),
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()),
    ):
        response = await harness.service.end(
            USER,
            "s" * 32,
            LiveEndRequest(outcome="ended", provider_conversation_id="conv_2"),
            language="fr",
        )
    assert response.duration_seconds == earlier.awake_seconds
    assert response.standbys == 1
    assert response.standby_seconds >= 3 * 3600
    # The vendor's bill is read over every conversation the wires named.
    assert bill.await_args.args[3] == ["conv_1", "conv_2"]
    card = CLOSING_ARCHIVE["mock"].await_args.kwargs["metadata"]["live_summary"]
    assert card["standbys"] == 1
    assert await harness.store.count_standby() == 0
