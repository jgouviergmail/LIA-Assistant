"""« No connector is active » is a TYPED failure, read in both execution modes.

Production 2026-10-07, 18:13: an account with no mail connector asked about
its mail. The answer was right — « no mail service is connected; connect one
from the connectors settings » — but it was right through the WRONG channel:
the validator's ``UNAUTHORIZED`` verdict, kept as « blocked » because the step
had failed. A step that ran is never « blocked » any more (RC1.2), so the
failures directive must say it on its own: the code enters ``ToolErrorCode``
(a free string degraded to ``UNKNOWN`` on its way to that directive) and
travels with the failure in the pipeline AND in the ReAct loop.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.core.field_names import FIELD_ERROR_CODE
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.nodes.react_call_execution import _process
from src.domains.agents.orchestration import parallel_executor as pe
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.tools.base import APIKeyConnectorTool, ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.models import ConnectorType, get_connector_display_name
from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES
from src.domains.diagnostics.failure_context import (
    extract_failures_from_steps,
    extract_failures_from_tool_messages,
)

pytestmark = [pytest.mark.unit]

_CODE = ToolErrorCode.CONNECTOR_NOT_ACTIVATED.value


def _category_failure() -> UnifiedToolOutput:
    """What a category tool answers when no provider serves the category."""
    return ConnectorTool._format_category_not_activated_error(SimpleNamespace(), "email", "en")


class TestEveryFormatterEmitsTheTypedCode:
    """Three formatters say « not connected »; one code says it to the directive."""

    def test_a_category_without_any_provider(self) -> None:
        assert _category_failure().error_code == _CODE

    def test_a_provider_bound_connector(self) -> None:
        owner = SimpleNamespace(connector_type=ConnectorType.GOOGLE_GMAIL)
        failure = ConnectorTool._format_connector_not_activated_error(owner, "en")
        assert failure.error_code == _CODE

    def test_a_connector_waiting_for_the_person_s_own_key(self) -> None:
        owner = SimpleNamespace(connector_type=ConnectorType.PERPLEXITY)
        failure = APIKeyConnectorTool._format_connector_not_activated_error(owner, "en")
        assert failure.error_code == _CODE


class TestTheSentenceNamesTheConnectorAsTheSettingsDo:
    """One name per connector: the one the connectors settings show.

    The OAuth formatter named the enum value (« The google_gmail service… ») and
    the key formatter kept a private copy of the display names, already drifted
    (« Perplexity AI » where ``CONNECTOR_DISPLAY_NAMES`` says « Perplexity »,
    Brave Search named ``brave_search``). A refused draft's card names it from
    ``CONNECTOR_DISPLAY_NAMES``; the tool path now says the same name.
    """

    def test_a_provider_bound_connector(self) -> None:
        owner = SimpleNamespace(connector_type=ConnectorType.GOOGLE_GMAIL)
        failure = ConnectorTool._format_connector_not_activated_error(owner, "en")
        assert failure.message == APIMessages.connector_not_activated("Gmail", "en")

    @pytest.mark.parametrize(
        "connector", [ConnectorType.PERPLEXITY, ConnectorType.BRAVE_SEARCH], ids=lambda c: c.value
    )
    def test_a_connector_waiting_for_the_person_s_own_key(self, connector: ConnectorType) -> None:
        owner = SimpleNamespace(connector_type=connector)
        failure = APIKeyConnectorTool._format_connector_not_activated_error(owner, "en")
        assert failure.message == APIMessages.connector_not_activated(
            get_connector_display_name(connector), "en", needs_api_key=True
        )


@pytest.mark.asyncio
class TestThePipelineCarriesTheCode:
    """Formatter → executor → step result → completed_steps → directive entry."""

    async def test_the_18_13_turn_reaches_the_directive_typed(self) -> None:
        async def _tool(**_: Any) -> UnifiedToolOutput:
            return _category_failure()

        tool = SimpleNamespace(coroutine=_tool, args_schema=None, name="get_emails_tool")
        registry = SimpleNamespace(get_tool=lambda _name: tool)
        with (
            patch.object(pe.ToolRegistry, "get_instance", return_value=registry),
            patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: a),
        ):
            executed = await pe._execute_tool(
                tool_name="get_emails_tool", args={}, config={"configurable": {}}, store=None
            )

        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            tool_name="get_emails_tool",
            agent_name="emails_agent",
            parameters={},
        )
        with (
            patch.object(pe, "_get_tool_manifest_for_step", return_value=(None, None)),
            patch.object(pe, "_execute_tool", new=AsyncMock(return_value=executed)),
        ):
            step_result = await pe._execute_tool_step(
                step=step,
                completed_steps={},
                config={"configurable": {}},
                wave_id=0,
                store=None,
            )

        completed: dict[str, Any] = {}
        pe._merge_single_step_result(
            completed, step_result, accumulated_registry={}, current_turn_touched_ids=set()
        )

        failures = extract_failures_from_steps(completed, {"step_1": "get_emails_tool"})
        assert [entry["error_code"] for entry in failures] == [_CODE]
        assert failures[0]["tool"] == "get_emails_tool"


class TestTheReactLoopCarriesTheCode:
    """The ReAct body is the tool's PROSE: the code travels beside it."""

    @staticmethod
    def _message(raw: object) -> ToolMessage:
        call = {"name": "fake_mail_tool", "args": {}, "id": "call_1", "type": "tool_call"}
        wrapper = SimpleNamespace(
            _accumulated_registry={},
            _process_result=lambda result, budget_tokens=None: str(
                getattr(result, "message", result)
            ),
        )
        ports = SimpleNamespace(result_budget=1_000, draft=lambda _raw, _name: None)
        return _process(call, raw, wrapper, ports, {}).message

    def test_a_declared_failure_carries_its_code(self) -> None:
        message = self._message(_category_failure())

        assert message.status == "error"
        assert message.response_metadata[FIELD_ERROR_CODE] == _CODE

    def test_a_success_carries_no_code(self) -> None:
        message = self._message(UnifiedToolOutput.data_success(message="3 emails"))

        assert FIELD_ERROR_CODE not in message.response_metadata

    def test_a_failure_without_a_code_carries_none(self) -> None:
        message = self._message({"success": False, "error": "boom"})

        assert message.status == "error"
        assert FIELD_ERROR_CODE not in message.response_metadata

    def test_the_code_survives_the_checkpoint_and_reaches_the_directive(self) -> None:
        serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
        restored = serde.loads_typed(serde.dumps_typed([self._message(_category_failure())]))

        failures = extract_failures_from_tool_messages(restored)
        assert [entry["error_code"] for entry in failures] == [_CODE]
        assert failures[0]["tool"] == "fake_mail_tool"


class TestTheDirectiveGivesTheCodeItsMeaning:
    """A typed code the directive never explains is read as « anything else »."""

    @staticmethod
    def _sections() -> tuple[str, str]:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        text = str(load_prompt("runtime_failures_directive"))
        meanings, _, rules = text.partition("ABSOLUTE RULES:")
        return meanings.partition("What each code means:")[2], rules

    def test_the_code_has_a_meaning(self) -> None:
        meanings, _ = self._sections()
        assert any(line.startswith(f"- {_CODE}") for line in meanings.splitlines())

    def test_the_rule_against_configuration_diagnoses_names_its_one_exception(self) -> None:
        """Rule 2 forbids « not connected » — except where an entry carries this code."""
        _, rules = self._sections()
        rule_2 = next(line for line in rules.splitlines() if line.startswith("2."))
        assert _CODE in rule_2
