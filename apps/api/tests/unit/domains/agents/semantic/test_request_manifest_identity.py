"""Semantic contracts follow the exact identity of the request's offered tools."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Literal
from uuid import UUID

import pytest

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents import registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    CostProfile,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic.manifest_semantics import available_manifest, available_manifests
from src.domains.agents.semantic.param_guard import check_semantic_params
from src.infrastructure.mcp.registration import build_mcp_react_task_manifest

pytestmark = pytest.mark.unit
FIRST = UUID("11111111-2222-3333-4444-555555555555")
SECOND = UUID("11111111-9222-3333-4444-555555555555")
ALIAS = "mcp_user_11111111_send"


def _manifest(
    name: str = ALIAS,
    *,
    origin: Literal["admin", "user"] | None = "user",
    key: str | None = str(FIRST),
    semantic_type: str = "email_address",
) -> ToolManifest:
    return ToolManifest(
        name=name,
        agent="mcp_people_agent",
        description="Account-specific semantic contract",
        parameters=[
            ParameterSchema("to", "string", True, "Recipient", semantic_type=semantic_type)
        ],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mcp_origin=origin,
        mcp_server_key=key,
    )


def _task(
    name: str = "mcp_user_11111111_task",
    *,
    origin: Literal["admin", "user"] | None = "user",
    key: str | None = str(FIRST),
) -> ToolManifest:
    return build_mcp_react_task_manifest(
        name,
        "mcp_people_agent",
        "People",
        "Read account-owned people",
        [],
        [],
        mcp_origin=origin,
        mcp_server_key=key,
    )


@contextmanager
def _request(
    offered: list[ToolManifest] | None,
    context: UserMCPToolsContext | None = None,
) -> Iterator[None]:
    request_token = request_tool_manifests_ctx.set(offered)
    user_token = user_mcp_tools_ctx.set(context)
    try:
        yield
    finally:
        user_mcp_tools_ctx.reset(user_token)
        request_tool_manifests_ctx.reset(request_token)


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> AgentRegistry:
    instance = AgentRegistry()
    monkeypatch.setattr(registry_module, "get_global_registry", lambda: instance)
    return instance


@pytest.mark.parametrize("suffix", ["", "_tool", "_action"])
def test_offered_personal_contract_wins_over_a_global_admin_namesake(
    registry: AgentRegistry, suffix: str
) -> None:
    admin = _manifest(origin="admin", key="user_11111111")
    personal = _manifest(semantic_type="Text")
    registry.register_tool_manifest(admin)
    with _request([personal]):
        assert available_manifest(f"{ALIAS}{suffix}") is personal
        assert check_semantic_params(f"{ALIAS}{suffix}", {"to": "Ada"}, {"ada"}) is None


@pytest.mark.parametrize("reverse", [False, True])
def test_two_offered_owners_with_one_alias_fail_closed(reverse: bool) -> None:
    offered = [_manifest(origin="admin", key="user_11111111"), _manifest()]
    if reverse:
        offered.reverse()
    with _request(offered):
        assert available_manifest(ALIAS) is None
        assert available_manifest(f"{ALIAS}_tool") is None


def test_explicit_empty_offer_cannot_resurrect_a_global_contract(registry: AgentRegistry) -> None:
    manifest = _manifest()
    registry.register_tool_manifest(manifest)
    with _request([]):
        assert available_manifest(manifest.name) is None
        assert available_manifests() == []


def test_unbound_diagnostics_keep_the_legacy_global_contract(registry: AgentRegistry) -> None:
    manifest = _manifest("legacy_tool", origin=None, key=None)
    registry.register_tool_manifest(manifest)
    with _request(None):
        assert available_manifest(manifest.name) is manifest
        assert available_manifest("absent_tool") is None


def test_directly_offered_legacy_contract_needs_no_mcp_identity() -> None:
    manifest = _manifest("native_lookup", origin=None, key=None)
    with _request([manifest]):
        assert available_manifest(manifest.name) is manifest


@pytest.mark.parametrize("suffix", ["", "_tool", "_action"])
def test_reactive_contract_uses_full_owner_identity_even_with_unrelated_aliases(
    suffix: str,
) -> None:
    candidate = _manifest("mcp_account_long_collision_safe_send")
    task = _task("mcp_personal_long_collision_safe_task")
    context = UserMCPToolsContext(
        tool_manifests=[task], reactive_tool_manifests={candidate.name: candidate}
    )
    with _request([task], context):
        assert available_manifest(f"{candidate.name}{suffix}") is candidate
        assert available_manifests() == [task]
        assert check_semantic_params(candidate.name, {"to": "Ada"}, {"ada"}) is not None


@pytest.mark.parametrize(
    "task",
    [
        _task(key=str(SECOND)),
        _task(origin="admin", key=str(FIRST)),
        _task(origin=None, key=None),
        replace(_task(), delegates_execution=False),
    ],
    ids=["another-full-uuid", "admin-origin", "legacy-prefix-only", "nondelegating-tool"],
)
def test_matching_textual_prefix_does_not_admit_an_unowned_reactive_contract(
    task: ToolManifest,
) -> None:
    candidate = _manifest()
    context = UserMCPToolsContext(
        tool_manifests=[task], reactive_tool_manifests={candidate.name: candidate}
    )
    with _request([task], context):
        assert available_manifest(candidate.name) is None


def test_shared_uuid_prefix_does_not_merge_two_reactive_catalogues() -> None:
    first = _manifest("mcp_first_send")
    second = _manifest("mcp_second_send", key=str(SECOND), semantic_type="Text")
    first_task = _task("mcp_first_task")
    second_task = _task("mcp_second_task", key=str(SECOND))
    context = UserMCPToolsContext(
        tool_manifests=[first_task, second_task],
        reactive_tool_manifests={first.name: first, second.name: second},
    )
    with _request([second_task], context):
        assert available_manifest(first.name) is None
        assert available_manifest(second.name) is second
        assert check_semantic_params(second.name, {"to": "Ada"}, {"ada"}) is None
    with _request([first_task], context):
        assert available_manifest(first.name) is first
        assert available_manifest(second.name) is None


def test_an_offered_exact_contract_keeps_precedence_over_a_reactive_namesake() -> None:
    offered = _manifest(origin="admin", key="People", semantic_type="Text")
    candidate = _manifest()
    task = _task()
    context = UserMCPToolsContext(
        tool_manifests=[task], reactive_tool_manifests={candidate.name: candidate}
    )
    with _request([offered, task], context):
        assert available_manifest(ALIAS) is offered


def test_duplicate_exact_offers_never_fall_back_to_a_reactive_namesake() -> None:
    candidate = _manifest()
    task = _task()
    offered = [_manifest(origin="admin", key="People"), _manifest(), task]
    context = UserMCPToolsContext(
        tool_manifests=[task], reactive_tool_manifests={candidate.name: candidate}
    )
    with _request(offered, context):
        assert available_manifest(ALIAS) is None
