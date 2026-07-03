"""Concurrency isolation tests for ConnectorTool runtime state (audit B6/N-126/N-135).

ConnectorTool instances are module-level singletons shared by every request.
``execute()`` stores the per-request ``ToolRuntime`` on the instance, and the
preference helpers (``get_user_preferences_safe``, mixin ``get_user_language``)
read it back after await points: when two users' tool calls interleave, user A
resolves user B's timezone/language (dates in the wrong timezone, HITL drafts
in the wrong language).

The probe drives the REAL ``execute()`` pipeline (validation, deps, credentials,
client cache) with stubbed dependencies; the gate inside ``execute_api_call``
only reorders task scheduling.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.dependencies import ToolDependencies
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.connectors.models import ConnectorType
from src.domains.users.preferences_cache import UserPreferencesCache

USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())
PREFS = {
    USER_A: (float("inf"), "Europe/Paris", "fr"),
    USER_B: (float("inf"), "America/New_York", "en"),
}


class _ProbeTool(ToolOutputMixin, ConnectorTool[Any]):
    """Minimal concrete ConnectorTool exercising the preference helpers."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = object
    registry_enabled = False

    def __init__(self, gates: dict[str, asyncio.Event]) -> None:
        super().__init__(tool_name="probe_tool", operation="probe")
        self._gates = gates

    async def execute_api_call(self, client: Any, user_id: uuid.UUID, **kwargs: Any) -> dict:
        gate = self._gates.get(str(user_id))
        if gate is not None:
            await gate.wait()  # scheduling only — parks A while B runs
        user_timezone, locale = await self.get_user_preferences_safe()
        return {
            "requested_user": str(user_id),
            "timezone": user_timezone,
            "locale": locale,
            "config_language": self.get_user_language(),
        }

    def format_response(self, result: dict) -> str:
        return json.dumps(result)


class _Runtime:
    """Duck-typed ToolRuntime: config + store are all execute() reads."""

    def __init__(self, user_id: str, language: str, deps: ToolDependencies) -> None:
        self.config = {
            "configurable": {
                "user_id": user_id,
                "thread_id": f"thread-{user_id}",
                "user_language": language,
                "__deps": deps,
            }
        }
        self.store = object()


def _deps() -> ToolDependencies:
    deps = ToolDependencies(db_session=MagicMock(spec=AsyncSession))
    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value={"access_token": "x"})
    deps.get_connector_service = AsyncMock(return_value=service)  # type: ignore[method-assign]
    deps.get_or_create_client = AsyncMock(return_value=object())  # type: ignore[method-assign]
    return deps


@pytest.mark.asyncio
async def test_runtime_isolated_between_interleaved_executions() -> None:
    """Each user's tool call must resolve its OWN timezone/language.

    Scenario (the production race): A's execute() stores its runtime and
    parks inside execute_api_call; B's execute() runs to completion on the
    same singleton instance; A resumes and reads the runtime-derived
    preferences. Shared instance state makes A read B's runtime.
    """
    gate_a = asyncio.Event()
    tool = _ProbeTool(gates={USER_A: gate_a})
    deps = _deps()

    with patch.dict(UserPreferencesCache._entries, PREFS, clear=False):
        task_a = asyncio.create_task(tool.execute(_Runtime(USER_A, "fr", deps)))
        # Let A reach the gate (its runtime is stored by then)
        while not gate_a._waiters:  # noqa: SLF001 — deterministic sync point
            await asyncio.sleep(0)

        result_b = json.loads(await tool.execute(_Runtime(USER_B, "en", deps)))

        gate_a.set()
        result_a = json.loads(await task_a)

    assert result_b["timezone"] == "America/New_York"
    assert result_b["config_language"] == "en"

    assert result_a["requested_user"] == USER_A
    assert (
        result_a["timezone"] == "Europe/Paris"
    ), "user B's runtime leaked into user A's tool execution (timezone)"
    assert result_a["locale"].startswith("fr"), "user B's runtime leaked (locale)"
    assert result_a["config_language"] == "fr", "user B's runtime leaked (config language)"


@pytest.mark.asyncio
async def test_runtime_helpers_still_work_single_user() -> None:
    """Sanity: the helpers resolve the caller's own preferences (no gate)."""
    tool = _ProbeTool(gates={})
    with patch.dict(UserPreferencesCache._entries, PREFS, clear=False):
        result = json.loads(await tool.execute(_Runtime(USER_B, "en", _deps())))

    assert result["timezone"] == "America/New_York"
    assert result["locale"].startswith("en")
    assert result["config_language"] == "en"
