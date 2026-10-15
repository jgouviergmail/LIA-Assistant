"""A payload that declares a failure never leaves a connector tool as a success (ADR-347).

The three Hue formatters answered a refused command with a success. The class
is wider than Hue: handed ``{"success": False}``, 27 of the 71 registry-mode
connector formatters answered with a success (probe of 2026-10-14).
``keep_declared_failure`` sits at the two chokepoints every connector tool goes
through (``ConnectorTool.execute`` and ``APIKeyConnectorTool.execute``): when
the payload declared a failure and the formatter answered a success, the
verdict of the payload wins, in its own words, and the correction is logged at
ERROR and counted.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime
from prometheus_client import REGISTRY

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.base import APIKeyConnectorTool, ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.failure_verdict import keep_declared_failure
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.models import ConnectorType
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = [pytest.mark.unit, pytest.mark.failure_verdict_correction]


def _corrections(tool_name: str) -> float:
    value = REGISTRY.get_sample_value(
        "tool_failure_verdict_corrected_total", {"tool_name": tool_name}
    )
    return value or 0.0


def _wrong_success(message: str = "Found 0 lights.") -> UnifiedToolOutput:
    return UnifiedToolOutput.data_success(message=message, structured_data={"success": False})


class TestThePayloadVerdictWins:
    def test_a_declared_failure_formatted_as_success_becomes_that_failure(self) -> None:
        before = _corrections("probe_a")
        payload = {"success": False, "error_code": "NOT_FOUND", "error": "no such lamp"}

        output = keep_declared_failure(payload, _wrong_success(), tool_name="probe_a")

        assert output.success is False
        assert output.error_code == ToolErrorCode.NOT_FOUND.value
        assert output.message == "no such lamp"
        assert output.structured_data == {}
        assert _corrections("probe_a") == before + 1

    @pytest.mark.parametrize("error", [None, "", "   ", {"code": 404}])
    def test_a_payload_without_words_keeps_the_formatter_s(self, error: object) -> None:
        payload = {"success": False, "error": error}

        output = keep_declared_failure(
            payload, _wrong_success("Light refused"), tool_name="probe_g"
        )

        assert output.success is False
        assert output.message == "Light refused"

    def test_a_refusal_declared_by_its_code_alone_is_a_failure_too(self) -> None:
        payload = {"error_code": ToolErrorCode.INVALID_INPUT.value, "message": "bad folder"}

        output = keep_declared_failure(payload, _wrong_success(""), tool_name="probe_b")

        assert output.success is False
        assert output.error_code == ToolErrorCode.INVALID_INPUT.value
        assert output.message == "bad folder"

    @pytest.mark.parametrize("code", [None, "", "NOT_A_TOOL_ERROR_CODE"])
    def test_a_failure_without_a_known_code_is_an_internal_error(self, code: str | None) -> None:
        payload = {"success": False, "error_code": code}

        output = keep_declared_failure(payload, _wrong_success(), tool_name="probe_c")

        assert output.success is False
        assert output.error_code == ToolErrorCode.INTERNAL_ERROR.value

    def test_a_failure_with_no_words_still_says_something(self) -> None:
        output = keep_declared_failure({"success": False}, _wrong_success(""), tool_name="probe_d")

        assert output.success is False
        assert output.message


class TestNothingElseIsTouched:
    @pytest.mark.parametrize(
        "payload",
        [
            {"success": True, "data": {"name": "Desk"}},
            {"success": True, "error_code": "NOT_FOUND"},
            {"data": {"name": "Desk"}},
            {"error_code": None, "data": {}},
            "a legacy string payload",
            None,
        ],
    )
    def test_a_payload_that_declares_no_failure_keeps_its_output(self, payload: object) -> None:
        before = _corrections("probe_e")
        output = UnifiedToolOutput.data_success(message="ok")

        assert keep_declared_failure(payload, output, tool_name="probe_e") is output
        assert _corrections("probe_e") == before

    def test_a_failure_already_formatted_as_a_failure_is_left_alone(self) -> None:
        before = _corrections("probe_f")
        output = UnifiedToolOutput.failure(message="refused", error_code="NOT_FOUND")

        result = keep_declared_failure({"success": False}, output, tool_name="probe_f")

        assert result is output
        assert _corrections("probe_f") == before


# ---------------------------------------------------------------- the chokepoints


class _Client:
    def __init__(self, *args: object) -> None:
        self.args = args


class _BuggyOAuthTool(ConnectorTool[_Client]):
    """A formatter that answers a refused payload with a success — the Hue defect."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = _Client
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="buggy_oauth_probe_tool", operation="read")

    async def execute_api_call(
        self, client: _Client, user_id: UUID, **kwargs: object
    ) -> dict[str, object]:
        return {"success": False, "error_code": "NOT_FOUND", "error": "no such contact"}

    def format_registry_response(self, result: dict[str, object]) -> UnifiedToolOutput:
        return UnifiedToolOutput.data_success(message=str(result.get("error")))


