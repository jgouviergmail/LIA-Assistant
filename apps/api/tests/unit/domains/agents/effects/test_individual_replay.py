"""A confirmed inner call is replayed once, by the tool it named (spec D5, probe P1).

A draft born inside an iterative task names an INDIVIDUAL tool — one the planner
never saw. When the person approves it, the replay must find that tool again
through the turn's offered task, run it once under the draft's own key, and say
so plainly when the tool is gone (the person switched the server off between
the question and the answer).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.confirmation import execute_tool_call_draft
from src.domains.agents.effects.scope import current_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.reactive_manifests import reset_reactive_manifests
from src.domains.agents.tools import tool_registry
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp import registration
from src.infrastructure.mcp.registration import build_mcp_adapters, register_mcp_tools
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_context import _register_user_iterative_server
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = [pytest.mark.unit]

PREFIX = "abcd1234"
_ID: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}
_DESTRUCTIVE = {"read_only_hint": False, "destructive_hint": True}
SENT: list[tuple[str, dict[str, Any], str | None]] = []


async def _server(self: Any, **kwargs: Any) -> UnifiedToolOutput:
    scope = current_scope()
    SENT.append((self.name, dict(kwargs), scope.idempotency_key if scope else None))
    return UnifiedToolOutput.action_success(message="deleted")


class _UniqueKeyLedger:
    """The repository's contract: one row per key; a lost claim is served the record."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def claim(self, request: Any) -> Any:
        if request.idempotency_key in self.keys:
            return gate_runtime.ClaimTicket(
                effect_id=uuid.uuid4(),
                claim_token=None,
                served_result={"success": True, "data": {"served": True}},
            )
        self.keys.append(request.idempotency_key)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
        )

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def abandon(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.fixture(autouse=True)
def _turn(monkeypatch: pytest.MonkeyPatch) -> Iterator[_UniqueKeyLedger]:
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    monkeypatch.setattr(registration, "_admin_mcp_domains", {})
    monkeypatch.setattr(registration, "_admin_mcp_server_domains", {})
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    SENT.clear()
    gate_runtime.reset_policy_cache()
    reset_reactive_manifests()
    ledger = _UniqueKeyLedger()
    sink = AsyncMock()
    with (
        installed_shared_mcp_access() as actor,
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=actor.id,
                thread_id="thread-replay",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        patch.object(UserMCPToolAdapter, "_call_server", new=_server),
        patch.object(MCPToolAdapter, "_call_server", new=_server),
        patch.object(gate_runtime, "_LEDGER", ledger),
        treatment_collector(run_id="individual-replay"),
    ):
        yield ledger
    reset_reactive_manifests()
    gate_runtime.reset_policy_cache()


def _personal() -> tuple[UserMCPToolsContext, str]:
    server = SimpleNamespace(
        id=uuid.UUID(f"{PREFIX}-0000-4000-8000-000000000000"),
        name="notes",
        url="https://notes.example/mcp",
        timeout_seconds=30,
        domain_description="Personal notes",
        auth_type="none",
        react_expand_iterative=None,
    )
    entry = SimpleNamespace(
        tools=[
            {
                "name": "delete_note",
                "description": "Delete a note",
                "input_schema": _ID,
                "annotations": _DESTRUCTIVE,
            }
        ],
        catalogue_fingerprint="fp-1",
        from_snapshot=False,
    )
    ctx = UserMCPToolsContext()
    _register_user_iterative_server(
        server, entry, uuid.uuid4(), ctx, False, {}, "mcp_notes", PREFIX  # type: ignore[arg-type]
    )
    name = next(n for n, t in ctx.tool_instances.items() if isinstance(t, UserMCPToolAdapter))
    return ctx, name


def _admin() -> tuple[AgentRegistry, str]:
    discovered = {
        "boards": [
            MCPDiscoveredTool(
                server_name="boards",
                tool_name="drop_board",
                description="Drop a board",
                input_schema=_ID,
                annotations=_DESTRUCTIVE,
            )
        ]
    }
    config = MCPServerConfig(
        transport=MCPTransportType.STDIO,
        command="fixture-only",
        description="Boards",
        iterative_mode=True,
        hitl_required=False,
    )
    registry = AgentRegistry()
    register_mcp_tools(
        registry, discovered, build_mcp_adapters(discovered), {"boards": config}, False
    )
    return registry, "mcp_boards_drop_board"


async def _replay(name: str, draft_id: str) -> Any:
    return await execute_tool_call_draft(
        {"tool_name": name, "tool_args": {"note_id": "n2"}, "draft_id": draft_id},
        uuid.uuid4(),
        None,
    )


class TestAConfirmedIndividualRunsOnce:
    async def test_confirmed_individual_replays_once(self, _turn: _UniqueKeyLedger) -> None:
        ctx, personal = _personal()
        registry, admin = _admin()
        token = user_mcp_tools_ctx.set(ctx)
        offered = request_tool_manifests_ctx.set(
            [*ctx.tool_manifests, registry.get_tool_manifest("mcp_boards_task")]
        )
        try:
            for name, draft_id in ((personal, "d-personal"), (admin, "d-admin")):
                await _replay(name, draft_id)
                await _replay(name, draft_id)  # a node re-execution replays the same draft
        finally:
            request_tool_manifests_ctx.reset(offered)
            user_mcp_tools_ctx.reset(token)

        assert SENT == [
            (personal, {"note_id": "n2"}, "call:d-personal"),
            (admin, {"note_id": "n2"}, "call:d-admin"),
        ], "each approved act reached its server once, under its draft's key"
        assert _turn.keys == ["call:d-personal", "call:d-admin"]

    async def test_server_gone_before_the_answer(self) -> None:
        """The person switched the server off: nothing runs, and the result says so."""
        ctx, personal = _personal()
        _registry, admin = _admin()
        token = user_mcp_tools_ctx.set(ctx)
        offered = request_tool_manifests_ctx.set([])  # neither task is offered any more
        try:
            results = [
                await _replay(name, f"d-{index}") for index, name in enumerate((personal, admin))
            ]
        finally:
            request_tool_manifests_ctx.reset(offered)
            user_mcp_tools_ctx.reset(token)

        assert SENT == []
        for result in results:
            assert result["success"] is False
            assert "nothing was performed" in result["error"]


class TestTheDraftExecutorTellsWhatHappened:
    async def test_a_confirmed_mcp_act_is_reported_performed(self, _turn: _UniqueKeyLedger) -> None:
        """Through the executor the response node calls: the act ran, so it says so.

        An MCP adapter answers with a ``UnifiedToolOutput``, not a dict: the
        executor must read it as the success it is, never report a failure for
        an act the server performed.
        """
        from src.domains.agents.services.draft_executor import execute_draft_if_confirmed

        ctx, personal = _personal()
        token = user_mcp_tools_ctx.set(ctx)
        offered = request_tool_manifests_ctx.set(list(ctx.tool_manifests))
        run = SimpleNamespace(
            user_id=uuid.uuid4(),
            thread_id="thread-replay",
            execution_mode="pipeline",
            is_automated_source=False,
            deps=object(),
            side_channel_queue=None,
        )
        try:
            with patch(
                "src.domains.agents.services.draft_executor.runtime_context_if_running",
                return_value=run,
            ):
                result = await execute_draft_if_confirmed(
                    {
                        "action": "confirm",
                        "draft_id": "d-exec",
                        "draft_type": "tool_call",
                        "draft_content": {"tool_name": personal, "tool_args": {"note_id": "n2"}},
                    },
                    {"configurable": {"thread_id": "thread-replay"}, "metadata": {"run_id": "r1"}},
                    "r1",
                    "en",
                )
        finally:
            request_tool_manifests_ctx.reset(offered)
            user_mcp_tools_ctx.reset(token)

        assert SENT == [(personal, {"note_id": "n2"}, "draft:d-exec")], "the act ran once"
        assert result is not None
        assert result.success is True, f"the act ran yet was reported: {result.error!r}"
