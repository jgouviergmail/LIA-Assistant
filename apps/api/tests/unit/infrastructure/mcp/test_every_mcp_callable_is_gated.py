"""Every MCP callable of a turn goes through the effect gate (spec D3).

The registry's boot assert sees the tools it registers; a personal server's
tools are built per request and never reach it. Measured 2026-10-29 (probe H5):
the personal iterative TASK tool — a named copy of a generic tool nobody
registers — carried no gate at all, so a server whose owner asked for
confirmation ran its whole sub-loop unasked. The copy is now gated under its own
name, and a context holding an ungated instance is refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.confirmation import execute_tool_call_draft
from src.domains.agents.effects.runtime import EFFECT_GATED_ATTR, EFFECT_GATED_NAME_ATTR
from src.domains.agents.effects.scope import EffectScope, current_scope, effect_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.tools import tool_registry
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.user_context import _register_user_iterative_server
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = [pytest.mark.unit]

PREFIX = "abcd1234"
TASK = f"mcp_user_{PREFIX}_task"
_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}
SENT: list[tuple[str, dict[str, Any], str | None]] = []


@pytest.fixture(autouse=True)
def _turn(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    SENT.clear()
    gate_runtime.reset_policy_cache()
    sink = AsyncMock()
    with (
        installed_shared_mcp_access() as actor,
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=actor.id,
                thread_id="thread-gated",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        patch.object(UserMCPToolAdapter, "_call_server", new=_server),
        treatment_collector(run_id="gated-callables"),
    ):
        yield
    gate_runtime.reset_policy_cache()


async def _server(self: UserMCPToolAdapter, **kwargs: Any) -> UnifiedToolOutput:
    scope = current_scope()
    SENT.append((self.mcp_tool_name, dict(kwargs), scope.idempotency_key if scope else None))
    return UnifiedToolOutput.action_success(message="archived")


def _context(*, hitl: bool) -> UserMCPToolsContext:
    """A personal iterative server registered through the real request path."""
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
            {"name": "archive_note", "description": "Archive a note", "input_schema": _SCHEMA},
            {"name": "read_note", "description": "Read a note", "input_schema": _SCHEMA},
        ],
        catalogue_fingerprint="fp-1",
        from_snapshot=False,
    )
    ctx = UserMCPToolsContext()
    _register_user_iterative_server(
        server, entry, uuid.uuid4(), ctx, hitl, {}, "mcp_notes", PREFIX  # type: ignore[arg-type]
    )
    return ctx


def _task_call(ctx: UserMCPToolsContext) -> Any:
    """The task tool's own call — what the pipeline executor invokes."""
    task = ctx.tool_instances[TASK]
    assert isinstance(task, StructuredTool) and task.coroutine is not None
    return task.coroutine


class _Ledger:
    def __init__(self) -> None:
        self.claims: list[str] = []

    async def claim(self, request: Any) -> Any:
        self.claims.append(request.idempotency_key)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
        )

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def abandon(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, *args: Any, **kwargs: Any) -> None:
        return None


