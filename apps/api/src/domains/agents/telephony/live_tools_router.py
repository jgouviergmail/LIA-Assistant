"""The call-backs a vendor tool makes during an owner call (lot 7, ADR-301).

``POST /telephony/tools/{tool_name}`` has no session: the vendor's voice
agent calls it while the person is on the line. It lives on the agents side
because running a registered tool needs the runtime context and the tool
registry, which ``telephony`` must not import (the T2 cycle); the telephony
half authorizes the call and counts the budget.

``POST /telephony/tools/send_to_lia`` is the Live mode's ONE tool (ADR-301):
declared BEFORE the generic route so the name is never read as a lookup. It
answers for a LIVE OWNER call that RUNS delegated — the row's own mode, never
the person's current choice — and hands the request to the server-side
bridge, which runs it as the person's own chat turn and gives back what the
voice can say. No flag: the mode on the row is the switch.

The order is the security, and every refusal short of a wrong secret on a
known call reads as « not found »:

1. the feature flag — off, the route does not exist;
2. the body parses and carries the ``call_id`` the dial injected;
3. the call is a LIVE OWNER call and the derived token matches — a stranger's
   call, a finished call, an unknown id all read alike, a wrong secret on a
   qualifying call is a security event (403, counted);
4. the tool is on the derived list AND currently offered — a capability
   switched off, or a domain the PERSON switched off, hides it here exactly
   as it keeps it off the agent;
5. the call's budget of lookups admits one more — exhausted, the agent hears
   a sentence, not an error;
6. the tool runs for the person and its text is returned.

Steps 4 to 6 are the shared admission of every voice lookup
(``voice_lookup.serve_voice_lookup``, the browser's session door runs the
same); this door hands it the offered set under the telephony flag, the
call's own budget, and says a refusal the vendor's way.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    CHAT_MESSAGE_MAX_LENGTH,
    DEFAULT_USER_DISPLAY_TIMEZONE,
    LIVE_DELEGATION_TOOL_NAME,
)
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_webhook_signature, raise_not_found_or_unauthorized
from src.core.user_display import resolve_user_display_name
from src.domains.agents.telephony.live_tools import (
    SURFACE,
    VoiceToolHost,
    available_live_tools,
    result_lines,
)
from src.domains.agents.telephony.voice_lookup import LookupRefusal, serve_voice_lookup
from src.domains.conversations.service import ConversationService
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.telephony.delegation_tool import delegation_wait_seconds
from src.domains.telephony.live_tools import (
    CALL_ID_VARIABLE,
    LIVE_TOOL_HEADER,
    LiveToolAuthOutcome,
    authorize_live_tool_call,
    consume_live_tool_budget,
)
from src.domains.users.models import User
from src.domains.voice_sessions.mandate import bridge_lines
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_telephony import (
    telephony_delegation_duration_seconds,
    telephony_delegations_total,
    telephony_live_tool_calls_total,
)
from src.infrastructure.scheduler.out_of_turn_run import resolve_run_context
from src.infrastructure.scheduler.voice_delegation import DelegationRequest, delegate

logger = get_logger(__name__)

#: The resource named in a refusal — one word, never the tool.
_RESOURCE = "phone_call"
#: The tool label of a refusal that happens before a tool is resolved.
_UNKNOWN_TOOL = "unknown"

router = APIRouter(
    prefix="/telephony/tools",
    tags=["Telephony"],
    dependencies=capability_dependencies(PlatformCapability.TELEPHONY),
)


def _refuse(outcome: str, *, tool: str = _UNKNOWN_TOOL) -> None:
    telephony_live_tool_calls_total.labels(tool=tool, outcome=outcome, surface=SURFACE).inc()


async def _authorized_call(
    db: AsyncSession,
    body: dict[str, Any],
    request: Request,
    *,
    counter: Callable[[str], None] = _refuse,
) -> Any:
    """The LIVE OWNER call the body names, or a refusal (step 3 above).

    Args:
        db: Request session.
        body: The parsed vendor body.
        request: The vendor's request (the secret header).
        counter: Which family counts the refusal — a lookup's or a delegation's.
    """
    auth = await authorize_live_tool_call(
        db,
        call_id_raw=str(body.get(CALL_ID_VARIABLE, "")),
        presented_token=request.headers.get(LIVE_TOOL_HEADER, ""),
    )
    if auth.outcome is LiveToolAuthOutcome.BAD_SECRET:
        counter("refused_secret")
        raise_invalid_webhook_signature("telephony")
    if auth.outcome is not LiveToolAuthOutcome.OK or auth.call is None:
        counter("refused_call")
        raise_not_found_or_unauthorized(_RESOURCE)
    return auth.call


async def _parse_body(request: Request) -> dict[str, Any] | None:
    try:
        payload = json.loads(await request.body())
    except ValueError, UnicodeDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _refuse_delegation(outcome: str) -> None:
    telephony_delegations_total.labels(outcome=outcome).inc()


@router.post(
    f"/{LIVE_DELEGATION_TOOL_NAME}",
    include_in_schema=False,
    summary="The Live mode's delegation call-back of an owner call (ADR-301)",
)
async def delegation_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Hand the person's request to LIA and answer what the voice can say.

    Args:
        request: The vendor's request (JSON body: ``call_id``, ``request``;
            the secret header).
        db: Request session.

    Returns:
        ``{"result": <text>}`` plus ``"tone"`` when the answer carries a
        delivery note (ADR-253) — the browser's function response, verbatim.
    """
    body = await _parse_body(request)
    if body is None:
        _refuse_delegation("refused_call")
        raise_not_found_or_unauthorized(_RESOURCE)
    call = await _authorized_call(db, body, request, counter=_refuse_delegation)
    if call.call_mode != "delegated":
        # A direct call's agent never carries this tool; a stale attach
        # answers « not found » exactly as a switched-off lookup does.
        _refuse_delegation("refused_mode")
        raise_not_found_or_unauthorized(_RESOURCE)
    text = body.get("request")
    if not isinstance(text, str) or len(text) > CHAT_MESSAGE_MAX_LENGTH:
        _refuse_delegation("refused_request")
        raise_not_found_or_unauthorized(_RESOURCE)
    # The call's own budget — the lookups' counter, which a Live call never
    # spends on lookups: a voice model looping on the function must not buy a
    # graph turn per iteration; the person's ceiling is the last net, not the first.
    admitted = await consume_live_tool_budget(
        await get_redis_cache(),
        call.id,
        limit=settings.telephony_live_tool_max_calls_per_call,
        ttl_seconds=settings.telephony_stale_call_timeout_minutes * 60,
    )
    if not admitted:
        _refuse_delegation("budget_exceeded")
        logger.info("telephony_delegation_budget_exceeded", call_id=str(call.id))
        return {"result": bridge_lines()["budget_exhausted"]}
    context = await resolve_run_context(db, call.user_id)
    if context is None:
        _refuse_delegation("refused_call")
        raise_not_found_or_unauthorized(_RESOURCE)
    conversation = await ConversationService().get_or_create_conversation(
        call.user_id, db, language=context.language
    )
    session = VoiceSession.phone(
        call_id=call.id,
        mode="delegated",
        user_id=call.user_id,
        conversation_id=conversation.id,
        language=context.language,
        timezone=context.timezone,
    )
    started = time.monotonic()
    result = await delegate(
        DelegationRequest(
            session=session,
            # The vendor's body names no id of its own: one is minted here, and
            # the newest-wins marker holds it.
            request_id=uuid.uuid4().hex,
            request=text,
            spoken_text=None,
            wait_seconds=delegation_wait_seconds(),
        ),
        context=context,
    )
    telephony_delegation_duration_seconds.observe(time.monotonic() - started)
    telephony_delegations_total.labels(outcome=result.outcome.value).inc()
    logger.info("telephony_delegation_answered", call_id=str(call.id), outcome=result.outcome.value)
    answer = {"result": result.text}
    if result.note:
        answer["tone"] = result.note
    return answer


