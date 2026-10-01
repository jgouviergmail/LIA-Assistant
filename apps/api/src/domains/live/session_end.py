"""How a live session closes its books, browser side (ADR-299, ADR-301, ADR-329).

Everything a session owes at its end — the card with EXACT figures, the
decision row, the learning of the voice-only rows — is the carrier-neutral
closing (``voice_session_closing``): the phone's post-call path calls the same
function. What stays here is the browser's own: the record, the claim, the
counts, the metrics and the vendor's bill. A session that slept is measured on
its time AWAKE, names its sleeps, hands the closing the fates of its standbys'
relays, and its vendor bill is read over every conversation its connections
opened. Extracted from ``service.py``, which is size-capped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.live.schemas import LiveEndRequest, LiveEndResponse
from src.domains.live.vendor_bill import fetch_vendor_bill
from src.domains.voice_sessions.session import VoiceSession, as_voice_session_mode
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.observability.metrics_live import (
    live_session_duration_seconds,
    live_sessions_active,
    live_sessions_standby,
    live_sessions_total,
)
from src.infrastructure.scheduler.voice_session_closing import close_voice_session

if TYPE_CHECKING:
    from src.domains.live.service import LiveService
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)


async def end_session(
    service: LiveService,
    user: User,
    session_id: str,
    payload: LiveEndRequest,
    *,
    language: str,
) -> LiveEndResponse:
    """Close the books through the voice session's own policy, then free the slot."""
    record = await service._owned_record(user, session_id, language=language)
    store = await service._store()
    now = datetime.now(UTC)
    # The card, the histogram and the decision measure the time AWAKE (ADR-329).
    duration = record.awake_duration_seconds(now)
    standby_seconds = max(0, int((now - record.started_at).total_seconds()) - duration)
    session = VoiceSession.browser(
        session_id=session_id,
        run_id=record.run_id,
        mode=as_voice_session_mode(record.mode),
        user_id=user.id,
        conversation_id=await service._conversation_id(user.id, language=language),
        language=language,
        timezone=str(user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE),
    )
    direct = record.mode == "direct"
    closed = await close_voice_session(
        service.db,
        session=session,
        memory_enabled=bool(user.memory_enabled),
        outcome=payload.outcome,
        duration_seconds=duration,
        extensions=record.extensions,
        transcript=VoiceTranscript.from_rows(await store.turns(user.id)) if direct else None,
        standbys=record.standbys,
        standby_relays=await store.relays(user.id) if direct else None,
    )
    await store.release(user.id, record.token)
    await store.unregister_active(session_id)
    await store.unregister_standby(session_id)
    live_sessions_active.set(await store.count_active(now))
    live_sessions_standby.set(await store.count_standby(now))
    live_sessions_total.labels(provider=record.provider, outcome=payload.outcome).inc()
    live_session_duration_seconds.observe(duration)
    # The vendor's own bill, read on the person's key and SHOWN — after the
    # books are closed and the slot freed, so a slow vendor delays nothing that
    # matters; never written anywhere (the platform re-bills none of it).
    vendor_bill = await fetch_vendor_bill(
        service.connectors,
        user,
        record,
        [*record.provider_conversation_ids, *filter(None, [payload.provider_conversation_id])],
    )
    logger.info(
        "live_session_ended",
        session_id=session_id,
        outcome=payload.outcome,
        detail=payload.detail,
        audio_diagnostics=(
            payload.audio_diagnostics.model_dump() if payload.audio_diagnostics else None
        ),
        duration_seconds=duration,
        standbys=record.standbys,
        delegations=closed.delegations,
        voice_turns=closed.voice_turns,
    )
    return LiveEndResponse(
        summary_message_id=closed.summary_message_id,
        duration_seconds=duration,
        delegations=closed.delegations,
        voice_turns=closed.voice_turns,
        relay=closed.relay,
        extensions=record.extensions,
        standbys=record.standbys,
        standby_seconds=standby_seconds,
        usage=closed.usage,
        vendor_bill=vendor_bill,
    )


__all__ = ["end_session"]
