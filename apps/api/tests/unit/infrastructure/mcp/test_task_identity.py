"""Exact task targets are enforced by callable copies, with no MCP/provider effects."""

from typing import Annotated

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, StructuredTool

from src.domains.agents.effects import runtime as effect_runtime
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import _install_effect_gate
from src.infrastructure.mcp.task_identity import (
    MCP_TASK_IDENTITY_METADATA_KEY,
    bind_task_identity,
)

pytestmark = pytest.mark.unit


def _invalid(result: object) -> None:
    assert isinstance(result, UnifiedToolOutput)
    assert not result.success and result.error_code == "INVALID_INPUT"


@pytest.mark.asyncio
@pytest.mark.parametrize("other", ["other", "Bound ", "bound", None, 123])
async def test_admin_target_is_exact_before_the_original_coroutine(other: object) -> None:
    calls: list[str] = []

    async def original(server_name: str, task: str) -> str:
        calls.append(server_name)
        return "accepted"

    source = StructuredTool.from_function(
        coroutine=original, name="admin_alias", description="Task"
    )
    bound = bind_task_identity(source, {"server_name": "Bound"})
    assert bound.coroutine is not None and source.coroutine is not None
    _invalid(await bound.coroutine(server_name=other, task="Read"))
    assert calls == []
    assert await source.coroutine(server_name="other", task="Read") == "accepted"
    assert calls == ["other"]  # Binding does not mutate the generic source tool.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "name"),
    [("different", "Bank"), ("12345678-full-uuid", "Other bank"), ("12345678", "Bank")],
)
async def test_user_target_requires_both_effective_prefix_and_name(prefix: str, name: str) -> None:
    calls: list[tuple[str, str]] = []

    async def original(server_id_prefix: str, server_name: str, task: str) -> str:
        calls.append((server_id_prefix, server_name))
        return "accepted"

    task = StructuredTool.from_function(coroutine=original, name="user_alias", description="Task")
    bound = bind_task_identity(
        task, {"server_id_prefix": "12345678-full-uuid", "server_name": "Bank"}
    )
    assert bound.coroutine is not None
    _invalid(await bound.coroutine(prefix, name, "Read"))
    assert calls == []
    assert await bound.coroutine("12345678-full-uuid", "Bank", "Read") == "accepted"
    assert calls == [("12345678-full-uuid", "Bank")]


@pytest.mark.asyncio
async def test_schema_runtime_config_and_callback_injection_are_preserved() -> None:
    received: list[tuple[object, RunnableConfig, object]] = []

    async def original(
        server_name: str,
        task: str,
        config: RunnableConfig,
        runtime: Annotated[object, InjectedToolArg] = None,
        callbacks: object = None,
    ) -> str:
        received.append((runtime, config, callbacks))
        return task

    source = StructuredTool.from_function(
        coroutine=original,
        name="admin_alias",
        description="Task",
        metadata={"mcp_origin": "admin", "mcp_server_key": "Bound"},
    )
    bound = bind_task_identity(source, {"server_name": "Bound"})
    sentinel = object()
    assert bound.args_schema is source.args_schema
    assert source.metadata is not None
    assert bound.metadata == {
        **source.metadata,
        MCP_TASK_IDENTITY_METADATA_KEY: {"server_name": "Bound"},
    }
    assert source.metadata == {"mcp_origin": "admin", "mcp_server_key": "Bound"}
    result = await bound.ainvoke(
        {"server_name": "Bound", "task": "Read", "runtime": sentinel},
        config={"tags": ["identity-fixture"]},
    )
    assert result == "Read"
    runtime, config, callbacks = received[0]
    assert runtime is sentinel
    assert config["tags"] == ["identity-fixture"]
    assert callbacks is not None
    _invalid(await bound.ainvoke({"server_name": "Elsewhere", "task": "Read"}))
    assert len(received) == 1


def test_sync_callable_and_identity_snapshot_are_also_guarded() -> None:
    calls: list[str] = []

    def original(server_name: str, task: str) -> str:
        calls.append(server_name)
        return task

    source = StructuredTool.from_function(func=original, name="admin_alias", description="Task")
    identity = {"server_name": "Bound"}
    bound = bind_task_identity(source, identity)
    identity["server_name"] = "Elsewhere"
    assert bound.metadata is not None
    assert bound.metadata[MCP_TASK_IDENTITY_METADATA_KEY] == {"server_name": "Bound"}
    assert bound.func is not None
    _invalid(bound.func("Elsewhere", "Read"))
    assert bound.invoke({"server_name": "Bound", "task": "Read"}) == "Read"
    assert calls == ["Bound"]


@pytest.mark.asyncio
async def test_an_existing_real_effect_gate_is_reached_only_after_identity_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    policies: list[str] = []

    async def original(server_name: str, task: str) -> str:
        calls.append(server_name)
        return task

    def confirmation_policy(name: str) -> str:
        policies.append(name)
        return "confirm"

    monkeypatch.setattr(effect_runtime, "resolve_policy", confirmation_policy)
    monkeypatch.setattr(
        "src.domains.agents.context.runtime_context.runtime_context_if_running", lambda: None
    )
    coroutine = effect_runtime.gated("admin_alias", original)
    task = StructuredTool.from_function(coroutine=coroutine, name="admin_alias", description="Task")
    bound = bind_task_identity(task, {"server_name": "Bound"})
    assert bound.coroutine is not None
    _invalid(await bound.coroutine(server_name="Elsewhere", task="Read"))
    assert policies == [] and calls == []
    result = await bound.coroutine(server_name="Bound", task="Read")
    assert isinstance(result, UnifiedToolOutput)
    assert result.metadata["requires_confirmation"] is True
    assert policies == ["admin_alias"] and calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("rename", [False, True])
