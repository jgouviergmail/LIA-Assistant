"""An unconfirmed effect ASKS instead of failing (ADR-263).

Refusing a tool the user could have confirmed is not safety, it is a capability
lost: the pipeline confirms nothing before execution, so a ``confirm`` tool
would be blocked for ever there. Measured before this change: such a tool ran
UNCONFIRMED (defect H2); after the gate alone: it could never run at all.

So the gate hands the call back as a DRAFT — the shape both execution modes
already know how to confirm. Nothing new is invented: the draft flows through
``pending_draft_critique``, the card the user already sees, and the executor
registry that already runs confirmed drafts. The only thing added is the draft
type and its executor.

Two boundaries the tests below pin:

- an UNATTENDED turn (a scheduled action) gets a refusal, not a card: there is
  nobody to answer it, and a draft nobody can confirm is a promise nobody keeps;
- the executor that replays the call is NOT itself ledgered — the tool's own
  gate records the effect under its real policy, and two rows for one effect
  would make the register lie about how much happened.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.scope import EffectScope, effect_scope

pytestmark = [pytest.mark.unit]

CALLS: list[dict[str, Any]] = []


async def _tool(**kwargs: Any) -> dict[str, Any]:
    CALLS.append(kwargs)
    return {"success": True, "data": {"id": "done-1"}}


@pytest.fixture(autouse=True)
def _reset() -> Any:
    CALLS.clear()
    gate_runtime.reset_policy_cache()
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id=__import__("uuid").uuid4(),
            thread_id="thread-A",
            execution_mode="pipeline",
            is_automated_source=False,
        ),
    ):
        yield


@pytest.fixture
def silent_ledger() -> Any:
    class _Ledger:
        def __init__(self) -> None:
            self.refusals: list[Any] = []
            self.claims: list[Any] = []

        async def claim(self, request: Any) -> Any:
            self.claims.append(request)
            return None

        async def close(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def refuse(self, request: Any, *, error_code: str) -> None:
            self.refusals.append((request, error_code))

    return _Ledger()


def _scope(**overrides: Any) -> EffectScope:
    base: dict[str, Any] = {
        "run_id": "run-1",
        "idempotency_key": "step:s1",
        "source": "user",
    }
    base.update(overrides)
    return EffectScope(**base)


class TestTheCallComesBackAsADraft:
    async def test_an_attended_confirm_asks_instead_of_failing(self, silent_ledger: Any) -> None:
        gated = gate_runtime.gated("mcp_era_cancel_subscription", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", silent_ledger),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
            effect_scope(_scope()),
        ):
            result = await gated(plan="premium")

        assert CALLS == [], "the tool must not run before the user answers"
        # The very shape the 25 draft-producing tools return, so every existing
        # path — card, queueing, batch, resume — handles it unchanged.
        payload = result.model_dump()
        assert payload["metadata"]["requires_confirmation"] is True
        assert payload["success"] is True, "asking is not failing"

    async def test_the_draft_carries_what_will_be_replayed(self, silent_ledger: Any) -> None:
        gated = gate_runtime.gated("mcp_era_cancel_subscription", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", silent_ledger),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
            effect_scope(_scope()),
        ):
            result = await gated(plan="premium")

        payload = result.model_dump()
        assert payload["metadata"]["draft_type"] == DraftType.TOOL_CALL.value

        draft_id, item = next(iter(payload["registry_updates"].items()))
        content = item["payload"]["content"]
        assert content["tool_name"] == "mcp_era_cancel_subscription"
        assert content["tool_args"] == {"plan": "premium"}
        assert content["tool_label"] == "era: cancel subscription"
        # ONE identity for one operation: the card the user answers, the resume
        # and the ledger all name the same draft.
        assert draft_id == payload["metadata"]["draft_id"]

    async def test_an_unattended_turn_is_refused_not_asked(self, silent_ledger: Any) -> None:
        """A draft nobody can confirm is a promise nobody keeps."""
        gated = gate_runtime.gated("mcp_era_cancel_subscription", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", silent_ledger),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
            effect_scope(_scope(source="scheduled")),
        ):
            result = await gated(plan="premium")

        assert CALLS == []
        assert result["success"] is False
        assert "requires_confirmation" not in result.get("metadata", {})
        assert silent_ledger.refusals, "the refusal is still a fact worth keeping"


class TestTheLabelTheUserReads:
    """The card says WHAT will run: the label is the only readable part of it."""

    def test_an_mcp_namespaced_tool_reads_as_words(self) -> None:
        """Real MCP servers namespace with a DOUBLE underscore.

        ``billing__cancel_subscription`` through a naive ``replace`` renders a
        double space on the card — measured on the Era server's own names.
        """
        from src.domains.agents.effects.confirmation import _readable_tool_name

        assert (
            _readable_tool_name("mcp_era_billing__cancel_subscription")
            == "era: billing cancel subscription"
        )

    def test_a_native_tool_keeps_its_words(self) -> None:
        from src.domains.agents.effects.confirmation import _readable_tool_name

        assert _readable_tool_name("delete_event_tool") == "delete event"

    def test_a_server_with_no_operation_still_reads(self) -> None:
        from src.domains.agents.effects.confirmation import _readable_tool_name

        assert _readable_tool_name("mcp_era") == "era"


class TestTheReplay:
    async def test_the_executor_runs_the_tool_under_an_approved_scope(self) -> None:
        from src.domains.agents.tools import tool_registry

        seen: list[EffectScope | None] = []

        async def _watching_tool(**kwargs: Any) -> dict[str, Any]:
            from src.domains.agents.effects.scope import current_scope

            seen.append(current_scope())
            return {"success": True, "data": {"id": "replayed"}}

        from langchain_core.tools import StructuredTool

        from src.domains.agents.effects.confirmation import execute_tool_call_draft

        tool = StructuredTool.from_function(
            coroutine=_watching_tool, name="replay_probe_tool", description="p"
        )
        tool_registry.register_external_tool(tool)

        with patch.object(gate_runtime, "resolve_policy", lambda _n: "read"):
            result = await execute_tool_call_draft(
                {"tool_name": "replay_probe_tool", "tool_args": {"x": 1}, "draft_id": "draft-9"},
                __import__("uuid").uuid4(),
                None,
            )

        assert result["success"] is True
        assert seen and seen[0] is not None
        assert seen[0].approved is True
        assert seen[0].approval_kind == "draft_critique"
        assert seen[0].idempotency_key == "call:draft-9"

    async def test_it_reuses_the_scope_the_draft_executor_published(self) -> None:
        """One operation, one identity — the real draft id, not an invented one."""
        from langchain_core.tools import StructuredTool

        from src.domains.agents.effects.confirmation import execute_tool_call_draft
        from src.domains.agents.effects.scope import current_scope
        from src.domains.agents.tools import tool_registry

        seen: list[EffectScope | None] = []

        async def _watching(**kwargs: Any) -> dict[str, Any]:
            seen.append(current_scope())
            return {"success": True}

        tool = StructuredTool.from_function(
            coroutine=_watching, name="replay_ambient_tool", description="p"
        )
        tool_registry.register_external_tool(tool)
        ambient = EffectScope(
            run_id="run-7",
            idempotency_key="draft:draft_real_id",
            source="user",
            approved=True,
            approval_kind="draft_critique",
            approval_ref="draft_real_id",
        )

        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            effect_scope(ambient),
        ):
            await execute_tool_call_draft(
                {"tool_name": "replay_ambient_tool", "tool_args": {}, "draft_id": "ignored"},
                __import__("uuid").uuid4(),
                None,
            )

        assert seen[0] is ambient

    async def test_an_unknown_tool_fails_honestly(self) -> None:
        from src.domains.agents.effects.confirmation import execute_tool_call_draft

        result = await execute_tool_call_draft(
            {"tool_name": "no_such_tool", "tool_args": {}, "draft_id": "d"},
            __import__("uuid").uuid4(),
            None,
        )
        assert result["success"] is False


class TestTheExecutorIsNotDoubleRecorded:
    def test_the_replay_executor_is_exempt_from_executor_gating(self) -> None:
        """One effect, one row: the TOOL's gate records it under its real policy.

        Gating the executor too would claim a second row — and worse, both
        would share the scope key, so the inner call would be mistaken for a
        replay and never run at all.
        """
        from src.domains.agents.services.draft_executor_types import (
            EXECUTORS_GATED_BY_THEIR_TOOL,
        )

        assert DraftType.TOOL_CALL.value in EXECUTORS_GATED_BY_THEIR_TOOL

    def test_the_exemption_is_a_closed_list(self) -> None:
        from src.domains.agents.services.draft_executor_types import (
            EXECUTORS_GATED_BY_THEIR_TOOL,
        )

        assert EXECUTORS_GATED_BY_THEIR_TOOL == frozenset({DraftType.TOOL_CALL.value})