class _BuggyApiKeyTool(APIKeyConnectorTool[_Client]):
    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = _Client
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="buggy_api_key_probe_tool", operation="read")

    def create_client(self, credentials: object, user_id: UUID) -> _Client:
        return _Client(credentials, user_id)

    async def execute_api_call(
        self, client: _Client, user_id: UUID, **kwargs: object
    ) -> dict[str, object]:
        return {"success": False, "error_code": "NOT_FOUND", "error": "no such city"}

    def format_registry_response(self, result: dict[str, object]) -> UnifiedToolOutput:
        return UnifiedToolOutput.data_success(message=str(result.get("error")))


def _runtime() -> ToolRuntime[LiaRuntimeContext, Any]:
    store = MagicMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    return make_tool_runtime(
        user_id=uuid4(),
        thread_id="t",
        conversation_id="t",
        state={},
        store=store,
        tool_call_id="call",
    )


def _deps(service: MagicMock) -> MagicMock:
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)

    async def _run_factory(
        cls: type, cache_key: object, factory: Callable[[], Awaitable[object]]
    ) -> object:
        return await factory()

    deps.get_or_create_client = AsyncMock(side_effect=_run_factory)
    deps.db = MagicMock()
    return deps


class TestBothChokepointsApplyTheNet:
    async def test_connector_tool_execute_returns_the_declared_failure(self) -> None:
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value={"access_token": "x"})
        before = _corrections("buggy_oauth_probe_tool")

        with patch("src.domains.agents.tools.base.get_dependencies", return_value=_deps(service)):
            output = await _BuggyOAuthTool().execute(_runtime())

        assert isinstance(output, UnifiedToolOutput)
        assert output.success is False
        assert output.error_code == ToolErrorCode.NOT_FOUND.value
        assert "no such contact" in output.message
        assert _corrections("buggy_oauth_probe_tool") == before + 1

    async def test_api_key_connector_tool_execute_returns_the_declared_failure(self) -> None:
        service = MagicMock()
        service.get_api_key_credentials = AsyncMock(return_value=MagicMock(api_key="k"))
        before = _corrections("buggy_api_key_probe_tool")

        with patch("src.domains.agents.tools.base.get_dependencies", return_value=_deps(service)):
            output = await _BuggyApiKeyTool().execute(_runtime())

        assert isinstance(output, UnifiedToolOutput)
        assert output.success is False
        assert output.error_code == ToolErrorCode.NOT_FOUND.value
        assert "no such city" in output.message
        assert _corrections("buggy_api_key_probe_tool") == before + 1

    async def test_a_legacy_json_tool_keeps_its_own_failure_flag(self) -> None:
        class _LegacyTool(_BuggyOAuthTool):
            registry_enabled = False

            def format_response(self, result: dict[str, object]) -> str:
                return json.dumps(result)

        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value={"access_token": "x"})

        with patch("src.domains.agents.tools.base.get_dependencies", return_value=_deps(service)):
            output = await _LegacyTool().execute(_runtime())

        assert isinstance(output, str)
        assert json.loads(output)["success"] is False
