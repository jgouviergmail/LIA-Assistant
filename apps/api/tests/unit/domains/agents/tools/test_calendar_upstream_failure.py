"""An upstream calendar refusal remains a typed failure through the unified wrapper."""

import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.agents.context.manager import ContextSaveMode
from src.domains.agents.tools import calendar_tools
from src.domains.agents.tools.calendar_tools import SearchEventsTool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.models import ConnectorType
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "instance_name,arguments,save_mode",
    [
        ("_search_events_tool_instance", {"calendar_id": "unavailable"}, ContextSaveMode.LIST),
        ("_get_event_details_tool_instance", {"event_id": "missing"}, ContextSaveMode.CURRENT),
    ],
)
async def test_upstream_404_is_not_replaced_by_a_context_save_attribute_error(
    instance_name, arguments, save_mode
):
    instance = getattr(calendar_tools, instance_name)
    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value=object())
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)
    deps.get_or_create_client = AsyncMock(return_value=MagicMock())
    refusal = ConnectorAPIError("google_calendar", 404, "Calendar resource not found.")
    # Run the real unified wrapper and ConnectorTool execution/error conversion.
    # Decorator I/O (rate limit/store) is separate from this return-shape regression.
    wrapper = inspect.unwrap(calendar_tools.get_events_tool.coroutine)
    with (
        patch.object(instance, "_get_deps_or_fallback", return_value=(True, deps)),
        patch.object(
            instance,
            "_resolve_category_provider",
            AsyncMock(return_value=(ConnectorType.GOOGLE_CALENDAR, GoogleCalendarClient)),
        ),
        patch.object(instance, "execute_api_call", AsyncMock(side_effect=refusal)),
    ):
        output = await wrapper(runtime=make_tool_runtime(store=MagicMock()), **arguments)

    assert isinstance(output, UnifiedToolOutput)
    assert not output.success
    assert output.metadata["error_type"] == "ConnectorAPIError"
    assert output.metadata["error_message"] == "404: Calendar resource not found."
    assert output.context_save_mode == save_mode
    assert not output.registry_updates


def test_a_legacy_connector_tool_keeps_its_json_error_contract():
    instance = SearchEventsTool()
    instance.registry_enabled = False
    output = instance.handle_error(
        ConnectorAPIError("google_calendar", 404, "Calendar resource not found."), None, {}
    )
    assert isinstance(output, str)
    failure = json.loads(output)
    assert not failure["success"]
    assert failure["metadata"]["error_type"] == "ConnectorAPIError"
