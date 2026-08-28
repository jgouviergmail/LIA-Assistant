"""Failure-context extraction — pure readers over what the run already carries.

No new state key: the pipeline's ``completed_steps`` and ReAct's ToolMessages
already hold every failure. These extractors turn them into TYPED entries
(source, tool, error_code, truncated message head) — never raw payloads, never
log text — for the response synthesis honesty block.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.domains.diagnostics.failure_context import (
    extract_failures_from_steps,
    extract_failures_from_tool_messages,
)

#: Mirrors the real directive's placeholders (the caller injects the file).
_TEMPLATE = "RUNTIME FAILURES THIS TURN:\n{failures_json}\n\n{degradations_block}"


@pytest.mark.unit
class TestPipelineExtraction:
    def test_error_steps_become_typed_failures(self) -> None:
        steps = {
            "step_1": {
                "status": "success",
                "agent": "contact_agent",
                "result": {"success": True},
            },
            "step_2": {
                "status": "error",
                "agent": "web_search_agent",
                "error": "brave down",
                "result": {
                    "success": False,
                    "error": {"code": "SERVICE_UNAVAILABLE", "message": "brave down " * 50},
                },
            },
        }
        failures = extract_failures_from_steps(steps)
        assert len(failures) == 1
        failure = failures[0]
        assert failure["source"] == "step_2"
        assert failure["agent"] == "web_search_agent"
        assert failure["error_code"] == "SERVICE_UNAVAILABLE"
        assert len(failure["message"]) <= 160  # head only, never a dump

    def test_success_only_steps_yield_nothing(self) -> None:
        steps = {"s": {"status": "success", "result": {"success": True}}}
        assert extract_failures_from_steps(steps) == []

    def test_none_and_malformed_steps_never_raise(self) -> None:
        assert extract_failures_from_steps(None) == []
        assert extract_failures_from_steps({"s": "garbage"}) == []
        assert extract_failures_from_steps({"s": {"status": "error"}}) != []

    def test_extraction_is_bounded(self) -> None:
        steps = {f"s{i}": {"status": "error", "error": "x", "result": {}} for i in range(50)}
        failures = extract_failures_from_steps(steps)
        assert len(failures) <= 10  # bounded so checkpoint/prompt cannot bloat


@pytest.mark.unit
class TestRuntimeFailuresDirective:
    async def test_healthy_turn_yields_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domains.diagnostics import failure_context as fc

        async def no_degradations() -> list:
            return []

        monkeypatch.setattr(fc, "get_active_degradations", no_degradations)
        block = await fc.build_runtime_failures_directive(
            completed_steps={}, messages=[], template=_TEMPLATE
        )
        assert block == ""

    async def test_failures_render_typed_directive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domains.diagnostics import failure_context as fc
        from src.domains.diagnostics.advisor import CapabilityDegradation

        async def one_degradation() -> list[CapabilityDegradation]:
            return [
                CapabilityDegradation(
                    capability="web_search",
                    status="degraded",
                    reason="circuit_open:brave_search",
                    alternative="perplexity",
                )
            ]

        monkeypatch.setattr(fc, "get_active_degradations", one_degradation)
        steps = {
            "step_2": {
                "status": "error",
                "agent": "web_search_agent",
                "error": "brave down",
                "result": {"success": False, "error": {"code": "SERVICE_UNAVAILABLE"}},
            }
        }
        block = await fc.build_runtime_failures_directive(
            completed_steps=steps, messages=[], template=_TEMPLATE
        )
        assert "SERVICE_UNAVAILABLE" in block
        assert "perplexity" in block
        assert "RUNTIME FAILURES" in block

    async def test_advisor_failure_never_breaks_the_directive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.diagnostics import failure_context as fc

        async def broken() -> list:
            raise ConnectionError("redis down")

        monkeypatch.setattr(fc, "get_active_degradations", broken)
        steps = {"s": {"status": "error", "error": "x", "result": {}}}
        block = await fc.build_runtime_failures_directive(
            completed_steps=steps, messages=[], template=_TEMPLATE
        )
        assert "UNKNOWN" in block  # failures still rendered without the advisor


@pytest.mark.unit
class TestReactExtraction:
    def test_failed_tool_messages_become_typed_failures(self) -> None:
        messages = [
            HumanMessage(content="check my mail"),
            AIMessage(content="ok"),
            ToolMessage(
                tool_call_id="c1",
                name="search_emails_tool",
                content=json.dumps(
                    {
                        "success": False,
                        "error": "token expired",
                        "error_code": "AUTHENTICATION_ERROR",
                    }
                ),
            ),
            ToolMessage(
                tool_call_id="c2",
                name="search_contacts_tool",
                content=json.dumps({"success": True, "message": "found 3"}),
            ),
        ]
        failures = extract_failures_from_tool_messages(messages)
        assert len(failures) == 1
        assert failures[0]["tool"] == "search_emails_tool"
        assert failures[0]["error_code"] == "AUTHENTICATION_ERROR"

    def test_non_json_tool_content_is_ignored(self) -> None:
        messages = [ToolMessage(tool_call_id="c", name="t", content="plain text")]
        assert extract_failures_from_tool_messages(messages) == []

    def test_empty_messages_yield_nothing(self) -> None:
        assert extract_failures_from_tool_messages([]) == []