async def test_registry_matching_identity_keeps_exactly_one_current_confirmation_gate(
    monkeypatch: pytest.MonkeyPatch,
    rename: bool,
) -> None:
    calls: list[str] = []
    policies: list[str] = []

    async def original(server_name: str, task: str) -> str:
        calls.append(server_name)
        return task

    def confirmation_policy(name: str) -> str:
        policies.append(name)
        return "confirm"

    monkeypatch.setattr(effect_runtime, "resolve_policy", confirmation_policy)
    monkeypatch.setattr(
        "src.domains.agents.context.runtime_context.runtime_context_if_running", lambda: None
    )
    task = StructuredTool.from_function(coroutine=original, name="first_alias", description="Task")
    bound = bind_task_identity(task, {"server_name": "Bound"})
    _install_effect_gate(bound)
    if rename:
        bound = bound.model_copy(update={"name": "renamed_alias"})
    _install_effect_gate(bound)
    _install_effect_gate(bound)
    result = await bound.ainvoke({"server_name": "Bound", "task": "Read"})
    assert isinstance(result, UnifiedToolOutput)
    assert result.metadata["requires_confirmation"] is True
    assert policies == [bound.name] and calls == []


def test_identical_rebinding_reuses_guard_and_snapshots_its_metadata() -> None:
    def original(server_name: str) -> str:
        return server_name

    task = StructuredTool.from_function(func=original, name="task", description="Task")
    first = bind_task_identity(task, {"server_name": "Bound"})
    second = bind_task_identity(first, {"server_name": "Bound"})
    assert second.func is first.func
    assert second.metadata is not first.metadata
    assert second.metadata is not None and first.metadata is not None
    assert (
        second.metadata[MCP_TASK_IDENTITY_METADATA_KEY]
        is not first.metadata[MCP_TASK_IDENTITY_METADATA_KEY]
    )


@pytest.mark.asyncio
async def test_registry_re_gating_a_renamed_copy_does_not_unwrap_the_identity_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def original(server_name: str, task: str) -> str:
        calls.append(server_name)
        return task

    monkeypatch.setattr(effect_runtime, "resolve_policy", lambda name: None)
    source = StructuredTool.from_function(
        coroutine=original, name="first_alias", description="Task"
    )
    bound = bind_task_identity(source, {"server_name": "Bound"})
    _install_effect_gate(bound)
    renamed = bound.model_copy(update={"name": "second_alias"})
    _install_effect_gate(renamed)
    assert renamed.coroutine is not None
    _invalid(await renamed.coroutine(server_name="Elsewhere", task="Read"))
    assert calls == []
    assert await renamed.coroutine(server_name="Bound", task="Read") == "Read"
    assert calls == ["Bound"]


@pytest.mark.asyncio
@pytest.mark.parametrize("rename", [False, True])
@pytest.mark.parametrize("framework", [False, True])
async def test_registry_identity_refusal_precedes_confirmation_and_survives_reregistration(
    monkeypatch: pytest.MonkeyPatch,
    rename: bool,
    framework: bool,
) -> None:
    calls: list[str] = []
    policies: list[str] = []

    async def original(server_name: str, task: str) -> str:
        calls.append(server_name)
        return task

    def confirmation_policy(name: str) -> str:
        policies.append(name)
        return "confirm"

    monkeypatch.setattr(effect_runtime, "resolve_policy", confirmation_policy)
    monkeypatch.setattr(
        "src.domains.agents.context.runtime_context.runtime_context_if_running", lambda: None
    )
    source = StructuredTool.from_function(
        coroutine=original, name="first_alias", description="Task"
    )
    bound = bind_task_identity(source, {"server_name": "Bound"})
    _install_effect_gate(bound)
    if rename:
        bound = bound.model_copy(update={"name": "renamed_alias"})
    _install_effect_gate(bound)
    _install_effect_gate(bound)
    assert bound.coroutine is not None
    arguments = {"server_name": "Elsewhere", "task": "Read"}
    result = await bound.ainvoke(arguments) if framework else await bound.coroutine(**arguments)
    _invalid(result)
    assert policies == [] and calls == []


def test_binding_rejects_missing_or_unknown_identity_fields() -> None:
    def original(server_name: str) -> str:
        return server_name

    task = StructuredTool.from_function(func=original, name="task", description="Task")
    with pytest.raises(ValueError, match="declared callable parameters"):
        bind_task_identity(task, {})
    with pytest.raises(ValueError, match="declared callable parameters"):
        bind_task_identity(task, {"server_id_prefix": "wrong seam"})


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [False, True])
async def test_the_actual_generic_mcp_task_schema_cannot_override_its_named_identity(
    user: bool,
) -> None:
    from src.domains.agents.tools.mcp_react_tools import (
        mcp_server_task_tool,
        mcp_user_server_task_tool,
    )

    generic = mcp_user_server_task_tool if user else mcp_server_task_tool
    expected = {"server_name": "Bound"}
    supplied: dict[str, object] = {"server_name": "Elsewhere", "task": "Read", "runtime": None}
    if user:
        expected["server_id_prefix"] = "full-allocated-server-id"
        supplied["server_id_prefix"] = "full-allocated-server-id"
    named = generic.model_copy(update={"name": "synthetic_bound_task"})
    bound = bind_task_identity(named, expected)
    assert bound.args_schema is generic.args_schema
    assert bound.coroutine is not None
    _invalid(await bound.coroutine(**supplied))