@router.post(
    "/{tool_name}", include_in_schema=False, summary="Live tool call-back of an owner call"
)
async def live_tool_callback(
    tool_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Run one allow-listed read tool for the person on the line.

    Args:
        tool_name: The last segment of the route — the tool's registry name.
        request: The vendor's request (JSON body, secret header).
        db: Request session.

    Returns:
        ``{"result": <text the voice agent reads>}``.
    """
    if not settings.telephony_live_tools_enabled:
        _refuse("refused_flag")
        raise_not_found_or_unauthorized(_RESOURCE)
    body = await _parse_body(request)
    if body is None:
        _refuse("refused_call")
        raise_not_found_or_unauthorized(_RESOURCE)
    call = await _authorized_call(db, body, request)
    user = await db.get(User, call.user_id)
    if user is None:
        _refuse("refused_call")
        raise_not_found_or_unauthorized(_RESOURCE)

    async def _consume_budget() -> bool:
        return await consume_live_tool_budget(
            await get_redis_cache(),
            call.id,
            limit=settings.telephony_live_tool_max_calls_per_call,
            # The call's duration cap is the portal's (owner decision 2026-09-16):
            # the counter lives as long as a row may stay live before the reaper.
            ttl_seconds=settings.telephony_stale_call_timeout_minutes * 60,
        )

    # The person's own switches hide a domain here exactly as they keep its
    # tools off the agent (lot 8): a tool still attached by a stale PATCH
    # answers « not found » on a domain switched off since.
    verdict = await serve_voice_lookup(
        tool_name,
        {key: value for key, value in body.items() if key != CALL_ID_VARIABLE},
        offered=await available_live_tools(
            disabled_domains=frozenset(user.phone_disabled_domains or ())
        ),
        consume_budget=_consume_budget,
        user_id=call.user_id,
        language=user.language or settings.default_language,
        timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        display_name=resolve_user_display_name(user.full_name, user.email),
        host=VoiceToolHost.phone_call(call.id),
    )
    if verdict.refusal is LookupRefusal.NOT_OFFERED:
        _refuse(verdict.refusal.value)
        logger.info("telephony_live_tool_refused", call_id=str(call.id), reason="tool")
        raise_not_found_or_unauthorized(_RESOURCE)
    if verdict.refusal is LookupRefusal.BUDGET:
        tool = verdict.spec.name if verdict.spec is not None else _UNKNOWN_TOOL
        _refuse(verdict.refusal.value, tool=tool)
        logger.info("telephony_live_tool_budget_exceeded", call_id=str(call.id), tool=tool)
        return {"result": result_lines()["budget_exhausted"]}
    return {"result": verdict.text}


__all__ = ["delegation_callback", "live_tool_callback", "router"]
