"""The synthesis says what a run does — held against the run's own registration (spec 2026-10-30 D5).

For every combination of the four confirmation levels (the tool's own choice — none,
always, never, a never made against another declaration — then the server, the account
and the instance), the server's shape choices, the instance's two switches and an MCP
App, the synthesis's DECISION — who drives the
server in ReAct, which tool is asked, whether a dedicated agent is asked before its
task — is compared with what the real registration path builds
(``_register_user_standard_server`` / ``_register_user_iterative_server``) and what the
real ReAct selector decides (``ReactToolSelector._expand_iterative_mcp``). The flows
are pinned elsewhere: by the flow tests of the 2026-10-29 programme and by the real
proofs (ledger, Tasks 0 and 7).
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from src.core.config import settings
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.registry.confirmation_rule import requires_confirmation
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.domains.user_mcp.behavior import BehaviorInputs, describe_server_behavior
from src.domains.user_mcp.behavior_schemas import Driver
from src.infrastructure.mcp.catalogue_snapshot import catalogue_fingerprint
from src.infrastructure.mcp.confirmation import (
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
    resolve_server_confirmation,
)
from src.infrastructure.mcp.user_context import (
    _register_user_iterative_server,
    _register_user_standard_server,
)
from src.infrastructure.mcp.user_pool import PoolEntry

pytestmark = pytest.mark.unit

USER_ID = UUID(int=7)
PREFIX = "abcd1234"
_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}

#: One tool per declaration class (spec 2026-10-30 D5 reasons).
_DECLARED: dict[str, dict[str, Any] | None] = {
    "delete_note": {"destructive_hint": True},
    "edit_note": {"read_only_hint": False},
    "add_note": {"read_only_hint": False, "destructive_hint": False},
    "read_note": {"read_only_hint": True},
    "ping": None,
}


def _tools(*, app: bool) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, declared in _DECLARED.items():
        tool: dict[str, Any] = {
            "name": name,
            "description": f"{name} description",
            "input_schema": _SCHEMA,
        }
        if declared is not None:
            tool["annotations"] = declared
        if app:
            tool["app_resource_uri"] = "ui://notes/widget"
        tools.append(tool)
    return tools


def _server(*, hitl: bool | None, iterative: bool, shape: bool | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID(f"{PREFIX}-0000-4000-8000-000000000000"),
        name="Notes",
        url="https://notes.example/mcp",
        timeout_seconds=30,
        hitl_required=hitl,
        iterative_mode=iterative,
        react_expand_iterative=shape,
        domain_description="Personal notes",
        auth_type="none",
        discovered_tools_cache=None,
    )


def _choices(variant: str, tools: list[dict[str, Any]]) -> dict[str, StoredToolChoice]:
    """The same choice for every tool: none, always, never, or a never made earlier."""
    if variant == "none":
        return {}
    if variant == "always":
        return {t["name"]: StoredToolChoice(ToolChoice.ALWAYS, "any") for t in tools}
    if variant == "never":
        return {
            t["name"]: StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(t)) for t in tools
        }
    return {t["name"]: StoredToolChoice(ToolChoice.NEVER, "another declaration") for t in tools}


_CHOICES = ["none", "always", "never", "stale_never"]


def _run_registration(
    server: SimpleNamespace,
    tools: list[dict[str, Any]],
    hitl: bool,
    choices: dict[str, StoredToolChoice],
) -> UserMCPToolsContext:
    """What a run builds for this server, through the run's own functions."""
    entry = PoolEntry(
        user_id=USER_ID,
        server_id=server.id,
        last_used=0.0,
        tools=tools,
        catalogue_fingerprint=catalogue_fingerprint(tools),
        configuration_fingerprint="cfg",
        has_reference_tool=False,
    )
    ctx = UserMCPToolsContext()
    register = (
        _register_user_iterative_server
        if settings.mcp_react_enabled and server.iterative_mode
        else _register_user_standard_server
    )
    register(
        server, entry, USER_ID, ctx, hitl, {}, "mcp_notes", PREFIX, tool_choices=choices  # type: ignore[arg-type]
    )
    return ctx


_LEVELS = list(itertools.product([True, False, None], [True, False, None], [True, False]))
_SHAPES = list(
    itertools.product(
        [False, True], [True, False, None], [True, False], [True, False], [False, True]
    )
)


@pytest.mark.parametrize(("server_hitl", "account", "instance"), _LEVELS)
def test_the_synthesis_decides_what_the_run_decides(
    monkeypatch: pytest.MonkeyPatch,
    server_hitl: bool | None,
    account: bool | None,
    instance: bool,
) -> None:
    monkeypatch.setattr(settings, "mcp_hitl_required", instance)
    for (iterative, shape, expand_default, dedicated_on, app), variant in itertools.product(
        _SHAPES, _CHOICES
    ):
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", expand_default)
        monkeypatch.setattr(settings, "mcp_react_enabled", dedicated_on)
        tools = _tools(app=app)
        choices = _choices(variant, tools)
        server = _server(hitl=server_hitl, iterative=iterative, shape=shape)
        hitl = resolve_server_confirmation(server_hitl, account).always
        ctx = _run_registration(server, tools, hitl, choices)
        synthesis = describe_server_behavior(
            BehaviorInputs(
                server_id=server.id,
                server_name=server.name,
                hitl_required=server_hitl,
                iterative_mode=iterative,
                react_expand_iterative=shape,
                tools=tuple(tools),
                tool_choices=choices,
            ),
            account,
        )
        case = (
            f"iterative={iterative} shape={shape} default={expand_default} "
            f"on={dedicated_on} app={app} choice={variant}"
        )

        # Who drives the server in ReAct: the selector's own decision.
        task = next((m for m in ctx.tool_manifests if m.delegates_execution), None)
        token = user_mcp_tools_ctx.set(ctx)
        try:
            expanded = ReactToolSelector._expand_iterative_mcp(task) if task else None
        finally:
            user_mcp_tools_ctx.reset(token)
        react_direct = task is None or expanded is not None
        assert (synthesis.react.driver is Driver.DIRECT) is react_direct, case
        assert (synthesis.pipeline.driver is Driver.DEDICATED_AGENT) is (task is not None), case

        # Which tool is asked: the manifests the run built, read by the run's predicate.
        built = {
            **{m.name: m for m in ctx.tool_manifests if not m.delegates_execution},
            **ctx.reactive_tool_manifests,
        }
        by_tool = {name.removeprefix(f"mcp_user_{PREFIX}_"): m for name, m in built.items()}
        for tool in synthesis.tools:
            assert tool.asks is requires_confirmation(by_tool[tool.tool_name]), (
                case,
                tool.tool_name,
            )
        # Owner decision 2026-10-31: a dedicated agent is asked before its task when
        # one of its tools would — the run's task manifest says it, the synthesis too.
        task_asked = task is not None and requires_confirmation(task)
        assert task_asked is (task is not None and any(t.asks for t in synthesis.tools)), case
        assert synthesis.pipeline.before_task is task_asked, case
        assert synthesis.react.before_task is (task_asked and not react_direct), case