class TestThePersonalTaskToolIsGated:
    def test_personal_task_tool_is_gated(self) -> None:
        call = _task_call(_context(hitl=False))

        assert getattr(call, EFFECT_GATED_ATTR, False) is True
        assert getattr(call, EFFECT_GATED_NAME_ATTR, None) == TASK

    async def test_a_wrong_server_target_is_refused_before_the_gate_asks(self) -> None:
        """The identity guard stays outside the gate: no card for a call it refuses."""
        ctx = _context(hitl=True)
        ledger = _Ledger()
        token = user_mcp_tools_ctx.set(ctx)
        offered = request_tool_manifests_ctx.set(list(ctx.tool_manifests))
        try:
            with patch.object(gate_runtime, "_LEDGER", ledger):
                result = await _task_call(ctx)(
                    server_id_prefix="ffffffff", server_name="notes", task="archive n3"
                )
        finally:
            request_tool_manifests_ctx.reset(offered)
            user_mcp_tools_ctx.reset(token)

        assert result.success is False and result.error_code == "INVALID_INPUT"
        assert not result.tool_metadata.get("requires_confirmation")
        assert ledger.claims == []

    async def test_hitl_on_iterative_task_is_asked_once_and_covers_the_loop(self) -> None:
        ctx = _context(hitl=True)
        loops: list[str] = []

        async def _sub_loop(*, server_tools: list[Any], task: str, **_: Any) -> Any:
            """What the sub-agent does: two acts on the server, through its own tools."""
            loops.append(task)
            archive = next(tool for tool in server_tools if tool.name == "archive_note")
            for call_id, note in (("c1", "n3"), ("c2", "n4")):
                await archive.ainvoke(
                    {
                        "name": archive.name,
                        "args": {"note_id": note},
                        "id": call_id,
                        "type": "tool_call",
                    }
                )
            return UnifiedToolOutput.action_success(message="archived n3 and n4")

        ledger = _Ledger()
        token = user_mcp_tools_ctx.set(ctx)
        offered = request_tool_manifests_ctx.set(list(ctx.tool_manifests))
        try:
            with (
                patch("src.domains.agents.tools.mcp_react_tools._run_mcp_react_task", _sub_loop),
                patch.object(gate_runtime, "_LEDGER", ledger),
            ):
                with effect_scope(
                    EffectScope(run_id="run-g", idempotency_key="run-g:step:s1", source="user")
                ):
                    asked = await _task_call(ctx)(
                        server_id_prefix=PREFIX, server_name="notes", task="archive n3 and n4"
                    )
                assert asked.tool_metadata["requires_confirmation"] is True
                assert (loops, SENT, ledger.claims) == ([], [], []), "nothing ran before the answer"

                draft_id, item = next(iter(asked.registry_updates.items()))
                replayed = await execute_tool_call_draft(
                    {**item.payload["content"], "draft_id": draft_id}, uuid.uuid4(), None
                )
        finally:
            request_tool_manifests_ctx.reset(offered)
            user_mcp_tools_ctx.reset(token)

        assert loops == ["archive n3 and n4"], "the approved task ran once"
        assert [(tool, args) for tool, args, _key in SENT] == [
            ("archive_note", {"note_id": "n3"}),
            ("archive_note", {"note_id": "n4"}),
        ], "every act of the approved task ran, none asked again"
        assert ledger.claims == [
            f"call:{draft_id}",
            f"call:{draft_id}:sub:c1",
            f"call:{draft_id}:sub:c2",
        ]
        assert not getattr(replayed, "tool_metadata", {}).get("requires_confirmation")


class TestAnUngatedInstanceNeverServesATurn:
    @staticmethod
    def _with_an_ungated_task(ctx: UserMCPToolsContext) -> None:
        async def _body(**_: Any) -> str:
            return "ran"

        ctx.tool_instances[TASK] = StructuredTool.from_function(
            coroutine=_body, name=TASK, description="An ungated copy"
        )

    def test_ungated_names_reads_the_gate_and_the_name_it_acts_under(self) -> None:
        from src.infrastructure.mcp.gated_tool import ungated_names

        ctx = _context(hitl=False)
        assert ungated_names(ctx.tool_instances) == []
        # Gated, but under another tool's name: policed by the wrong declaration.
        assert ungated_names({"mcp_user_other_task": ctx.tool_instances[TASK]}) == [
            "mcp_user_other_task"
        ]

        self._with_an_ungated_task(ctx)
        assert ungated_names(ctx.tool_instances) == [TASK]

    def test_an_ungated_instance_is_dropped_in_production_and_raises_elsewhere(self) -> None:
        from src.infrastructure.mcp.user_context import _refuse_ungated_tools

        ctx = _context(hitl=False)
        self._with_an_ungated_task(ctx)

        with patch("src.infrastructure.mcp.user_context.settings") as current:
            current.is_production = False
            with pytest.raises(RuntimeError, match="effect gate"):
                _refuse_ungated_tools(ctx, uuid.uuid4())

            current.is_production = True
            with patch("src.infrastructure.mcp.user_context.logger") as log:
                _refuse_ungated_tools(ctx, uuid.uuid4())

        assert TASK not in ctx.tool_instances
        assert all(manifest.name != TASK for manifest in ctx.tool_manifests)
        assert ctx.tool_instances, "the gated siblings keep serving"
        event, fields = log.error.call_args.args[0], log.error.call_args.kwargs
        assert event == "mcp_user_tool_ungated" and fields["count"] == 1
