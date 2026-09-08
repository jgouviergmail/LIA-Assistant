"""A truncated structured output is a refusal, never a rescue (ADR-275).

``json_recovery`` closes an open JSON structure mechanically, so a payload cut
at the provider's output budget used to validate as a SHORTER document —
rendered, stored and announced complete. These tests pin the two halves of the
fix: the predicate reads the provider's own verdict (five shapes, each read in
the installed adapter), and it runs BEFORE any rescue can shorten the answer.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    StructuredOutputTruncatedError,
    _get_json_mode_fallback,
    _get_native_structured_output,
    _structured_via_auto_tool,
    get_structured_output_with_retry,
)

pytestmark = [pytest.mark.unit]


class _Report(BaseModel):
    """A schema whose cut payload closes into a valid, shorter document."""

    title: str
    items: list[str]


class TestThePredicateReadsTheProvidersVerdict:
    """Five adapters spell « output budget exhausted » five ways."""

    @pytest.mark.parametrize(
        ("shape", "metadata"),
        [
            ("openai_chat", {"finish_reason": "length"}),
            ("google", {"finish_reason": "MAX_TOKENS"}),
            ("anthropic", {"stop_reason": "max_tokens"}),
            ("ollama", {"done_reason": "length"}),
            (
                "openai_responses",
                {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            ),
        ],
    )
    def test_every_provider_shape_is_read(self, shape: str, metadata: dict[str, Any]) -> None:
        assert is_output_truncated(AIMessage(content="{", response_metadata=metadata)), shape

    @pytest.mark.parametrize(
        "metadata",
        [
            {"finish_reason": "stop"},
            {"finish_reason": "tool_calls"},
            {"finish_reason": "content_filter"},
            {"stop_reason": "end_turn"},
            {"stop_reason": "tool_use"},
            {"done_reason": "stop"},
            {"status": "completed"},
            {"status": "incomplete", "incomplete_details": {"reason": "content_filter"}},
            {"status": "incomplete"},
            {},
        ],
    )
    def test_any_other_stop_is_not_a_truncation(self, metadata: dict[str, Any]) -> None:
        assert not is_output_truncated(AIMessage(content="{}", response_metadata=metadata))

    def test_anything_without_usable_metadata_is_not_a_truncation(self) -> None:
        """Doubt never invents a refusal: no message, no metadata, no verdict."""
        assert not is_output_truncated(None)
        assert not is_output_truncated("length")

        class _NoMetadata:
            pass

        assert not is_output_truncated(_NoMetadata())

        class _WrongType:
            response_metadata = "length"

        assert not is_output_truncated(_WrongType())


class _FakeStructured:
    """The ``with_structured_output`` wrapper the buffered path awaits."""

    def __init__(self, bundle: dict[str, Any]) -> None:
        self._bundle = bundle

    async def ainvoke(self, messages: Any, **_: Any) -> dict[str, Any]:
        return self._bundle


class _FakeLLM:
    """The attributes the native path reads, and the wrapper it builds."""

    model_name = "gpt-test"

    def __init__(self, bundle: dict[str, Any]) -> None:
        self._bundle = bundle

    def with_structured_output(self, schema: Any, **_: Any) -> _FakeStructured:
        return _FakeStructured(self._bundle)


class TestTheRefusalHappensBeforeAnyRescue:
    """The closable prefix WOULD validate — measured; it must never be returned."""

    @staticmethod
    def _cut_bundle() -> dict[str, Any]:
        raw = AIMessage(
            content='{"title": "Report", "items": ["a", "b", "c"',
            response_metadata={"finish_reason": "length"},
        )
        return {"raw": raw, "parsed": None, "parsing_error": ValueError("unterminated")}

    async def test_the_buffered_path_refuses_a_cut_payload(self) -> None:
        llm = _FakeLLM(self._cut_bundle())
        with pytest.raises(StructuredOutputTruncatedError) as excinfo:
            await _get_native_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[],
                schema=_Report,
                provider="openai",
            )
        assert excinfo.value.schema_name == "_Report"
        assert excinfo.value.provider == "openai"
        assert isinstance(excinfo.value, StructuredOutputError)

    async def test_an_answer_the_provider_parsed_whole_is_kept_despite_the_verdict(self) -> None:
        """No false positive: the object closed BEFORE the budget stopped the stream.

        A complete payload loses nothing, and refusing it would cost a valid
        document and a second bill. The verdict is only consulted once no
        complete answer exists.
        """
        raw = AIMessage(
            content='{"title": "Report", "items": ["a"]}',
            response_metadata={"finish_reason": "length"},
        )
        bundle = {"raw": raw, "parsed": _Report(title="Report", items=["a"]), "parsing_error": None}
        result = await _get_native_structured_output(
            llm=_FakeLLM(bundle),  # type: ignore[arg-type]
            messages=[],
            schema=_Report,
            provider="openai",
        )
        assert result.items == ["a"]

    async def test_the_same_payload_without_the_verdict_is_still_rescued(self) -> None:
        """The falsifier: only the provider's verdict turns a rescue into a refusal."""
        bundle = self._cut_bundle()
        bundle["raw"] = AIMessage(
            content='{"title": "Report", "items": ["a", "b", "c"',
            response_metadata={"finish_reason": "stop"},
        )
        rescued = await _get_native_structured_output(
            llm=_FakeLLM(bundle),  # type: ignore[arg-type]
            messages=[],
            schema=_Report,
            provider="openai",
        )
        assert rescued.items == ["a", "b", "c"]

    async def test_the_auto_tool_path_refuses_a_cut_answer(self) -> None:
        raw = AIMessage(content="", response_metadata={"stop_reason": "max_tokens"})

        class _Bound:
            async def ainvoke(self, payload: Any, **_: Any) -> AIMessage:
                return raw

        class _LLM:
            def bind_tools(self, tools: Any, tool_choice: str) -> _Bound:
                return _Bound()

        with pytest.raises(StructuredOutputTruncatedError):
            await _structured_via_auto_tool(
                llm=_LLM(),  # type: ignore[arg-type]
                messages=[],
                schema=_Report,
                reasoning_emit=None,
                provider="anthropic",
            )

    async def test_the_auto_tool_path_keeps_a_complete_tool_call(self) -> None:
        """A tool call that validates is complete, whatever the stop reason."""
        raw = AIMessage(
            content="",
            response_metadata={"stop_reason": "max_tokens"},
            tool_calls=[
                {
                    "name": "_Report",
                    "args": {"title": "Report", "items": ["a"]},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        )

        class _Bound:
            async def ainvoke(self, payload: Any, **_: Any) -> AIMessage:
                return raw

        class _LLM:
            def bind_tools(self, tools: Any, tool_choice: str) -> _Bound:
                return _Bound()

        result = await _structured_via_auto_tool(
            llm=_LLM(),  # type: ignore[arg-type]
            messages=[],
            schema=_Report,
            reasoning_emit=None,
            provider="anthropic",
        )
        assert result is not None and result.items == ["a"]

    async def test_the_auto_tool_path_still_returns_none_on_an_ordinary_miss(self) -> None:
        """A model that simply declined the tool is not a truncation."""
        raw = AIMessage(
            content="I would rather chat", response_metadata={"stop_reason": "end_turn"}
        )

        class _Bound:
            async def ainvoke(self, payload: Any, **_: Any) -> AIMessage:
                return raw

        class _LLM:
            def bind_tools(self, tools: Any, tool_choice: str) -> _Bound:
                return _Bound()

        assert (
            await _structured_via_auto_tool(
                llm=_LLM(),  # type: ignore[arg-type]
                messages=[],
                schema=_Report,
                reasoning_emit=None,
                provider="anthropic",
            )
            is None
        )


class TestTheJsonModeFallbackRefusesItToo:
    """Ollama and Perplexity parse text by hand — the same rescue, the same trap.

    This path is worse than the native one: ``json_recovery`` is called
    DELIBERATELY here, its own comment naming truncation as a case it handles.
    A cut answer therefore validated as a shorter object without even a
    parsing error to notice.
    """

    @staticmethod
    def _llm(metadata: dict[str, Any]) -> Any:
        cut = AIMessage(
            content='{"title": "Report", "items": ["a", "b", "c"',
            response_metadata=metadata,
        )

        class _LLM:
            model_name = "qwen3"

            def bind(self, **_: Any) -> _LLM:
                return self

            async def ainvoke(self, messages: Any, **_: Any) -> AIMessage:
                return cut

        return _LLM()

    async def test_a_cut_json_answer_is_refused(self) -> None:
        with pytest.raises(StructuredOutputTruncatedError):
            await _get_json_mode_fallback(
                llm=self._llm({"done_reason": "length"}),
                messages=[],
                schema=_Report,
                provider="ollama",
            )

    async def test_the_same_answer_that_merely_stopped_is_still_recovered(self) -> None:
        """The falsifier: recovery still works when the provider says it finished."""
        result = await _get_json_mode_fallback(
            llm=self._llm({"done_reason": "stop"}),
            messages=[],
            schema=_Report,
            provider="ollama",
        )
        assert result.items == ["a", "b", "c"]

    async def test_a_whole_json_answer_is_kept_despite_the_verdict(self) -> None:
        """No false positive here either: bare ``json.loads`` succeeded."""
        whole = AIMessage(
            content='{"title": "Report", "items": ["a"]}',
            response_metadata={"done_reason": "length"},
        )

        class _LLM:
            model_name = "qwen3"

            def bind(self, **_: Any) -> _LLM:
                return self

            async def ainvoke(self, messages: Any, **_: Any) -> AIMessage:
                return whole

        result = await _get_json_mode_fallback(
            llm=_LLM(),  # type: ignore[arg-type]
            messages=[],
            schema=_Report,
            provider="ollama",
        )
        assert result.items == ["a"]


class TestTheRetryWrapperNeverRetriesIt:
    """A truncation is deterministic: each retry is paid in full for nothing."""

    async def test_a_truncation_is_raised_on_the_first_attempt(self) -> None:
        door = AsyncMock(
            side_effect=StructuredOutputTruncatedError(
                "cut", provider="openai", schema_name="_Report"
            )
        )
        with patch("src.infrastructure.llm.structured_output.get_structured_output", door):
            with pytest.raises(StructuredOutputTruncatedError):
                await get_structured_output_with_retry(
                    llm=object(),  # type: ignore[arg-type]
                    messages=[],
                    schema=_Report,
                    provider="openai",
                    max_retries=3,
                )
        assert door.await_count == 1

    async def test_an_ordinary_structured_failure_is_still_retried(self) -> None:
        door = AsyncMock(
            side_effect=StructuredOutputError("nope", provider="openai", schema_name="_Report")
        )
        with patch("src.infrastructure.llm.structured_output.get_structured_output", door):
            with pytest.raises(StructuredOutputError):
                await get_structured_output_with_retry(
                    llm=object(),  # type: ignore[arg-type]
                    messages=[],
                    schema=_Report,
                    provider="openai",
                    max_retries=3,
                )
        assert door.await_count == 3
