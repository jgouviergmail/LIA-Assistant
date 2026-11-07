"""What the « Tools » rail shows: one state per tool, read in ONE short session (ADR-369).

A tool is ``ready`` when its category's active provider (or, for Drive and the
Hue bridge, the connector's own row) is usable; ``reconnect_required`` when that
provider broke (``ERROR`` — a deliberate ``REVOKED`` is never nagged about,
ADR-134 V2); ``unavailable`` when the instance withholds every provider of the
tool (the administrator's global switch — no row means enabled); otherwise
``not_connected``, drawn in « To connect » (D6). The gestures and bounds
published are the provider's own (ADR-184).

Everything is read through ``DetachedConnectorService`` in one unit of work,
closed before the answer leaves (ADR-304); the providers themselves are not
called — the rail shows what is connected, not what the provider holds.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from src.core.config import settings
from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.provider_resolver import (
    LEGACY_CONNECTOR_ALIASES,
    resolve_active_connector,
)
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.workbench.features import (
    PROVIDER_BOUNDS,
    PROVIDER_FEATURES,
    TOOL_CATEGORY,
    TOOL_PROVIDERS,
    WorkbenchTool,
)
from src.domains.workbench.schemas.common import (
    ToolAvailability,
    ToolState,
    WorkbenchAvailability,
    WorkbenchLimits,
)


class _ConnectorRow(Protocol):
    """What the rail reads of one connector of the account."""

    connector_type: ConnectorType
    status: ConnectorStatus


async def read_availability(user_id: UUID) -> WorkbenchAvailability:
    """The rail of one account.

    Args:
        user_id: Whose connectors.

    Returns:
        Every tool in rail order, and the bounds every route enforces.
    """
    connectors = DetachedConnectorService()
    async with connectors.unit_of_work() as service:
        listed = await service.get_user_connectors(user_id)
        withheld = {
            config.connector_type
            for config in await service.repository.get_all_global_configs()
            if not config.is_enabled
        }
        active = {
            tool: await resolve_active_connector(user_id, category, service)
            for tool, category in TOOL_CATEGORY.items()
        }
    statuses = connector_statuses(listed.connectors)
    return WorkbenchAvailability(
        tools=[_tool(tool, active.get(tool), statuses, withheld) for tool in WorkbenchTool],
        limits=WorkbenchLimits(
            page_size=listing_page_size(),
            bulk_max_items=settings.workbench_bulk_max_items,
            download_max_bytes=settings.workbench_download_max_bytes,
            upload_max_bytes=settings.workbench_upload_max_bytes,
            calendar_window_max_events=settings.workbench_calendar_window_max_events,
            send_undo_seconds=settings.workbench_send_undo_seconds,
            draft_autosave_seconds=settings.workbench_draft_autosave_seconds,
            search_max_chars=WORKBENCH_MAIL_QUERY_MAX_CHARS,
            assist_text_max_chars=settings.tool_assist_text_max_chars,
            assist_instruction_max_chars=settings.tool_assist_instruction_max_chars,
        ),
    )


def listing_page_size() -> int:
    """One page of every listing: the setting, under the ceiling every client applies."""
    return min(settings.workbench_page_size, settings.api_max_items_per_request)


def connector_statuses(connectors: Iterable[_ConnectorRow]) -> dict[ConnectorType, ConnectorStatus]:
    """Each connector's status by its canonical type (legacy aliases resolved)."""
    return {
        ConnectorType(LEGACY_CONNECTOR_ALIASES.get(row.connector_type, row.connector_type)): (
            ConnectorStatus(row.status)
        )
        for row in connectors
    }


def broken_provider(
    tool: WorkbenchTool, statuses: dict[ConnectorType, ConnectorStatus]
) -> ConnectorType | None:
    """The tool's provider stuck in ``ERROR``, if any (never a revoked one)."""
    return next(
        (
            kind
            for kind in sorted(TOOL_PROVIDERS[tool], key=lambda k: k.value)
            if statuses.get(kind) == ConnectorStatus.ERROR
        ),
        None,
    )


def _tool(
    tool: WorkbenchTool,
    resolved: ConnectorType | None,
    statuses: dict[ConnectorType, ConnectorStatus],
    withheld: set[ConnectorType],
) -> ToolAvailability:
    ready = resolved if tool in TOOL_CATEGORY else _single_active(tool, statuses)
    if ready is not None:
        return ToolAvailability(
            tool=tool,
            state="ready",
            provider=ready.value,
            features=sorted(PROVIDER_FEATURES[ready], key=lambda feature: feature.value),
            bounds=dict(PROVIDER_BOUNDS.get(ready, {})),
        )
    broken = broken_provider(tool, statuses)
    if broken is not None:
        return ToolAvailability(
            tool=tool, state="reconnect_required", provider=broken.value, features=[], bounds={}
        )
    state: ToolState = "unavailable" if TOOL_PROVIDERS[tool] <= withheld else "not_connected"
    return ToolAvailability(tool=tool, state=state, provider=None, features=[], bounds={})


def _single_active(
    tool: WorkbenchTool, statuses: dict[ConnectorType, ConnectorStatus]
) -> ConnectorType | None:
    """The tool's one connector when its row is active (Drive, the Hue bridge)."""
    return next(
        (kind for kind in TOOL_PROVIDERS[tool] if statuses.get(kind) == ConnectorStatus.ACTIVE),
        None,
    )
