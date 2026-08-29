"""Behavioural proof that migrated readers take their values from the typed context.

The ratchet guard (``test_configurable_reader_ratchet.py``) proves a file no longer
*reads the bag*; it cannot prove the replacement reads the *right* value. That is
what this file does, wave by wave: install a context whose values differ from the
defaults, call the migrated code, and assert the context's value came through.

Each test is deliberately written so it would still pass against the pre-migration
code ONLY if that code read the same value — the assertions are on behaviour, not
on the mechanism.

Context: ADR-231, task 11.
"""

import uuid

import pytest

from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime


@pytest.mark.unit
class TestRouterNodeExecutionMode:
    """``router_node_v3`` publishes the run's execution mode into the state."""

    def test_execution_mode_comes_from_the_typed_context(self) -> None:
        from src.domains.agents.nodes.router_node_v3 import _resolve_execution_mode

        with installed_runtime_context(execution_mode="react"):
            assert _resolve_execution_mode() == "react"

    def test_execution_mode_falls_back_to_the_canonical_default_outside_a_run(self) -> None:
        """A direct call (unit test, script) has no run; the default must be the
        centralized constant, never an inline literal."""
        from src.core.constants import EXECUTION_MODE_PIPELINE
        from src.domains.agents.nodes.router_node_v3 import _resolve_execution_mode

        assert _resolve_execution_mode() == EXECUTION_MODE_PIPELINE


@pytest.mark.unit
class TestToolsReadTheContext:
    """Tools receive the context on their injected ``ToolRuntime``."""

    def test_validated_runtime_config_takes_the_identity_from_the_context(self) -> None:
        from src.domains.agents.tools.runtime_helpers import (
            ValidatedRuntimeConfig,
            validate_runtime_config,
        )

        # The two planes are made to DISAGREE on purpose: with the same value in
        # both, this test would pass against the pre-migration code and prove
        # nothing. Only a reader that takes the context wins here.
        context_user = uuid.uuid4()
        runtime = make_tool_runtime(
            user_id=context_user,
            configurable={"user_id": "stale-value-from-the-bag"},
            store=object(),
        )

        result = validate_runtime_config(runtime, "any_tool")

        assert isinstance(result, ValidatedRuntimeConfig)
        assert result.user_id == str(context_user), (
            "the identity must come from the typed context, projected to the string "
            "the tool layer and the Store namespaces expect"
        )

    def test_validated_runtime_config_refuses_a_runtime_without_a_context(self) -> None:
        """A tool reached outside the agent layer gets a structured error, never a
        silently wrong identity."""
        from langchain.tools import ToolRuntime

        from src.domains.agents.tools.output import UnifiedToolOutput
        from src.domains.agents.tools.runtime_helpers import validate_runtime_config

        contextless = ToolRuntime(
            state=None,
            context=None,
            config={"configurable": {"thread_id": "t", "user_id": "u"}},
            stream_writer=lambda _: None,
            tool_call_id=None,
            store=object(),
        )

        result = validate_runtime_config(contextless, "any_tool")

        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
