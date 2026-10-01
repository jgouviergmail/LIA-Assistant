"""The live standby (ADR-329): a session asleep holds no provider connection and bills nothing.

The browser closes the provider connection and says so here; the record stays
claimed, lives to the standby bound instead of its frozen cap, and leaves the
instance count. A wake — the phrase, or the person's button — re-renders the
setup at the wake's instant (the clock, LIA's inner state, the person's current
switches: never the start's), shifts the cap by the length of the sleep, and
mints a fresh credential: one session, many connections beneath it.

A DIRECT session's words since its last wake become the person's own turn at
each standby, as a single session's did at its end (ADR-301): the kept turns
are drained in one command and relayed off the request path, the fate kept for
the closing card. A delegated session owes nothing: its exchanges were archived
as they happened.

Extracted from ``service.py``, which is size-capped; the service routes here
and lends its doors.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import structlog

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, LIVE_DIRECT_TRANSCRIPT_MAX_ROWS
from src.domains.connectors.models import ConnectorType
from src.domains.live.errors import (
    raise_live_instance_busy,
    raise_live_mint_rate_limited,
    raise_live_session_awake,
    raise_live_session_expired,
    raise_live_session_not_found,
)
from src.domains.live.providers import PROVIDERS, setup_inputs_from_dict, setup_inputs_to_dict
from src.domains.live.schemas import (
    LiveStandbyRequest,
    LiveStandbyResponse,
    LiveWakeRequest,
    LiveWakeResponse,
)
from src.domains.live.setup_render import render_setup_inputs
from src.domains.voice_sessions.session import VoiceSession, as_voice_session_mode
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.observability.metrics_live import (
    live_session_standby_total,
    live_session_wakes_total,
    live_sessions_active,
    live_sessions_standby,
)
from src.infrastructure.scheduler.voice_session_closing import schedule_standby_relay

if TYPE_CHECKING:
    from src.domains.live.service import LiveService
    from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)

#: What a standby says of a direct session's words: relayed off the request
#: path, or nothing was said; None for a delegated session.
StandbyRelay = Literal["scheduled", "empty"] | None


def _asleep_response(
    record: LiveSessionRecord, *, relay: StandbyRelay = None
) -> LiveStandbyResponse:
    if record.standby_since is None:
        raise ValueError("a standby response needs a record asleep")
    return LiveStandbyResponse(
        standby_since=record.standby_since,
        awake_seconds=record.awake_seconds,
        standby_deadline_at=record.standby_deadline(settings.live_standby_max_seconds),
        relay=relay,
    )


async def enter_standby(
    service: LiveService,
    user: User,
    session_id: str,
    payload: LiveStandbyRequest,
    *,
    language: str,
) -> LiveStandbyResponse:
    """Put the session to sleep — the browser already closed the provider connection.

    Idempotent: a session already asleep answers the figures of that sleep.
    """
    record = await service._owned_record(user, session_id, language=language)
    if record.in_standby:
        return _asleep_response(record)
    store = await service._store()
    now = datetime.now(UTC)
    asleep = record.entering_standby(now, conversation_id=payload.provider_conversation_id)
    life = asleep.life_seconds(now, standby_max_seconds=settings.live_standby_max_seconds)
    if not await store.extend(asleep, ttl_seconds=life):
        # The claim is a successor's: this session is over for this tab.
        raise_live_session_not_found(language)
    await store.unregister_active(session_id)
    await store.register_standby(
        session_id, asleep.standby_deadline(settings.live_standby_max_seconds)
    )
    relay = await _relay_kept_words(service, store, user, asleep, life, language=language)
    live_sessions_active.set(await store.count_active(now))
    live_sessions_standby.set(await store.count_standby(now))
    live_session_standby_total.labels(provider=record.provider, reason=payload.reason).inc()
    logger.info(
        "live_session_standby",
        session_id=session_id,
        reason=payload.reason,
        awake_seconds=asleep.awake_seconds,
        standbys=asleep.standbys,
    )
    return _asleep_response(asleep, relay=relay)


async def _relay_kept_words(
    service: LiveService,
    store: LiveSessionStore,
    user: User,
    asleep: LiveSessionRecord,
    life: int,
    *,
    language: str,
) -> StandbyRelay:
    """A direct session's words since its last wake, relayed; None for a delegated one."""
    if asleep.mode != "direct":
        return None
    rows = await store.drain_turns(user.id, max_rows=LIVE_DIRECT_TRANSCRIPT_MAX_ROWS)
    if not rows:
        return "empty"
    session = VoiceSession.browser(
        session_id=asleep.session_id,
        run_id=asleep.run_id,
        mode=as_voice_session_mode(asleep.mode),
        user_id=user.id,
        conversation_id=await service._conversation_id(user.id, language=language),
        language=language,
        timezone=str(user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE),
    )

    async def keep_fate(fate: str, recap: str | None) -> None:
        await store.append_relay(user.id, fate, recap, ttl_seconds=life)

    schedule_standby_relay(session, VoiceTranscript.from_rows(rows), keep_fate=keep_fate)
    return "scheduled"


