"""A tool the person chose « never ask » for runs under an approval of its own (spec D6, H7).

Its declaration owes a confirmation, so its policy stays ``confirm``; its manifest is
APPROVED IN ADVANCE. The effect gate reads that fact at the same point it reads a
routine's pre-approval and runs the call under an approved scope the register names
``standing_choice``, with the server as its reference — never the person's
``tool_confirmation``, which they did not give for this call. It runs when nobody is
there as well (D6: no routine pre-approval needed). A manifest without the fact is
refused exactly as before, and only the tool's OWN manifest carries it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.gate import ERROR_CONFIRMATION_IMPOSSIBLE
from src.domains.agents.effects.preapproval import STANDING_CHOICE_KIND, preapproved_scope
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.user_context import _build_user_tool_manifest
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = [pytest.mark.unit]

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}
REACHED: list[dict[str, Any]] = []


@contextmanager
def _turn(*, automated: bool) -> Iterator[None]:
    REACHED.clear()
    gate_runtime.reset_policy_cache()
    sink = AsyncMock()
    with (
        installed_shared_mcp_access() as actor,
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=actor.id,
                thread_id="thread-1",
                execution_mode="pipeline",
                is_automated_source=automated,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        treatment_collector(run_id="run-1"),
    ):
        yield
    gate_runtime.reset_policy_cache()


async def _server(self: UserMCPToolAdapter, **kwargs: Any) -> UnifiedToolOutput:
    REACHED.append(dict(kwargs))
    return UnifiedToolOutput.action_success(message="done")


def _destructive_tool(
    server_id: uuid.UUID, *, never_asked: bool
) -> tuple[UserMCPToolAdapter, ToolManifest]:
    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id=server_id,
        user_id=uuid.uuid4(),
        server_name="notes",
        tool_name="delete_note",
        description="Delete a note",
        input_schema=_SCHEMA,
        server_prefix="abcd1234",
    )
    manifest = _build_user_tool_manifest(
        adapter_name=adapter.name,
        tool_name=adapter.mcp_tool_name,
        description="Delete a note",
        input_schema=_SCHEMA,
        server_name="notes",
        server_domain="mcp_notes",
        hitl_required=False,
        annotations={"destructive_hint": True},
        server_key=str(server_id),
        standing_approval=never_asked,
    )
    return adapter, manifest


@contextmanager
def _offered(adapter: UserMCPToolAdapter, manifest: ToolManifest) -> Iterator[None]:
    ctx = UserMCPToolsContext(tool_manifests=[manifest], tool_instances={adapter.name: adapter})
    token = user_mcp_tools_ctx.set(ctx)
    offered = request_tool_manifests_ctx.set([manifest])
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(offered)
        user_mcp_tools_ctx.reset(token)


class _Ledger:
    def __init__(self) -> None:
        self.claims: list[Any] = []
        self.refusals: list[tuple[str, str]] = []

    async def claim(self, request: Any) -> Any:
        self.claims.append(request)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
        )

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def abandon(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        self.refusals.append((request.tool_name, error_code))


def _step(*, automated: bool = False) -> EffectScope:
    """What the executor publishes around a step nobody approved (a routine's: nobody there)."""
    return EffectScope(
        run_id="run-1",
        idempotency_key="run-1:step:s1",
        source="scheduled" if automated else "user",
    )


async def _call(
    adapter: UserMCPToolAdapter, manifest: ToolManifest, ledger: _Ledger, *, automated: bool
) -> None:
    with (
        _offered(adapter, manifest),
        patch.object(UserMCPToolAdapter, "_call_server", new=_server),
        patch.object(gate_runtime, "_LEDGER", ledger),
        effect_scope(_step(automated=automated)),
    ):
        await adapter.coroutine(note_id="n-1")


class TestTheGate:
    @pytest.mark.parametrize("automated", [False, True], ids=["attended", "unattended"])
    async def test_a_never_asked_destruction_runs_under_its_own_approval(
        self, automated: bool
    ) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id, never_asked=True)
        ledger = _Ledger()

        with _turn(automated=automated):
            await _call(adapter, manifest, ledger, automated=automated)

        assert REACHED == [{"note_id": "n-1"}], "the act ran, without a question"
        (claim,) = ledger.claims
        assert (claim.approval_kind, claim.approval_ref) == (STANDING_CHOICE_KIND, str(server_id))
        assert ledger.refusals == []

    async def test_without_the_choice_an_unattended_call_is_still_refused(self) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id, never_asked=False)
        ledger = _Ledger()

        with _turn(automated=True):
            await _call(adapter, manifest, ledger, automated=True)

        assert REACHED == [] and ledger.claims == []
        assert ledger.refusals == [(adapter.name, ERROR_CONFIRMATION_IMPOSSIBLE)]


class TestWhatAStandingChoiceCovers:
    def test_only_the_tool_s_own_offered_manifest_carries_it(self) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id, never_asked=True)
        scope = _step()

        with _turn(automated=False), _offered(adapter, manifest):
            approved = preapproved_scope(adapter.name, "confirm", scope)
            elsewhere = preapproved_scope(f"{adapter.name}_tool", "confirm", scope)

        assert approved is not None and approved.approved is True
        assert approved.approval_kind == STANDING_CHOICE_KIND
        assert elsewhere is scope, "a name resolving through a suffix is another tool"

    def test_a_scope_already_approved_keeps_its_own_approval(self) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id, never_asked=True)
        confirmed = replace(_step(), approved=True, approval_kind="tool_confirmation")

        with _turn(automated=False), _offered(adapter, manifest):
            assert preapproved_scope(adapter.name, "confirm", confirmed) is confirmed

    def test_no_published_authority_is_never_invented(self) -> None:
        server_id = uuid.uuid4()
        adapter, manifest = _destructive_tool(server_id, never_asked=True)

        with _turn(automated=False), _offered(adapter, manifest):
            assert preapproved_scope(adapter.name, "confirm", None) is None
