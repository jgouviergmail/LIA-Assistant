"""Opening a Live session after its discussion reservation has committed."""

from __future__ import annotations

import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import structlog

from src.core.config import settings
from src.core.constants import (
    LIVE_DELEGATION_TOOL_NAME,
    LIVE_DURATION_UNLIMITED,
    LIVE_SESSION_RUN_PREFIX,
    LIVE_TURN_TEXT_MAX_CHARS,
)
from src.core.conversation_execution import ReservedWork
from src.core.conversation_selection import ConversationSelection
from src.domains.connectors.models import Connector, ConnectorType
from src.domains.live.binding import opening_work
from src.domains.live.errors import raise_live_instance_busy, raise_live_session_in_progress
from src.domains.live.providers import LiveProvider, setup_inputs_to_dict
from src.domains.live.schemas import (
    LiveConnectorSettings,
    LiveModelCapabilitiesResponse,
    LiveRates,
    LiveSessionMode,
    LiveSessionStartResponse,
)
from src.domains.live.session_store import LiveSessionRecord
from src.domains.live.setup_render import render_setup_inputs
from src.domains.voice_sessions.expression import expression_of
from src.infrastructure.observability.metrics_live import live_mint_total, live_sessions_active
from src.infrastructure.streaming.live_binding import prepare_live_retirement

if TYPE_CHECKING:
    from src.domains.live.service import LiveService
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)


def live_session_run_id(session_id: str) -> str:
    """The stable accounting key, separate from the LIA business discussion."""
    return f"{LIVE_SESSION_RUN_PREFIX}{session_id}"


async def start_session(
    service: LiveService,
    user: User,
    *,
    language: str,
    timezone: str,
    display_name: str,
    mode: LiveSessionMode,
    audio_transport: Literal["websocket", "webrtc"],
    selection: ConversationSelection,
) -> LiveSessionStartResponse:
    """Close a predecessor before reserving a new target and contacting its provider."""
    connector, provider, chosen, rates = await service._admit(user, mode, language=language)
    await service.db.commit()
    await prepare_live_retirement(user.id)
    previous = await (await service._store()).get(user.id)
    if previous is not None and not await service._supersede(user, previous, language=language):
        raise_live_session_in_progress(language)
    session_id = uuid.uuid4().hex
    async with opening_work(
        service,
        user,
        selection,
        session_id=session_id,
        run_id=live_session_run_id(session_id),
        language=language,
    ) as work:
        return await _open_session(
            service,
            user,
            connector,
            provider,
            chosen,
            rates,
            work,
            session_id=session_id,
            language=language,
            timezone=timezone,
            display_name=display_name,
            mode=mode,
            audio_transport=audio_transport,
        )


