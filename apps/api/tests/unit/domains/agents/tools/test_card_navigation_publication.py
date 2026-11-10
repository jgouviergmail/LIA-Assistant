"""The real connector execution stamps its effective source for native navigation."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.agents.tools.calendar_list_tools import ListCalendarsTool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.workbench.card_targets import CARD_TARGET_FIELD, read_card_target
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def test_resolved_microsoft_source_is_stamped_through_real_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = uuid4()
    credentials = ConnectorCredentials(access_token="not-used", account_binding="actual-grant")
    client = MagicMock(credentials=credentials)
    client.list_calendars = AsyncMock(
        return_value={"items": [{"id": "real-calendar", "summary": "Work"}]}
    )
    service = MagicMock(get_connector_credentials=AsyncMock(return_value=credentials))
    deps = MagicMock(
        get_connector_service=AsyncMock(return_value=service),
        get_or_create_client=AsyncMock(return_value=client),
    )
    monkeypatch.setattr("src.domains.agents.tools.base.get_dependencies", lambda _: deps)
    monkeypatch.setattr(
        ListCalendarsTool,
        "_resolve_category_provider",
        AsyncMock(return_value=(ConnectorType.MICROSOFT_CALENDAR, None)),
    )
    monkeypatch.setattr(
        "src.domains.agents.tools.calendar_list_tools.get_user_preferences",
        AsyncMock(return_value=("en", "UTC", "en_US")),
    )
    runtime = make_tool_runtime(
        user_id=user,
        thread_id="t",
        conversation_id="t",
        state={},
        store=MagicMock(aget=AsyncMock(return_value=None), aput=AsyncMock()),
    )
    result = await ListCalendarsTool().execute(runtime)
    assert isinstance(result, UnifiedToolOutput) and result.success
    stored = next(iter(result.registry_updates.values()))
    proof = read_card_target(stored.meta.display[CARD_TARGET_FIELD], user)
    assert proof is not None
    assert proof.provider == ConnectorType.MICROSOFT_CALENDAR
    assert proof.target.item_id == "real-calendar"
    client.list_calendars.assert_awaited_once()
    service.get_connector_credentials.assert_awaited_once_with(
        user, ConnectorType.MICROSOFT_CALENDAR
    )
