"""The gate reads a personal MCP tool's policy from the turn's offered manifest (spec D2).

Measured 2026-10-29 (probes H1/H2): a personal server's manifest declared
``confirm`` and the gate read nothing, because it only asked the global
registry — which never holds a personal tool. A Pipeline step therefore ran a
declared destructive tool without asking. The gate now falls back to the
manifest the turn OFFERED, and never memoises it: a personal server's setting
changes between turns, and an 8-hex name prefix is not an account boundary.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.user_context import _build_user_tool_manifest
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = [pytest.mark.unit]

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}
_DESTRUCTIVE = {"destructive_hint": True, "read_only_hint": False}
_ADDITIVE = {"destructive_hint": False, "read_only_hint": False}
REACHED: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def _turn() -> Iterator[None]:
    REACHED.clear()
    gate_runtime.reset_policy_cache()
    sink = AsyncMock()
    with (
        installed_shared_mcp_access() as actor,
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=actor.id,
                thread_id="thread-offered",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        treatment_collector(run_id="offered-manifest"),
    ):
        yield
    gate_runtime.reset_policy_cache()


async def _server(self: UserMCPToolAdapter, **kwargs: Any) -> UnifiedToolOutput:
    REACHED.append(dict(kwargs))
    return UnifiedToolOutput.action_success(message="done")


def _adapter(server_id: uuid.UUID, tool: str = "delete_note", **built: Any) -> UserMCPToolAdapter:
    return UserMCPToolAdapter.from_discovered_tool(
        server_id=server_id,
        user_id=uuid.uuid4(),
        server_name="notes",
        tool_name=tool,
        description=f"{tool} on the notes server",
        input_schema=_SCHEMA,
        server_prefix="abcd1234",
        **built,
    )


def _manifest(
    adapter: UserMCPToolAdapter,
    server_id: uuid.UUID,
    *,
    hitl: bool,
    annotations: dict[str, Any] | None,
) -> ToolManifest:
    return _build_user_tool_manifest(
        adapter_name=adapter.name,
        tool_name=adapter.mcp_tool_name,
        description="A tool of the notes server",
        input_schema=_SCHEMA,
        server_name="notes",
        server_domain="mcp_notes",
        hitl_required=hitl,
        annotations=annotations,
        server_key=str(server_id),
    )


@contextmanager
def _offered(adapter: UserMCPToolAdapter, manifest: ToolManifest) -> Iterator[None]:
    """What the turn installs: the account's context and the catalogue it offers."""
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


def _pipeline_step() -> EffectScope:
    """What ``parallel_executor`` publishes around a step: nothing approved."""
    return EffectScope(run_id="run-offered", idempotency_key="run-offered:step:s1", source="user")


class TestThePolicyComesFromTheOfferedManifest:
    async def test_personal_confirm_tool_becomes_a_draft_in_pipeline(self) -> None:
        server_id = uuid.uuid4()
        adapter = _adapter(server_id)
        ledger = _Ledger()
        with (
            _offered(adapter, _manifest(adapter, server_id, hitl=True, annotations=None)),
            patch.object(UserMCPToolAdapter, "_call_server", new=_server),
            patch.object(gate_runtime, "_LEDGER", ledger),
            effect_scope(_pipeline_step()),
        ):
            result = await adapter.coroutine(note_id="n-1")

        assert REACHED == [], "a confirm tool reached its server unasked"
        assert result.tool_metadata["requires_confirmation"] is True
        assert ledger.claims == [], "an unconfirmed act is never claimed"

    async def test_an_additive_personal_tool_is_recorded_under_its_step(self) -> None:
        server_id = uuid.uuid4()
        adapter = _adapter(server_id, "label_note")
        ledger = _Ledger()
        with (
            _offered(adapter, _manifest(adapter, server_id, hitl=False, annotations=_ADDITIVE)),
            patch.object(UserMCPToolAdapter, "_call_server", new=_server),
            patch.object(gate_runtime, "_LEDGER", ledger),
            effect_scope(_pipeline_step()),
        ):
            await adapter.coroutine(note_id="n-1")

        assert REACHED == [{"note_id": "n-1"}]
        assert ledger.claims == ["run-offered:step:s1"]

    def test_personal_policy_is_never_memoised(self) -> None:
        server_id = uuid.uuid4()
        adapter = _adapter(server_id)

        with _offered(adapter, _manifest(adapter, server_id, hitl=True, annotations=None)):
            first = gate_runtime.resolve_policy(adapter.name)
        # The person switched the confirmation off and the tool declares an
        # additive update: the next turn offers another manifest.
        with _offered(adapter, _manifest(adapter, server_id, hitl=False, annotations=_ADDITIVE)):
            second = gate_runtime.resolve_policy(adapter.name)

        assert (first, second) == ("confirm", "reversible")
        assert gate_runtime.resolve_policy(adapter.name) is None, "no turn, no offered manifest"

    async def test_two_accounts_same_prefix_keep_their_own_policy(self) -> None:
        """Two servers whose ids share 8 hex characters get the same adapter name."""
        first, second = uuid.uuid4(), uuid.uuid4()
        mine, theirs = _adapter(first), _adapter(second)
        assert mine.name == theirs.name

        async def _read(
            adapter: UserMCPToolAdapter, server_id: uuid.UUID, hitl: bool
        ) -> tuple[str | None, str | None]:
            manifest = _manifest(adapter, server_id, hitl=hitl, annotations=_ADDITIVE)
            with _offered(adapter, manifest):
                before = gate_runtime.resolve_policy(adapter.name)
                await asyncio.sleep(0)  # the other account reads in between
                return before, gate_runtime.resolve_policy(adapter.name)

        readings = await asyncio.gather(_read(mine, first, True), _read(theirs, second, False))

        assert readings == [("confirm", "confirm"), ("reversible", "reversible")]

    def test_a_suffix_alias_never_lends_another_tool_its_policy(self) -> None:
        """Only the tool's own declaration polices it — never a near namesake's."""
        server_id = uuid.uuid4()
        adapter = _adapter(server_id, "export")
        with _offered(adapter, _manifest(adapter, server_id, hitl=True, annotations=None)):
            assert gate_runtime.resolve_policy(adapter.name) == "confirm"
            assert gate_runtime.resolve_policy(f"{adapter.name}_tool") is None


