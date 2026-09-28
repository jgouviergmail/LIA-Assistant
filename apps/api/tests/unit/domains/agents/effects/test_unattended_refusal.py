"""The unattended refusal of a draft names the tool that stands in for it (ADR-314, amended).

The loop that received « this action waits for the user » did the only thing it
was told: it reported the action and sent nothing (production, 2026-09-27). The
refusal now says which tool performs it without a confirmation, and in which
case — the first rung of ADR-310's ladder, « the loop's own call corrected »,
made possible in the same turn. Only a loop can take that rung: the pipeline's
response node calls no tool, so the name is never given there.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.core.constants import EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.gate import ERROR_CONFIRMATION_IMPOSSIBLE
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.registry.catalogue import UnattendedStandIn

pytestmark = [pytest.mark.unit]

CASE = "the recipient is the user themselves"
STAND_IN = ("send_email_to_me_tool", CASE)


@pytest.fixture(autouse=True)
def _fresh_policies() -> None:
    gate_runtime.reset_policy_cache()


def _run_context(execution_mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-routine",
        execution_mode=execution_mode,
        is_automated_source=True,
    )


class _Ledger:
    """Records the refusals it is told about; claims nothing."""

    def __init__(self) -> None:
        self.refusals: list[str] = []

    async def claim(self, request: Any) -> None:
        return None

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        self.refusals.append(error_code)


async def _send(to: str = "me@example.org", subject: str = "News") -> dict[str, Any]:
    raise AssertionError("a refused draft must never run")


async def _refuse_unattended(
    stand_in: tuple[str, str] | None, *, run_context: SimpleNamespace | None
) -> str:
    """Run a draft send in a routine and return the message the model reads."""
    ledger = _Ledger()
    gated = gate_runtime.gated("send_email_tool", _send)
    with (
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=run_context,
        ),
        patch.object(gate_runtime, "_LEDGER", ledger),
        patch.object(gate_runtime, "resolve_policy", lambda _name: "draft"),
        patch.object(gate_runtime, "resolve_unattended_stand_in", lambda _name: stand_in),
        effect_scope(
            EffectScope(run_id="run-routine", idempotency_key="call:c1", source="scheduled")
        ),
    ):
        result: dict[str, Any] = await gated(to="me@example.org", subject="News")
    assert result["success"] is False
    expected = [ERROR_CONFIRMATION_IMPOSSIBLE] if run_context is not None else []
    assert ledger.refusals == expected, "the refusal is recorded whenever an identity exists"
    message: str = result["error"]
    assert message.endswith(f"[{ERROR_CONFIRMATION_IMPOSSIBLE}]")
    assert "Nothing was performed" in message, "it must still say nothing happened"
    assert "never announce it as done" in message, "and keep the honest fallback"
    return message


class TestTheRefusalNamesTheStandIn:
    async def test_a_react_loop_is_told_the_tool_and_its_case(self) -> None:
        message = await _refuse_unattended(STAND_IN, run_context=_run_context(EXECUTION_MODE_REACT))

        assert f"If {CASE} and `send_email_to_me_tool` is among your tools" in message

    async def test_without_a_stand_in_the_refusal_is_unchanged(self) -> None:
        message = await _refuse_unattended(None, run_context=_run_context(EXECUTION_MODE_REACT))

        assert "`" not in message, "no tool is named when none was declared"
        assert "Report that the action is waiting for the user" in message

    async def test_the_pipeline_is_never_told_a_tool_it_cannot_call(self) -> None:
        """The response node calls no tool: a name would invite a false promise."""
        message = await _refuse_unattended(
            STAND_IN, run_context=_run_context(EXECUTION_MODE_PIPELINE)
        )

        assert "send_email_to_me_tool" not in message

    async def test_a_call_with_no_run_context_names_nothing(self) -> None:
        message = await _refuse_unattended(STAND_IN, run_context=None)

        assert "send_email_to_me_tool" not in message


def _registry(*manifests: Any) -> Any:
    return SimpleNamespace(list_tool_manifests=lambda: list(manifests))


class TestTheResolverReadsTheDeclaration:
    def test_it_finds_the_tool_that_declared_itself(self) -> None:
        registry = _registry(
            SimpleNamespace(name="send_email_tool", stands_in_unattended_for=None),
            SimpleNamespace(
                name="send_email_to_me_tool",
                stands_in_unattended_for=UnattendedStandIn("send_email_tool", CASE),
            ),
        )
        with patch("src.domains.agents.registry.get_global_registry", return_value=registry):
            assert gate_runtime.resolve_unattended_stand_in("send_email_tool") == STAND_IN
            assert gate_runtime.resolve_unattended_stand_in("create_event_tool") is None

    def test_an_unreadable_catalogue_offers_nothing(self) -> None:
        """A refusal must never fail because the catalogue could not be read."""
        with patch(
            "src.domains.agents.registry.get_global_registry",
            side_effect=RuntimeError("not initialised"),
        ):
            assert gate_runtime.resolve_unattended_stand_in("send_email_tool") is None
