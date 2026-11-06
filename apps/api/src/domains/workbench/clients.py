"""Open the provider client of a workbench tool, or refuse with the right code (ADR-369).

A data tool opens its category's active provider through the ADR-304 door; the
Hue bridge opens its own connector by type. Either way no session is held while
the provider answers. When the door names no client, the refusal
tells the person what to do: reconnect a provider that broke, or connect one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import NoReturn
from uuid import UUID

from src.domains.connectors.active_client import (
    ActiveClient,
    ClientUnavailable,
    open_active_client,
    open_client_by_type,
)
from src.domains.connectors.preferences.owner_defaults import OwnerContainer
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.workbench.availability import broken_provider, connector_statuses
from src.domains.workbench.errors import NOT_CONNECTED, RECONNECT_REQUIRED, refuse
from src.domains.workbench.features import TOOL_CATEGORY, TOOL_SINGLE_TYPE, WorkbenchTool


@asynccontextmanager
async def open_tool_client(
    tool: WorkbenchTool, user_id: UUID, *, container: OwnerContainer | None = None
) -> AsyncIterator[ActiveClient]:
    """The open client of ``tool`` for ``user_id``, closed on every path.

    Args:
        tool: The workbench tool.
        user_id: Whose provider.
        container: The owner's default container to read with it, if any
            (a category's only: it travels as ``preferred_name``).

    Yields:
        The open client and the connector type that answered.

    Raises:
        BaseAPIException: ``reconnect_required`` when the tool's provider broke,
            ``not_connected`` otherwise.
    """
    door = (
        open_active_client(TOOL_CATEGORY[tool], user_id, container=container)
        if tool in TOOL_CATEGORY
        else open_client_by_type(TOOL_SINGLE_TYPE[tool], user_id)
    )
    async with door as opened:
        if isinstance(opened, ClientUnavailable):
            await _refuse_unavailable(tool, user_id)
        yield opened


async def _refuse_unavailable(tool: WorkbenchTool, user_id: UUID) -> NoReturn:
    """Say whether the tool's provider must be reconnected or connected."""
    async with DetachedConnectorService().unit_of_work() as service:
        listed = await service.get_user_connectors(user_id)
    if broken_provider(tool, connector_statuses(listed.connectors)) is not None:
        refuse(RECONNECT_REQUIRED)
    refuse(NOT_CONNECTED)
