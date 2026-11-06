"""The workbench's door reads the owner's default with the client (ADR-369, ADR-304)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import CALENDAR
from src.domains.workbench import clients
from src.domains.workbench.features import WorkbenchTool

pytestmark = pytest.mark.unit


async def test_the_container_asked_reaches_the_category_door() -> None:
    asked: dict[str, Any] = {}

    @contextlib.asynccontextmanager
    async def door(category: str, user_id: Any, *, container: Any = None) -> AsyncIterator[Any]:
        asked.update(category=category, container=container)
        yield ActiveClient(
            client=MagicMock(),
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            preferred_name="Famille",
        )

    with patch.object(clients, "open_active_client", door):
        async with clients.open_tool_client(
            WorkbenchTool.CALENDAR, uuid4(), container=CALENDAR
        ) as opened:
            assert opened.preferred_name == "Famille"

    assert asked == {"category": "calendar", "container": CALENDAR}
