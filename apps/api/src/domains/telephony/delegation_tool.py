"""The ONE vendor tool of a Live owner call: ``send_to_lia`` (ADR-301).

In Live mode the voice on the phone holds no lookup of its own: every request
goes through one webhook tool, the same function the browser's live mode
declares to its provider (``LIVE_DELEGATION_TOOL_NAME``, the shared
description and request schema of ``voice_sessions/mandate.py``), and the
server-side bridge turns it into the person's own chat turn. The tool is
ASYNCHRONOUS on the vendor's side (measured 2026-09-20, lot 0): the voice
announces the call in one sentence and keeps the conversation going until the
result comes back — under the vendor's own timeout, which is why the bridge
always answers a few seconds BEFORE it (``telephony_delegation_timeout_seconds``
minus the inner margin).

Provisioned once per connector and remembered by fingerprint beside the live
tools' ids (a NEW metadata dict, never a mutation — the JSONB rule): a drift
of the description (the person's name), the URL, the token or the timeout
re-creates it before the next dial. Attached to the AGENT for the owner's Live
call only, exactly like the live tools of a direct call, and taken off it when
the call ends — a stranger is never phoned by an agent still carrying the
person's delegation.

It lives in ``telephony`` (not ``agents/telephony``) because it needs nothing
of the tool registry: one fixed tool, one fixed schema.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    LIVE_DELEGATION_TOOL_NAME,
    TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS,
)
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.live_tools import (
    LiveToolParameter,
    live_tool_token,
    live_tool_url,
    live_tools_fingerprint,
    webhook_tool_body,
)
from src.domains.voice_sessions.mandate import (
    REQUEST_PARAMETER,
    delegation_request_schema,
    delegation_tool_description,
)

logger = structlog.get_logger(__name__)

#: Connector metadata: the vendor id of the delegation tool, and the
#: fingerprint of the body it was created from.
METADATA_DELEGATION_ID: Final = "delegation_tool_id"
METADATA_DELEGATION_HASH: Final = "delegation_tool_hash"


def _request_parameter() -> LiveToolParameter:
    """The one parameter, copied from the shared schema of the browser's declaration."""
    request = delegation_request_schema()["properties"][REQUEST_PARAMETER]
    return LiveToolParameter(
        name=REQUEST_PARAMETER,
        type=str(request["type"]),
        description=str(request["description"]),
        required=True,
    )


def delegation_tool_body(*, token: str, user_name: str) -> dict[str, Any]:
    """The vendor body of the delegation tool for one connector.

    Args:
        token: The derived call-back token.
        user_name: What the voice calls the person (in the description).

    Returns:
        The ``POST /convai/tools`` body, asynchronous.
    """
    return webhook_tool_body(
        name=LIVE_DELEGATION_TOOL_NAME,
        description=delegation_tool_description(user_name),
        url=live_tool_url(LIVE_DELEGATION_TOOL_NAME),
        token=token,
        parameters=(_request_parameter(),),
        timeout_seconds=settings.telephony_delegation_timeout_seconds,
        asynchronous=True,
    )


def delegation_wait_seconds() -> float:
    """How long the bridge may wait before the vendor's own timeout would fire."""
    return float(
        max(
            1,
            settings.telephony_delegation_timeout_seconds
            - TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS,
        )
    )


async def ensure_vendor_delegation_tool(
    db: AsyncSession,
    *,
    connector: Any,
    api_key: str,
    api_secret: str,
    user_name: str,
    client_factory: Callable[[str], ElevenLabsAgentsClient] | None = None,
) -> str | None:
    """Make sure the vendor holds the delegation tool of this connector.

    Idempotent by fingerprint; on drift the new tool is created first, the old
    one deleted after (forced), and the metadata committed. A vendor refusal
    leaves the dial WITHOUT the tool rather than without a dial — the caller
    then runs the call direct and says so.

    Args:
        db: Session the connector row is committed on.
        connector: The active telephony connector.
        api_key: The person's vendor key.
        api_secret: The connector's webhook secret, which the token derives from.
        user_name: What the voice calls the person.
        client_factory: Test seam for the vendor client.

    Returns:
        The vendor id of the tool, or None when it could not be provisioned.
    """
    body = delegation_tool_body(token=live_tool_token(api_secret), user_name=user_name)
    fingerprint = live_tools_fingerprint([body])
    metadata: dict[str, Any] = dict(connector.connector_metadata or {})
    stored = metadata.get(METADATA_DELEGATION_ID)
    if stored and metadata.get(METADATA_DELEGATION_HASH) == fingerprint:
        return str(stored)

    client = (client_factory or ElevenLabsAgentsClient)(api_key)
    try:
        created = await client.create_tool(body)
    except ElevenLabsAgentsError as exc:
        logger.warning("telephony_delegation_tool_provisioning_failed", status_code=exc.status_code)
        return None
    if stored:
        await client.delete_tool(str(stored))
    connector.connector_metadata = {
        **metadata,
        METADATA_DELEGATION_ID: created,
        METADATA_DELEGATION_HASH: fingerprint,
    }
    await db.commit()
    logger.info("telephony_delegation_tool_provisioned")
    return created


__all__ = [
    "METADATA_DELEGATION_HASH",
    "METADATA_DELEGATION_ID",
    "delegation_tool_body",
    "delegation_wait_seconds",
    "ensure_vendor_delegation_tool",
]