class TestTheCurrentDeclarationStillHasTheLastWord:
    """ADR-366: a tool turned destructive AFTER the offer is refused, never sent.

    The gate decides on the OFFERED declaration; the pool re-reads the server's
    current one before an unverified call. Reading the offered manifest must not
    pre-empt that check (lia-cd, 2026-10-30).
    """

    async def test_a_tool_turned_destructive_after_the_offer_is_refused_unsent(self) -> None:
        from src.infrastructure.mcp.catalogue_snapshot import build_snapshot
        from src.infrastructure.mcp.user_pool import UserMCPClientPool

        declared = {
            "name": "archive_note",
            "description": "Archive a note",
            "input_schema": _SCHEMA,
            "output_schema": None,
            "title": None,
            "annotations": None,
            "app_resource_uri": None,
            "app_visibility": None,
        }
        server_id, user_id = uuid.uuid4(), uuid.uuid4()
        pool = UserMCPClientPool()
        pool._raise_if_cooling = AsyncMock()  # type: ignore[method-assign]
        pool._check_rate_limit = AsyncMock()  # type: ignore[method-assign]
        entry = pool.hydrate(
            user_id=user_id,
            server_id=server_id,
            url="https://notes.example/mcp",
            auth=None,
            timeout_seconds=30,
            extra_headers=None,
            snapshot=build_snapshot(
                tools=[declared],
                configuration_fingerprint="cfg",
                discovered_at=datetime.now(UTC),
                generation=1,
            ),
            verified=False,
        )
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=server_id,
            user_id=user_id,
            server_name="notes",
            tool_name="archive_note",
            description="Archive a note",
            input_schema=_SCHEMA,
            server_prefix="abcd1234",
            built_from=entry.catalogue_fingerprint,
            declaration=declared,
        )
        sent: list[str] = []

        class _Session:
            async def list_tools(self, **_: Any) -> Any:
                now = SimpleNamespace(
                    name="archive_note",
                    description="Archive a note",
                    input_schema=_SCHEMA,
                    output_schema=None,
                    annotations={"readOnlyHint": False, "destructiveHint": True},
                    title=None,
                    meta=None,
                )
                return SimpleNamespace(tools=[now], next_cursor=None)

            async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
                sent.append(name)
                return SimpleNamespace(is_error=False, content=[SimpleNamespace(text="ok")])

        @asynccontextmanager
        async def _ephemeral(*_: Any, **__: Any) -> AsyncIterator[_Session]:
            yield _Session()

        manifest = _manifest(adapter, server_id, hitl=False, annotations=None)
        assert manifest.mutation_policy is None, "offered as harmless: the gate lets it through"
        with (
            _offered(adapter, manifest),
            patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool),
            patch("src.infrastructure.mcp.user_pool._ephemeral_client", _ephemeral),
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            effect_scope(_pipeline_step()),
        ):
            result = await adapter.coroutine(note_id="n-1")

        assert sent == [], "the server's current declaration refused the call: never sent"
        assert result.success is False
        assert result.metadata["reason"] == "tightened"
