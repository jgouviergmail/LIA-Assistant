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
        """The shape ``parallel_executor`` really writes (ADR-303).

        This fixture used to carry ``status``, ``agent`` and a nested
        ``result.error.code`` — three keys no writer in the repository ever
        produced. The suite was green over a reader that returned ``[]`` on
        every real turn.
        """
        steps = {
            "step_1": {"success": True},
            "step_2": {
                "success": False,
                "error": "brave down " * 50,
                "error_code": "SERVICE_UNAVAILABLE",
            },
        }
        failures = extract_failures_from_steps(steps, {"step_2": "brave_search_tool"})
        assert len(failures) == 1
        failure = failures[0]
        assert failure["tool"] == "brave_search_tool"
        assert failure["error_code"] == "SERVICE_UNAVAILABLE"
        assert len(failure["message"]) <= 160  # head only, never a dump

    def test_success_only_steps_yield_nothing(self) -> None:
        assert extract_failures_from_steps({"s": {"success": True}}) == []

    def test_a_for_each_aggregate_is_skipped_its_items_carry_the_failures(self) -> None:
        """Listing the aggregate AND its items would count one failure twice."""
        steps = {
            "step_2_item_0": {"success": False, "error": "a", "error_code": "TIMEOUT"},
            "step_2_item_1": {"success": True},
            "step_2": {
                "success": True,
                "error": "1/2 items failed: a",
                "_for_each_aggregate": True,
            },
        }
        failures = extract_failures_from_steps(steps, {"step_2": "create_reminder_tool"})
        # One entry — the ITEM's — and the capability resolved through its
        # parent step id, which is where the plan names the tool.
        assert len(failures) == 1
        assert failures[0]["message"] == "a"
        assert failures[0]["tool"] == "create_reminder_tool"

    def test_a_missing_code_reads_unknown(self) -> None:
        failures = extract_failures_from_steps({"s": {"success": False, "error": "x"}})
        assert failures[0]["error_code"] == "UNKNOWN"

    def test_the_count_is_exact_beyond_the_shown_bound(self) -> None:
        """A capped list never hides how many there really were (ADR-185)."""
        from src.domains.diagnostics.failure_context import MAX_FAILURES, count_failed_steps

        steps = {f"s{i}": {"success": False, "error": "x"} for i in range(MAX_FAILURES + 5)}
        assert len(extract_failures_from_steps(steps)) == MAX_FAILURES
        assert count_failed_steps(steps) == MAX_FAILURES + 5

    def test_none_and_malformed_steps_never_raise(self) -> None:
        assert extract_failures_from_steps(None) == []
        assert extract_failures_from_steps({"s": "garbage"}) == []
        assert extract_failures_from_steps({"s": {"success": False}}) != []

    def test_extraction_is_bounded(self) -> None:
        steps = {f"s{i}": {"success": False, "error": "x"} for i in range(50)}
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
                "success": False,
                "error": "brave down",
                "error_code": "SERVICE_UNAVAILABLE",
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
        steps = {"s": {"success": False, "error": "x"}}
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


class TestAListShapedToolMessage:
    """``content`` is not always a string, and a Python repr is not a message.

    LangChain serializes typed blocks inside a LIST-shaped ``content`` — the
    shape CLAUDE.md already names for ``function_call`` under ``responses/v1``
    and ``tool_use`` on Anthropic. Read with ``str()``, such a body reached the
    model as ``"[{'type': 'text', 'text': '…'}]"``: the repr of our own data
    structure, spent as tokens and read as noise (ADR-303 cold review).
    """

    @staticmethod
    def _extract(content: object) -> list[dict[str, str]]:
        from langchain_core.messages import ToolMessage

        from src.domains.diagnostics.failure_context import extract_failures_from_tool_messages

        message = ToolMessage(
            content=content,  # type: ignore[arg-type]
            tool_call_id="c1",
            name="get_events_tool",
            status="error",
        )
        return extract_failures_from_tool_messages([message])

    def test_the_text_of_typed_blocks_is_read(self) -> None:
        failures = self._extract(
            [
                {"type": "text", "text": "Calendar unavailable:"},
                {"type": "text", "text": "the token expired."},
            ]
        )
        assert failures[0]["message"] == "Calendar unavailable: the token expired."

    def test_a_block_carrying_no_text_says_nothing_rather_than_a_repr(self) -> None:
        failures = self._extract([{"type": "image", "source": {"data": "AAAA"}}])
        assert failures[0]["message"] == ""

    def test_a_plain_string_is_unchanged(self) -> None:
        failures = self._extract("Calendar unavailable.")
        assert failures[0]["message"] == "Calendar unavailable."

    def test_a_list_of_plain_strings_is_read(self) -> None:
        """``content`` accepts ``list[str]`` too — filtering on dicts lost it."""
        failures = self._extract(["Calendar unavailable:", "the token expired."])
        assert failures[0]["message"] == "Calendar unavailable: the token expired."

    def test_a_mixed_list_reads_every_readable_part(self) -> None:
        failures = self._extract(
            ["Calendar unavailable:", {"type": "text", "text": "the token expired."}]
        )
        assert failures[0]["message"] == "Calendar unavailable: the token expired."


class TestAnEntryCarriesOnlyWhatTheModelUses:
    """What reaches the model is what the prompt names — nothing else (ADR-284).

    Two findings of the ADR-303 cold review. The directive ordered « Name the
    capability from "tool" » while the field is EMPTY whenever the turn has no
    execution plan to resolve it from: a prompt asking for what the code cannot
    supply is the exact trap ADR-184 names, and a model told to name something
    it was not given invents one. And ``source`` (``step_1``, ``react_tool``)
    was published on every entry while the prompt never mentions it and no
    reader ever used it: tokens billed on every failed turn for noise.
    """

    @staticmethod
    def _entry(tool_names: dict[str, str] | None) -> dict[str, str]:
        from src.domains.diagnostics.failure_context import extract_failures_from_steps

        return extract_failures_from_steps(
            {"step_1": {"success": False, "error": "boom", "error_code": "TIMEOUT"}},
            tool_names,
        )[0]

    def test_an_unnamed_capability_omits_the_field_rather_than_publishing_emptiness(
        self,
    ) -> None:
        assert "tool" not in self._entry(None)

    def test_a_named_capability_carries_it(self) -> None:
        assert self._entry({"step_1": "get_events_tool"})["tool"] == "get_events_tool"

    def test_no_entry_carries_a_key_the_prompt_never_names(self) -> None:
        assert "source" not in self._entry({"step_1": "get_events_tool"})

    def test_a_react_entry_follows_the_same_rule(self) -> None:
        from langchain_core.messages import ToolMessage

        from src.domains.diagnostics.failure_context import extract_failures_from_tool_messages

        named = ToolMessage(content="x", tool_call_id="c", name="get_emails_tool", status="error")
        unnamed = ToolMessage(content="x", tool_call_id="c", status="error")
        assert extract_failures_from_tool_messages([named])[0]["tool"] == "get_emails_tool"
        assert "tool" not in extract_failures_from_tool_messages([unnamed])[0]
        assert "source" not in extract_failures_from_tool_messages([named])[0]
