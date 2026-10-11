"""Recorded call history is a bounded owner read, never a calling or billing action."""

import json
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.telephony.history_schemas import PhoneHistoryProjection, PhoneHistoryRead

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("flag", ["application_tools_enabled", "telephony_enabled"])
async def test_disabled_history_capability_precedes_the_read_port(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    module = import_module("src.domains.agents.application.phone_history_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(settings, flag, False)
    gateway = AsyncMock()
    monkeypatch.setattr(module, "get_phone_history", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.read_phone_history(db, uuid4(), PhoneHistoryRead())
    gateway.read.assert_not_awaited()


@pytest.mark.parametrize("flag", ["application_tools_enabled", "telephony_enabled"])
async def test_capability_revoked_during_history_read_withholds_the_result(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    module = import_module("src.domains.agents.application.phone_history_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(module, "load_actor", AsyncMock())

    async def read(*args: object) -> PhoneHistoryProjection:
        monkeypatch.setattr(settings, flag, False)
        return PhoneHistoryProjection(calls=[], total=0)

    gateway = AsyncMock()
    gateway.read.side_effect = read
    monkeypatch.setattr(module, "get_phone_history", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.read_phone_history(db, uuid4(), PhoneHistoryRead())
    gateway.read.assert_awaited_once()


async def test_actor_revoked_during_history_read_withholds_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.agents.application.phone_history_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(
        module,
        "load_actor",
        AsyncMock(side_effect=[object(), AuthorizationError(detail={"error_code": "FORBIDDEN"})]),
    )
    gateway = AsyncMock()
    gateway.read.return_value = PhoneHistoryProjection(calls=[], total=0)
    monkeypatch.setattr(module, "get_phone_history", lambda: gateway)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    with pytest.raises(AuthorizationError):
        await module.read_phone_history(db, uuid4(), PhoneHistoryRead())
    gateway.read.assert_awaited_once()


def test_history_read_identity_and_bounded_schema_are_consistently_registered() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    module = import_module("src.domains.agents.tools.application_phone_history_tools")
    assert set(
        module.get_lia_phone_calls_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"query"}
    assert "get_lia_phone_calls_tool" in APPLICATION_TOOL_NAMES
    spec = APPLICATION_OPERATIONS.get("phone_history.read")
    assert spec.kind == OperationKind.READ and spec.sections == ("telephony-calls",)


def test_history_budget_cursor_advances_only_past_the_last_visible_call() -> None:
    from src.domains.agents.tools.output import UnifiedToolOutput
    from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

    rows = [{"id": str(uuid4()), "summary": "Long " * 300} for _ in range(8)]
    output = UnifiedToolOutput.data_success(
        message="calls",
        structured_data={"calls": rows, "total": 8, "next_cursor": None},
        metadata={"application_phone_call_cursor": True},
    )
    rendered = json.loads(extract_data_for_llm(output, budget_tokens=120))
    assert 0 < len(rendered["calls"]) < 8
    assert rendered["next_cursor"] == rendered["calls"][-1]["id"]
    assert output.structured_data["next_cursor"] is None