async def _open_session(
    service: LiveService,
    user: User,
    connector: Connector,
    provider: LiveProvider,
    chosen: LiveConnectorSettings,
    rates: LiveRates | None,
    work: ReservedWork,
    *,
    session_id: str,
    language: str,
    timezone: str,
    display_name: str,
    mode: LiveSessionMode,
    audio_transport: Literal["websocket", "webrtc"],
) -> LiveSessionStartResponse:
    """All provider effects belong to the already admitted target and opening worker."""
    connector_type = ConnectorType(connector.connector_type)
    capabilities = provider.capabilities_of(chosen.model)
    prefs = service.connectors.preferences(user)
    now = datetime.now(UTC)
    # An unlimited cap (0) rolls by extension slices the client renews without
    # asking; a bounded one is the model's own. Either way the credential and
    # the record live to the cap, never for ever (a key with no TTL is never written).
    cap_minutes = chosen.session_max_minutes or settings.live_extension_minutes
    expires_at = now + timedelta(minutes=cap_minutes)
    api_key = await service.connectors.api_key_of(user.id, connector_type)
    # The credential read ends before the vendor is asked (ADR-304).
    await service.db.commit()
    cue_dialect = await service._expression_of(provider, api_key, chosen.model)
    inputs = await render_setup_inputs(
        service.connectors,
        provider,
        user,
        chosen,
        mode=mode,
        language=language,
        timezone=timezone,
        display_name=display_name,
        now=now,
        personality=await service._personality_of(user.id),
        psyche_block=await service._inner_state_of(user.id, timezone),
        cue_dialect=cue_dialect,
    )
    if provider.provider_id == "elevenlabs" and audio_transport == "webrtc":
        inputs = replace(inputs, audio_transport="webrtc")
    # A provider whose sessions run on the person's AGENT prepares it for
    # THIS setup under the already committed reservation. A known refusal
    # releases the failed opening; an unknown outcome retains it for recovery.
    # The render's reads end before the vendor call (ADR-304).
    await service.db.commit()
    await service._sync_agent(provider, connector, api_key, inputs, language=language)
    record = LiveSessionRecord(
        session_id=session_id,
        user_id=user.id,
        provider=provider.provider_id,
        model=chosen.model,
        run_id=live_session_run_id(session_id),
        started_at=now,
        expires_at=expires_at,
        token=uuid.uuid4().hex,
        setup_inputs=setup_inputs_to_dict(inputs),
        unlimited_cap=chosen.session_max_minutes == LIVE_DURATION_UNLIMITED,
        mode=mode,
        lia_conversation_id=work.admission.target.id,
        lia_conversation_revision=work.admission.target.revision,
        lia_activity_id=work.admission.activity_id,
    )
    store = await service._store()
    ttl_seconds = record.remaining_life_seconds(now)
    if not await store.claim(record, ttl_seconds=ttl_seconds):
        raise_live_session_in_progress(language)
    if await store.count_active(now) >= settings.live_max_concurrent_sessions:
        await store.release(user.id, record.token)
        live_mint_total.labels(provider=provider.provider_id, outcome="instance_busy").inc()
        raise_live_instance_busy(language)

    async def _undo() -> None:
        await store.release(user.id, record.token)

    credential = await service._mint(
        provider,
        api_key,
        inputs,
        expires_at=expires_at,
        language=language,
        on_failure=_undo,
    )
    # Two starts of one account in the same second: the second superseded
    # this record while the credential was being minted. The slot is the
    # other tab's now — count nothing for this one and refuse it honestly.
    current = await store.get(user.id)
    kept = (
        await service._keep_nonce(store, provider, record, credential)
        if current is not None and current.token == record.token
        else None
    )
    if kept is None:
        live_mint_total.labels(provider=provider.provider_id, outcome="session_in_progress").inc()
        raise_live_session_in_progress(language)
    await store.register_active(session_id, expires_at)
    live_sessions_active.set(await store.count_active(now))
    logger.info(
        "live_session_minted", session_id=session_id, provider=provider.provider_id, mode=mode
    )
    return LiveSessionStartResponse(
        **credential.model_dump(),
        session_id=session_id,
        conversation_id=work.admission.target.id,
        conversation_revision=work.admission.target.revision,
        provider=provider.provider_id,
        model=chosen.model,
        run_id=record.run_id,
        mode=mode,
        expression=expression_of(cue_dialect),
        expires_at=expires_at,
        session_max_minutes=chosen.session_max_minutes,
        idle_timeout_seconds=chosen.idle_timeout_seconds,
        standby_max_seconds=settings.live_standby_max_seconds,
        preferences=prefs,
        capabilities=LiveModelCapabilitiesResponse(**asdict(capabilities)),
        delegation_tool_name=LIVE_DELEGATION_TOOL_NAME,
        tool_names=[
            str(tool["name"])
            for tool in (
                [inputs.tool_declaration]
                if inputs.tool_declaration is not None
                else inputs.direct_tools
            )
        ],
        delegation_timeout_seconds=settings.live_delegation_timeout_seconds,
        delegation_result_max_tokens=settings.live_delegation_result_max_tokens,
        turn_text_max_chars=LIVE_TURN_TEXT_MAX_CHARS,
        rates=rates,
        session_budget_eur=chosen.session_budget_eur,
    )