async def wake(
    service: LiveService,
    user: User,
    session_id: str,
    payload: LiveWakeRequest,
    *,
    language: str,
    timezone: str,
    display_name: str,
) -> LiveWakeResponse:
    """Wake a sleeping session: refuse in order, re-render, mint, then write it awake.

    The credential is minted BEFORE the record is written: a refused mint
    leaves the session asleep, exactly as it was, and the person's next wake
    tries again.
    """
    record = await service._owned_record(user, session_id, language=language)

    def refused(outcome: str) -> None:
        live_session_wakes_total.labels(
            provider=record.provider, reason=payload.reason, outcome=outcome
        ).inc()

    if not record.in_standby:
        refused("session_awake")
        raise_live_session_awake(language)
    now = datetime.now(UTC)
    awake = record.waking(now)
    if now >= awake.expires_at:
        # It went to sleep past its cap: the client offers the extension, then wakes.
        refused("session_expired")
        raise_live_session_expired(language)
    if await service._rate_limited(user.id):
        refused("rate_limited")
        raise_live_mint_rate_limited(language)
    store = await service._store()
    if await store.count_active(now) >= settings.live_max_concurrent_sessions:
        refused("instance_busy")
        raise_live_instance_busy(language)
    connector = await service.connectors.connector_of(user, record.provider, language=language)
    connector_type = ConnectorType(connector.connector_type)
    provider = PROVIDERS[connector_type]
    kept = setup_inputs_from_dict(record.setup_inputs)
    inputs = await render_setup_inputs(
        service.connectors,
        provider,
        user,
        service.connectors.settings_for_model(connector, record.model),
        mode=as_voice_session_mode(record.mode),
        language=language,
        timezone=timezone,
        display_name=display_name,
        now=now,
        personality=await service._personality_of(user.id),
        psyche_block=await service._inner_state_of(user.id, timezone),
    )
    # The wire the session opened on stays the session's.
    inputs = replace(inputs, audio_transport=kept.audio_transport)
    api_key = await service.connectors.api_key_of(user.id, connector_type)

    async def _asleep_still() -> None:
        refused("provider_error")

    # An agent-bound provider learns a tool set that changed meanwhile before
    # the credential exists; a vendor refusal leaves the session asleep.
    try:
        await service._sync_agent(provider, connector, api_key, inputs, language=language)
    except Exception:
        refused("provider_error")
        raise
    credential = await service._mint(
        provider,
        api_key,
        inputs,
        expires_at=awake.expires_at,
        language=language,
        on_failure=_asleep_still,
    )
    awake = replace(awake, setup_inputs=setup_inputs_to_dict(inputs))
    if provider.connection == "offer":
        awake = replace(
            awake, nonce=credential.credential, nonce_until=credential.connect_deadline_at
        )
    if not await store.extend(awake, ttl_seconds=awake.remaining_life_seconds(now)):
        raise_live_session_not_found(language)
    await store.unregister_standby(session_id)
    await store.register_active(session_id, awake.expires_at)
    live_sessions_active.set(await store.count_active(now))
    live_sessions_standby.set(await store.count_standby(now))
    live_session_wakes_total.labels(
        provider=record.provider, reason=payload.reason, outcome="ok"
    ).inc()
    logger.info(
        "live_session_woken",
        session_id=session_id,
        reason=payload.reason,
        slept_seconds=int((now - (record.standby_since or now)).total_seconds()),
    )
    return LiveWakeResponse(
        credential=credential, expires_at=awake.expires_at, extensions=awake.extensions
    )


__all__ = ["enter_standby", "wake"]
