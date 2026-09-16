"""The call-back a vendor tool makes during an owner call (lot 7).

``POST /telephony/tools/{tool_name}`` has no session: the vendor's voice
agent calls it while the person is on the line. It lives on the agents side
because running a registered tool needs the runtime context and the tool
registry, which ``telephony`` must not import (the T2 cycle); the telephony
half authorizes the call and counts the budget.

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
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_webhook_signature, raise_not_found_or_unauthorized
from src.core.user_display import resolve_user_display_name
from src.domains.agents.telephony.live_tools import (
    available_live_tools,
    result_lines,
    run_live_tool,
    spec_for,
)
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.telephony.live_tools import (
    CALL_ID_VARIABLE,
    LIVE_TOOL_HEADER,
    LiveToolAuthOutcome,
    authorize_live_tool_call,
    consume_live_tool_budget,
)
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_telephony import telephony_live_tool_calls_total

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
    telephony_live_tool_calls_total.labels(tool=tool, outcome=outcome).inc()


async def _authorized_call(db: AsyncSession, body: dict[str, Any], request: Request) -> Any:
    """The LIVE OWNER call the body names, or a refusal (step 3 above)."""
    auth = await authorize_live_tool_call(
        db,
        call_id_raw=str(body.get(CALL_ID_VARIABLE, "")),
        presented_token=request.headers.get(LIVE_TOOL_HEADER, ""),
    )
    if auth.outcome is LiveToolAuthOutcome.BAD_SECRET:
        _refuse("refused_secret")
        raise_invalid_webhook_signature("telephony")
    if auth.outcome is not LiveToolAuthOutcome.OK or auth.call is None:
        _refuse("refused_call")
        raise_not_found_or_unauthorized(_RESOURCE)
    return auth.call


async def _parse_body(request: Request) -> dict[str, Any] | None:
    try:
        payload = json.loads(await request.body())
    except ValueError, UnicodeDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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

    # The person's own switches hide a domain here exactly as they keep its
    # tools off the agent (lot 8): a tool still attached by a stale PATCH
    # answers « not found » on a domain switched off since.
    spec = spec_for(tool_name)
    offered = await available_live_tools(
        disabled_domains=frozenset(user.phone_disabled_domains or ())
    )
    if spec is None or spec not in offered:
        _refuse("refused_tool")
        logger.info("telephony_live_tool_refused", call_id=str(call.id), reason="tool")
        raise_not_found_or_unauthorized(_RESOURCE)

    admitted = await consume_live_tool_budget(
        await get_redis_cache(),
        call.id,
        limit=settings.telephony_live_tool_max_calls_per_call,
        # The call's duration cap is the portal's (owner decision 2026-09-16):
        # the counter lives as long as a row may stay live before the reaper.
        ttl_seconds=settings.telephony_stale_call_timeout_minutes * 60,
    )
    if not admitted:
        _refuse("budget_exceeded", tool=spec.name)
        logger.info("telephony_live_tool_budget_exceeded", call_id=str(call.id), tool=spec.name)
        return {"result": result_lines()["budget_exhausted"]}

    args = {key: value for key, value in body.items() if key != CALL_ID_VARIABLE}
    text = await run_live_tool(
        spec,
        args,
        user_id=call.user_id,
        language=user.language or settings.default_language,
        timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        display_name=resolve_user_display_name(user.full_name, user.email),
        call_id=call.id,
    )
    return {"result": text}


__all__ = ["live_tool_callback", "router"]
