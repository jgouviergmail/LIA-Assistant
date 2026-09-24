"""Live read-only tools on an owner call — the telephony half (lot 7).

During a call with the account holder, the vendor's voice agent may look
something up in LIA: the vendor calls a **webhook tool** back on this API,
which runs a read-only capability for the person and answers in plain text.
This module holds everything that side needs and that ``agents`` must not own
(the T2 cycle: ``telephony`` never imports ``agents``):

- the **token** a vendor tool presents, derived from the connector's webhook
  secret and never equal to it — the secret authenticates the post-call
  webhook by HMAC and must not travel as a bearer to a third party's config;
- the public **URL** a tool calls back on;
- the vendor **tool body**, built from ONE declaration of the parameters a
  tool exposes (the agents half declares them, this half serialises them);
- a **fingerprint** of the whole set, so a drift (a wording, a rotated secret,
  a new host) re-provisions the tools before the next owner call;
- the **authorization** of a call-back: an active OWNER call — a stranger's
  call, a finished call, an unknown or malformed id all read the same way, and
  the secret is compared only once the call qualifies;
- a per-call **budget** of lookups, keyed by the call and dying with it;
- the **attachment** of the tools to the agent for the owner's call, and their
  detachment after it. Measured on a real owner call 2026-09-16: the vendor
  refuses tool ids inside a per-call override (« Tool IDs not attached to
  this agent ») and the call dies at pickup, so the ids are PATCHed on the
  agent before the owner is dialled and removed once the call is over — the
  connector remembers which state the agent is in, so a stranger is never
  phoned by an agent still carrying the owner's tools.

The agents half (``domains/agents/telephony/live_tools.py``) composes these
into provisioning and execution.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_TELEPHONY_LIVE_TOOL_PREFIX
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.callback import callback_base_url
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.models import CallKind, PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.connectors.models import Connector

logger = structlog.get_logger(__name__)

#: The header a vendor tool presents the derived token in.
LIVE_TOOL_HEADER: Final = "X-LIA-Tool-Secret"
#: The dynamic variable the dial path injects and the tool body binds.
CALL_ID_VARIABLE: Final = "call_id"
#: Statuses under which a call is on the line.
_LIVE_STATUSES: Final = frozenset({PhoneCallStatus.DIALING, PhoneCallStatus.IN_PROGRESS})
#: The label the token is derived under — a different purpose derives a
#: different token from the same secret.
_TOKEN_LABEL: Final = b"lia-telephony-live-tools"
#: Grace past the stale-call timeout: the vendor may deliver a last tool call
#: while it is wrapping the conversation up.
_AGE_GRACE: Final = timedelta(seconds=60)
#: The connector metadata key remembering whether the agent currently carries
#: the owner's live tools.
LIVE_TOOLS_ATTACHED_KEY: Final = "live_tools_attached"
#: What the vendor schema says of one item of an array parameter (technical
#: English, read by the vendor's model — ADR-256).
ARRAY_ITEM_DESCRIPTION: Final = "One value."


@dataclass(frozen=True)
class LiveToolParameter:
    """One parameter a live tool exposes to the voice agent.

    Attributes:
        name: The parameter as the tool's own signature names it.
        type: A JSON schema type (``string``, ``integer``, ``number``,
            ``boolean`` or ``array``).
        description: What the model reads.
        required: Whether the vendor must send it.
        enum: A closed set of values, or None.
        items_type: The scalar type of an ``array``'s items, else None.
            Measured 2026-09-16: the vendor refuses an array whose items
            carry no description, so the body always writes one.
    """

    name: str
    type: str
    description: str
    required: bool
    enum: tuple[str, ...] | None = None
    items_type: str | None = None


@dataclass(frozen=True)
class LiveToolBinding:
    """A provisioned vendor tool: the capability's name and the vendor's id.

    Attributes:
        name: The registry name of the tool (also the route's last segment).
        vendor_id: The id the vendor gave the webhook tool.
        domain: The domain the tool reads (lot 8) — what the person's own
            switches decide on, and what the owner prompt names.
    """

    name: str
    vendor_id: str
    domain: str


class LiveToolAuthOutcome(str, Enum):
    """What the authorization of a call-back concluded."""

    OK = "ok"
    UNKNOWN_CALL = "unknown_call"
    BAD_SECRET = "bad_secret"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class LiveToolAuth:
    """The verdict, and the call when it is positive.

    Attributes:
        outcome: The verdict.
        call: The owner call the lookup belongs to; None unless ``OK``.
    """

    outcome: LiveToolAuthOutcome
    call: PhoneCall | None = None


def live_tool_token(api_secret: str) -> str:
    """Derive the call-back token from the connector's webhook secret.

    Args:
        api_secret: The connector's post-call webhook HMAC secret.

    Returns:
        A hex digest; deterministic, so the endpoint recomputes it rather than
        storing a second credential.
    """
    return hmac.new(api_secret.encode("utf-8"), _TOKEN_LABEL, hashlib.sha256).hexdigest()


def live_tool_url(tool_name: str) -> str:
    """The public URL the vendor calls a tool back on.

    Args:
        tool_name: The registry name of the tool.

    Returns:
        ``{callback base}{API_PREFIX}/telephony/tools/{tool_name}`` — the base
        being ``TELEPHONY_CALLBACK_BASE_URL`` when declared, else ``API_URL``
        (``callback.callback_base_url``, ONE reader for the two tool kinds).
    """
    return f"{callback_base_url()}{settings.api_prefix}/telephony/tools/{tool_name}"


def webhook_tool_body(
    *,
    name: str,
    description: str,
    url: str,
    token: str,
    parameters: Sequence[LiveToolParameter],
    timeout_seconds: int,
    asynchronous: bool = False,
) -> dict[str, Any]:
    """The vendor's ``POST /convai/tools`` body for one live tool.

    Shape measured 2026-09-16 on the production workspace: ``tool_config`` of
    type ``webhook`` with an ``api_schema`` whose ``request_body_schema``
    binds ``call_id`` to the dial path's dynamic variable. An ASYNCHRONOUS
    tool (measured 2026-09-20, ADR-301 lot 0: ``execution_mode: async`` and
    ``pre_tool_speech: force``) lets the voice announce the call in one
    sentence and keep talking while the result is on its way — the shape of
    the Live mode's delegation.

    Args:
        name: The tool's name (the vendor shows it to its model).
        description: What the model reads to decide when to call it.
        url: Where the vendor posts.
        token: The derived call-back token, sent as a header.
        parameters: The exposed parameters, in order.
        timeout_seconds: The vendor's own timeout on the call-back.
        asynchronous: Whether the voice keeps talking while the tool runs.

    Returns:
        The request body.
    """
    properties: dict[str, Any] = {
        CALL_ID_VARIABLE: {"type": "string", "dynamic_variable": CALL_ID_VARIABLE}
    }
    required = [CALL_ID_VARIABLE]
    for parameter in parameters:
        prop: dict[str, Any] = {"type": parameter.type, "description": parameter.description}
        if parameter.enum:
            prop["enum"] = list(parameter.enum)
        if parameter.type == "array":
            prop["items"] = {
                "type": parameter.items_type or "string",
                "description": ARRAY_ITEM_DESCRIPTION,
            }
        properties[parameter.name] = prop
        if parameter.required:
            required.append(parameter.name)
    config: dict[str, Any] = {
        "type": "webhook",
        "name": name,
        "description": description,
        "response_timeout_secs": timeout_seconds,
    }
    if asynchronous:
        config["execution_mode"] = "async"
        config["pre_tool_speech"] = "force"
    return {
        "tool_config": {
            **config,
            "api_schema": {
                "url": url,
                "method": "POST",
                "request_headers": {LIVE_TOOL_HEADER: token},
                "request_body_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
    }


def live_tools_fingerprint(bodies: Iterable[dict[str, Any]]) -> str:
    """A stable digest of a set of tool bodies, order-independent.

    Args:
        bodies: The vendor bodies of every live tool.

    Returns:
        A short hex digest stored beside the vendor ids; any drift of a body
        (wording, URL, token, timeout) changes it.
    """
    canonical = json.dumps(
        sorted(bodies, key=lambda body: str(body["tool_config"]["name"])),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _is_live_owner_call(call: PhoneCall, *, now: datetime) -> bool:
    """Whether a row is an owner call still plausibly on the line.

    The duration cap is the portal's (owner decision, 2026-09-16), so the
    application cannot read it: the bound is the stale-call timeout the
    reaper already applies to a row whose webhook never came.
    """
    if call.call_kind is not CallKind.SELF or call.status not in _LIVE_STATUSES:
        return False
    started = call.initiated_at
    if started is None:
        return False
    max_age = timedelta(minutes=settings.telephony_stale_call_timeout_minutes) + _AGE_GRACE
    return now - started <= max_age


async def authorize_live_tool_call(
    db: AsyncSession, *, call_id_raw: str, presented_token: str
) -> LiveToolAuth:
    """Decide whether a vendor call-back may run a lookup for a call.

    The order is the security: the call must be a LIVE OWNER call before the
    secret is even looked up, and every refusal short of a wrong secret on a
    qualifying call reads as ``UNKNOWN_CALL`` — nothing tells a caller whether
    an id exists, belongs to a stranger's call, or has ended.

    Args:
        db: Session the call and the connector are read on.
        call_id_raw: The ``call_id`` the vendor echoed from the dial.
        presented_token: The header value the vendor sent.

    Returns:
        The verdict, with the call on ``OK``.
    """
    try:
        call_id = UUID(call_id_raw)
    except ValueError, TypeError:
        return LiveToolAuth(LiveToolAuthOutcome.UNKNOWN_CALL)
    call = await TelephonyRepository(db).get_by_call_id(call_id)
    if call is None or not _is_live_owner_call(call, now=datetime.now(UTC)):
        return LiveToolAuth(LiveToolAuthOutcome.UNKNOWN_CALL)
    creds = await ConnectorService(db).get_api_key_credentials(
        call.user_id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    if creds is None or not creds.api_secret:
        return LiveToolAuth(LiveToolAuthOutcome.NOT_CONFIGURED)
    expected = live_tool_token(creds.api_secret)
    if not hmac.compare_digest(expected.encode("utf-8"), presented_token.encode("utf-8")):
        logger.warning("telephony_live_tool_bad_secret", call_id=str(call.id))
        return LiveToolAuth(LiveToolAuthOutcome.BAD_SECRET)
    return LiveToolAuth(LiveToolAuthOutcome.OK, call=call)


async def consume_live_tool_budget(
    redis: aioredis.Redis, call_id: UUID, *, limit: int, ttl_seconds: int
) -> bool:
    """Count one lookup against the call's budget.

    Args:
        redis: The cache client.
        call_id: The owner call.
        limit: Lookups allowed per call.
        ttl_seconds: How long the counter lives (the call's own cap).

    Returns:
        True when this lookup is within the budget.
    """
    key = f"{REDIS_KEY_TELEPHONY_LIVE_TOOL_PREFIX}{call_id}"
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, ttl_seconds)
    return count <= limit


async def attach_live_tools(
    client: ElevenLabsAgentsClient, connector: Connector, tool_ids: Sequence[str]
) -> bool:
    """Make the agent carry exactly ``tool_ids`` (an empty sequence detaches).

    One PATCH of the agent's ``tool_ids``, then the connector remembers the
    state as a NEW metadata dict (the JSONB rule); the caller commits. On a
    vendor refusal nothing is recorded, so the record stays honest: a failed
    attach leaves the agent tool-less and unmarked, a failed detach leaves
    it marked attached and the next dial retries.

    Args:
        client: The vendor client on the connector's key.
        connector: The active telephony connector (its ``agent_id`` in
            metadata).
        tool_ids: The vendor tool ids, or nothing.

    Returns:
        True when the agent is in the requested state.
    """
    metadata = connector.connector_metadata or {}
    agent_id = str(metadata.get("agent_id") or "")
    ids = list(tool_ids)
    try:
        await client.set_agent_tool_ids(agent_id, ids)
    except ElevenLabsAgentsError as exc:
        logger.warning(
            "telephony_live_tools_attach_failed",
            agent_id=agent_id,
            tool_count=len(ids),
            status_code=exc.status_code,
        )
        return False
    connector.connector_metadata = {**metadata, LIVE_TOOLS_ATTACHED_KEY: bool(ids)}
    return True


def live_tools_attached(connector: Connector) -> bool:
    """Whether the connector's agent currently carries the owner's live tools."""
    return bool((connector.connector_metadata or {}).get(LIVE_TOOLS_ATTACHED_KEY))


async def detach_live_tools(
    db: AsyncSession,
    *,
    user_id: UUID,
    client_factory: Callable[[str], ElevenLabsAgentsClient] | None = None,
) -> bool:
    """Take the owner's live tools off the agent once the owner call is over.

    Best-effort and idempotent: no active connector, or an agent already
    detached, is nothing to do. Commits the connector's new state.

    Args:
        db: Session the connector is read and committed on.
        user_id: The account whose agent carried the tools.
        client_factory: Builds the vendor client from the key (tests).

    Returns:
        True when the agent carries no live tools afterwards.
    """
    connector = await TelephonyConnectorService(db).get_active(user_id)
    if connector is None:
        return False
    if not live_tools_attached(connector):
        return True
    creds = await ConnectorService(db).get_api_key_credentials(
        user_id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    if creds is None or not creds.api_key:
        return False
    # The reads end before the vendor is asked (ADR-304).
    await db.commit()
    client = (client_factory or ElevenLabsAgentsClient)(creds.api_key)
    if not await attach_live_tools(client, connector, ()):
        return False
    await db.commit()
    logger.info("telephony_live_tools_detached", user_id=str(user_id))
    return True


__all__ = [
    "CALL_ID_VARIABLE",
    "LIVE_TOOL_HEADER",
    "LIVE_TOOLS_ATTACHED_KEY",
    "LiveToolAuth",
    "LiveToolAuthOutcome",
    "LiveToolBinding",
    "LiveToolParameter",
    "attach_live_tools",
    "authorize_live_tool_call",
    "consume_live_tool_budget",
    "detach_live_tools",
    "live_tool_token",
    "live_tool_url",
    "live_tools_attached",
    "live_tools_fingerprint",
    "webhook_tool_body",
]
