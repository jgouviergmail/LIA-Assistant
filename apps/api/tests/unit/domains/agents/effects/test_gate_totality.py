"""A gate on every capability must survive every way a capability is CALLED.

Three holes found by cold review on 2026-09-04, each of which turns the gate
from a safeguard into an outage or a lie:

1. **Positional arguments.** ``set_current_item`` calls
   ``resolve_reference.coroutine(reference, runtime, domain)`` — three
   positionals. A keyword-only wrapper raises ``TypeError`` there, breaking
   reference resolution outright.
2. **A renamed copy.** ``registration.py`` registers
   ``mcp_server_task_tool.model_copy(update={"name": ...})`` once per MCP
   server. The copy carries the gate of the ORIGINAL, closed over the original
   name — so every server's task tool would resolve the wrong policy and land
   in the register under a name that is not its own. A register that names the
   wrong actor is worse than no register.
3. **A lost claim with nothing to serve.** Losing the claim means the effect
   already happened *or is happening right now*: the winner may not have
   written its result yet. Returning its ``None`` hands the model a null where
   a tool result belongs.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.tools import StructuredTool

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.effects.scope import EffectScope, effect_scope

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _attended_user() -> Any:
    gate_runtime.reset_policy_cache()
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id=uuid.uuid4(),
            thread_id="thread-totality",
            execution_mode="pipeline",
            is_automated_source=False,
        ),
    ):
        yield


def _scope(**overrides: Any) -> EffectScope:
    base: dict[str, Any] = {"run_id": "run-1", "idempotency_key": "step:s1", "source": "user"}
    base.update(overrides)
    return EffectScope(**base)


class TestAPositionalCallStillWorks:
    """The measured caller: ``resolve_reference.coroutine(a, b, c)``."""

    async def test_a_read_passes_positional_arguments_through(self) -> None:
        seen: list[tuple[Any, ...]] = []

        async def _tool(reference: str, runtime: Any = None, domain: str | None = None) -> Any:
            seen.append((reference, runtime, domain))
            return {"success": True}

        gated = gate_runtime.gated("resolve_reference", _tool)
        with patch.object(gate_runtime, "resolve_policy", lambda _n: "read"):
            await gated("le premier", "runtime-obj", "contact")

        assert seen == [("le premier", "runtime-obj", "contact")]

    async def test_a_mutation_records_positional_arguments_by_NAME(self) -> None:
        """The evidence must not depend on how the caller spelled the call."""
        claims: list[Any] = []

        class _Ledger:
            async def claim(self, request: Any) -> Any:
                claims.append(request)
                return None

            async def close(self, *a: Any, **k: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        async def _tool(room: str, brightness: int = 50) -> Any:
            return {"success": True}

        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            await gated("Salon", 80)

        keyword_digest = gate_runtime.args_digest(
            "control_hue_light_tool", {"room": "Salon", "brightness": 80}
        )
        assert claims[0].args_digest == keyword_digest

    async def test_a_confirmation_draft_replays_positional_arguments(self) -> None:
        """The replay calls ``coroutine(**tool_args)``: names or nothing."""

        class _Ledger:
            async def claim(self, request: Any) -> Any:
                return None

            async def close(self, *a: Any, **k: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        async def _tool(room: str, brightness: int = 50) -> Any:
            return {"success": True}

        gated = gate_runtime.gated("mcp_era_cancel_subscription", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
            effect_scope(_scope()),
        ):
            result = await gated("Salon", 80)

        payload = result.model_dump()
        _draft_id, item = next(iter(payload["registry_updates"].items()))
        assert item["payload"]["content"]["tool_args"] == {"room": "Salon", "brightness": 80}


class TestTheEvidenceIsAboutTheCallNotThePlumbing:
    """A digest that changes on its own answers no question at all."""

    async def test_two_identical_calls_digest_identically(self) -> None:
        """The executor injects a fresh ``ToolRuntime`` per call.

        It has no value identity, so ``str()`` of it carries its ADDRESS: kept
        in the evidence, the same call made twice would look like two
        different calls, and the register could never say otherwise.
        """
        claims: list[Any] = []

        class _Ledger:
            async def claim(self, request: Any) -> Any:
                claims.append(request)
                return None

            async def close(self, *a: Any, **k: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        class _Runtime:
            """Stands in for ``ToolRuntime``: no ``__eq__``, default repr."""

        async def _tool(room: str, runtime: Any = None) -> Any:
            return {"success": True}

        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            await gated(room="Salon", runtime=_Runtime())
            await gated(room="Salon", runtime=_Runtime())

        assert claims[0].args_digest == claims[1].args_digest

    async def test_the_arguments_that_carry_intent_still_separate_calls(self) -> None:
        """Anti-vacuity: the digest is not simply constant."""
        claims: list[Any] = []

        class _Ledger:
            async def claim(self, request: Any) -> Any:
                claims.append(request)
                return None

            async def close(self, *a: Any, **k: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        async def _tool(room: str, runtime: Any = None) -> Any:
            return {"success": True}

        gated = gate_runtime.gated("control_hue_light_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            await gated(room="Salon", runtime=None)
            await gated(room="Chambre", runtime=None)

        assert claims[0].args_digest != claims[1].args_digest


class TestARenamedCopyIsGatedUnderItsOwnName:
    """One MCP server's task tool must not act under another's name."""

    def test_reregistering_a_renamed_copy_rebinds_the_gate(self) -> None:
        from src.domains.agents.tools import tool_registry

        async def _run(x: int = 1) -> dict[str, Any]:
            return {"success": True}

        original = StructuredTool.from_function(
            coroutine=_run, name="server_task_probe_tool", description="t"
        )
        tool_registry.register_external_tool(original)

        renamed = original.model_copy(update={"name": "mcp_era_task_probe_tool"})
        tool_registry.register_external_tool(renamed)

        assert (
            getattr(renamed.coroutine, gate_runtime.EFFECT_GATED_NAME_ATTR, None)
            == "mcp_era_task_probe_tool"
        ), "the copy still acts under the original tool's identity"

    async def test_the_rebound_gate_resolves_the_copys_policy(self) -> None:
        from src.domains.agents.tools import tool_registry

        seen: list[str] = []

        async def _run(x: int = 1) -> dict[str, Any]:
            return {"success": True}

        original = StructuredTool.from_function(
            coroutine=_run, name="policy_probe_original_tool", description="t"
        )
        tool_registry.register_external_tool(original)
        renamed = original.model_copy(update={"name": "policy_probe_renamed_tool"})
        tool_registry.register_external_tool(renamed)

        def _policy(name: str) -> str:
            seen.append(name)
            return "read"

        with patch.object(gate_runtime, "resolve_policy", _policy):
            await renamed.coroutine(x=1)

        assert seen == ["policy_probe_renamed_tool"]

    def test_the_gate_is_not_nested_when_the_name_is_unchanged(self) -> None:
        """Re-registering the same tool must stay a no-op."""
        from src.domains.agents.tools import tool_registry

        async def _run(x: int = 1) -> dict[str, Any]:
            return {"success": True}

        tool = StructuredTool.from_function(
            coroutine=_run, name="stable_name_probe_tool", description="t"
        )
        tool_registry.register_external_tool(tool)
        once = tool.coroutine
        tool_registry.register_external_tool(tool)

        assert tool.coroutine is once


class TestALostClaimNeverReturnsNothing:
    """The winner may still be in flight: there is nothing to serve yet."""

    async def test_an_in_flight_duplicate_gets_an_honest_answer(self) -> None:
        class _Ledger:
            async def claim(self, request: Any) -> Any:
                return ClaimTicket(effect_id=uuid.uuid4(), claim_token=None, served_result=None)

            async def close(self, *a: Any, **k: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        calls: list[int] = []

        async def _tool(room: str = "Salon") -> Any:
            calls.append(1)
            return {"success": True}

        gated = gate_runtime.gated("send_email_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            result = await gated(room="Salon")

        assert calls == [], "the effect must not be repeated"
        assert result is not None, "a tool result slot must never be filled with None"
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "already" in str(result).lower() or "en cours" in str(result).lower()

    async def test_a_recorded_result_is_still_served_verbatim(self) -> None:
        """No regression: when the winner DID record, that is the answer."""

        class _Ledger:
            async def claim(self, request: Any) -> Any:
                return ClaimTicket(
                    effect_id=uuid.uuid4(),
                    claim_token=None,
                    served_result={"success": True, "data": {"id": "msg-1"}},
                )

            async def close(self, *a: Any, **k: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        async def _tool(room: str = "Salon") -> Any:
            return {"success": True, "data": {"id": "SECOND-SEND"}}

        gated = gate_runtime.gated("send_email_tool", _tool)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(_scope()),
        ):
            result = await gated(room="Salon")

        assert result == {"success": True, "data": {"id": "msg-1"}}
