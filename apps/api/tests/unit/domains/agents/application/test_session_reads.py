"""Session listing is bounded, permission-fenced and continued at visible item boundaries."""

import json
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.session_schemas import DeviceSessionsRead

pytestmark = pytest.mark.unit


async def test_disabled_application_tools_stop_session_metadata_before_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.session_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    redis = AsyncMock()
    monkeypatch.setattr(module, "get_redis_session", redis)
    with pytest.raises(AuthorizationError):
        await module.read_session_settings(
            AsyncMock(spec=AsyncSession), uuid4(), DeviceSessionsRead()
        )
    redis.assert_not_awaited()


def test_session_read_is_registered_and_has_no_cookie_or_current_device_input() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    module = import_module("src.domains.agents.tools.application_session_tools")
    schema = module.get_lia_device_sessions_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"query"}
    assert set(schema["$defs"]["DeviceSessionsRead"]["properties"]) == {"cursor", "limit"}
    assert "get_lia_device_sessions_tool" in APPLICATION_TOOL_NAMES
    manifest = next(
        row for row in APPLICATION_MANIFESTS if row.name == "get_lia_device_sessions_tool"
    )
    assert manifest.mutation_policy == "read"
    assert APPLICATION_OPERATIONS.get("device_sessions.read").kind == OperationKind.READ


def test_session_budget_continuation_names_last_session_actually_shown() -> None:
    from src.domains.agents.tools.output import UnifiedToolOutput
    from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

    rows = [{"id": f"{index:016x}", "device_name": "Phone " * 300} for index in range(8)]
    output = UnifiedToolOutput.data_success(
        message="sessions",
        structured_data={"sessions": rows, "next_cursor": None, "total": 8},
        metadata={"application_session_cursor": True},
    )
    rendered = json.loads(extract_data_for_llm(output, budget_tokens=120))
    assert 0 < len(rendered["sessions"]) < 8
    assert rendered["next_cursor"] == rendered["sessions"][-1]["id"]
    assert output.structured_data["next_cursor"] is None
