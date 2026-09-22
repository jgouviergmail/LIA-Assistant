"""The tool door of a DIRECT live session (ADR-300 wave 4, ADR-301).

The phone's door, on the person's own session: ``POST /live/sessions/{id}/tools``
runs ONE read-only lookup the voice asked for. What is this door's own is the
ADMISSION's inputs — the record must be direct, the offered set is the derived
read-only set under the LIVE capability minus the person's switches, the
budget is the session's — and the refusal's transport: every refusal is a
sentence the voice can say. The sequence itself (offered, then the budget,
then the run under the ``live_session`` host) is the shared admission of
every voice lookup (``agents/telephony/voice_lookup``), the phone's call-back
included. Extracted from ``service.py``, which is size-capped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import structlog

from src.core.config import settings
from src.domains.agents.expressivity.activity import capture_activity
from src.domains.agents.telephony.live_tools import VoiceToolHost
from src.domains.agents.telephony.voice_lookup import LookupRefusal, serve_voice_lookup
from src.domains.live.direct_mandate import direct_tool_specs, refusal_line
from src.domains.live.schemas import LiveToolCallRequest, LiveToolCallResponse
from src.infrastructure.observability.metrics_live import live_tool_calls_total

if TYPE_CHECKING:
    from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)

#: The sentence of each refusal, by the line key of ``live_direct_lines.txt``.
_REFUSAL_LINE: Final[dict[LookupRefusal, str]] = {
    LookupRefusal.NOT_OFFERED: "refused_tool",
    LookupRefusal.BUDGET: "budget_exhausted",
}


async def run_session_tool(
    record: LiveSessionRecord,
    store: LiveSessionStore,
    user: User,
    payload: LiveToolCallRequest,
    *,
    language: str,
    timezone: str,
    display_name: str,
) -> LiveToolCallResponse:
    """Run one lookup the voice asked for on the person's own DIRECT session.

    Args:
        record: The session record, already checked to be the person's.
        store: The session store (the lookup budget lives there).
        user: The person.
        payload: The call as the browser relayed it.
        language: Their backend-canonical language.
        timezone: Their IANA zone.
        display_name: What the tools may sign as.

    Returns:
        The projected result, or the refusal the voice says (``ok`` False).
    """
    if record.mode != "direct":
        live_tool_calls_total.labels(provider=record.provider, outcome="refused_mode").inc()
        return LiveToolCallResponse(text=refusal_line("refused_mode"), ok=False)

    async def _consume_budget() -> bool:
        return await store.consume_tool_budget(
            record.session_id,
            limit=settings.live_direct_tool_calls_max,
            ttl_seconds=record.remaining_life_seconds(datetime.now(UTC)),
        )

    with capture_activity(record.run_id) as activity:
        verdict = await serve_voice_lookup(
            payload.name,
            payload.arguments,
            offered=await direct_tool_specs(frozenset(user.phone_disabled_domains or ())),
            consume_budget=_consume_budget,
            user_id=user.id,
            language=language,
            timezone=timezone,
            display_name=display_name,
            host=VoiceToolHost.live_session(record.session_id, record.run_id),
        )
    if verdict.refusal is not None:
        live_tool_calls_total.labels(provider=record.provider, outcome=verdict.refusal.value).inc()
        if verdict.refusal is LookupRefusal.NOT_OFFERED:
            logger.info("live_tool_refused", session_id=record.session_id, tool=payload.name[:64])
        return LiveToolCallResponse(text=refusal_line(_REFUSAL_LINE[verdict.refusal]), ok=False)
    live_tool_calls_total.labels(provider=record.provider, outcome="ok").inc()
    return LiveToolCallResponse(
        text=verdict.text, ok=True, activity=activity[-1] if activity else None
    )


__all__ = ["run_session_tool"]
