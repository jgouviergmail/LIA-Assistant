"""The phone's live lookups, held exactly in the person's ElevenLabs workspace (lots 7-8).

The vendor holds every live lookup a connector may offer as a WEBHOOK tool, and
an owner call attaches its own subset (``TelephonyService._arm_agent_tools``).
This module only makes the workspace hold them, exactly: remembered by
fingerprint, created whole, and held against what the workspace serves before
every owner call — a tool edited on the portal is rewritten in place, a lost one
re-created and recorded (owner decision 2026-11-11: never an agent with tools
out of date or incomplete), through the door the live sessions share
(``telephony/workspace_tools.py``). The rule that derives the set, the bodies the
vendor is sent and the execution stay in ``live_tools.py``, read through its
module so the doors the tests replace there serve here too.

Extracted from ``live_tools.py``, which is size-capped.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

from src.domains.agents.telephony import live_tools
from src.domains.telephony.client import ElevenLabsAgentsClient
from src.domains.telephony.live_tools import (
    LiveToolBinding,
    live_tool_token,
    live_tools_fingerprint,
)
from src.domains.telephony.workspace_tools import (
    VENDOR_FAILURES,
    create_tools,
    read_workspace_tools,
    repair_set,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.agents.telephony.live_specs import LiveToolSpec

logger = structlog.get_logger(__name__)


async def ensure_vendor_live_tools(
    db: AsyncSession,
    *,
    connector: Any,
    api_key: str,
    api_secret: str,
    client_factory: Callable[[str], ElevenLabsAgentsClient] | None = None,
) -> tuple[LiveToolBinding, ...] | None:
    """Make sure the vendor holds every live tool this connector may offer, exactly.

    Remembered by fingerprint: on drift the new tools are created first
    (concurrently, all or nothing — ``workspace_tools.create_tools``), the old
    ones deleted after (forced), and the metadata committed — a NEW dict, never
    a mutation (the JSONB rule). A set already recorded is held against what
    the workspace serves before every owner call (owner decision 2026-11-11:
    never an agent with tools out of date or incomplete): a tool edited on the
    portal is rewritten in place, a lost one re-created and recorded. The
    person's own domain switches are applied by the caller on the bindings:
    the vendor holds the whole set, one call attaches its subset.

    Args:
        db: Session the connector row is committed on.
        connector: The active telephony connector.
        api_key: The person's vendor key.
        api_secret: The connector's webhook secret, which the token derives from.
        client_factory: Test seam for the vendor client.

    Returns:
        The bindings the dial may attach; empty when nothing is offered; None
        when the vendor refused or the workspace could not be read — the owner
        call is then refused, never dialled without its tools.
    """
    specs = await live_tools.available_live_tools()
    if not specs:
        return ()
    bodies = live_tools.vendor_bodies(specs, token=live_tool_token(api_secret))
    fingerprint = live_tools_fingerprint(bodies)
    metadata: dict[str, Any] = dict(connector.connector_metadata or {})
    stored: dict[str, Any] = metadata.get(live_tools.METADATA_IDS) or {}
    client = (client_factory or ElevenLabsAgentsClient)(api_key)
    recorded = metadata.get(live_tools.METADATA_HASH) == fingerprint
    if recorded and all(s.name in stored for s in specs):
        ids = await _verified_ids(db, connector, client, specs, bodies)
    else:
        ids = await _provisioned_ids(db, connector, client, specs, bodies, fingerprint)
    if ids is None:
        return None
    return tuple(
        LiveToolBinding(s.name, tool_id, s.domain) for s, tool_id in zip(specs, ids, strict=True)
    )


async def _verified_ids(
    db: AsyncSession,
    connector: Any,
    client: ElevenLabsAgentsClient,
    specs: tuple[LiveToolSpec, ...],
    bodies: list[dict[str, Any]],
) -> tuple[str, ...] | None:
    """The recorded set held against the workspace's webhook tools; None when it cannot be.

    A lost tool re-created is recorded at once (a NEW dict, committed), so the
    next call holds the tool this one attaches.
    """
    metadata: dict[str, Any] = dict(connector.connector_metadata or {})
    stored: dict[str, Any] = metadata.get(live_tools.METADATA_IDS) or {}
    try:
        served = await read_workspace_tools(client, "webhook")
        repair = await repair_set(
            client, [str(stored[s.name]) for s in specs], bodies, served, surface="phone"
        )
    except VENDOR_FAILURES as exc:
        logger.warning("telephony_live_tools_unverified", error_type=type(exc).__name__)
        return None
    if repair.recreated:
        renewed = {s.name: tool_id for s, tool_id in zip(specs, repair.ids, strict=True)}
        connector.connector_metadata = {
            **metadata,
            live_tools.METADATA_IDS: {**stored, **renewed},
        }
        await db.commit()
    return repair.ids


async def _provisioned_ids(
    db: AsyncSession,
    connector: Any,
    client: ElevenLabsAgentsClient,
    specs: tuple[LiveToolSpec, ...],
    bodies: list[dict[str, Any]],
    fingerprint: str,
) -> tuple[str, ...] | None:
    """A new set created whole, the old one deleted, the new one recorded; None on a failure."""
    metadata: dict[str, Any] = dict(connector.connector_metadata or {})
    stored: dict[str, Any] = metadata.get(live_tools.METADATA_IDS) or {}
    try:
        created_ids = await create_tools(client, bodies)
    except VENDOR_FAILURES as exc:
        logger.warning("telephony_live_tools_provisioning_failed", error_type=type(exc).__name__)
        return None
    created = {s.name: tool_id for s, tool_id in zip(specs, created_ids, strict=True)}
    for old_id in stored.values():
        await client.delete_tool(str(old_id))
    connector.connector_metadata = {
        **metadata,
        live_tools.METADATA_IDS: created,
        live_tools.METADATA_HASH: fingerprint,
    }
    await db.commit()
    logger.info("telephony_live_tools_provisioned", count=len(created))
    return tuple(created_ids)


__all__ = ["ensure_vendor_live_tools"]
