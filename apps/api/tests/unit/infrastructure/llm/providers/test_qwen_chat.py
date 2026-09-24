"""Qwen's explicit prompt cache, marked where the static prefix ends (ADR-309).

DashScope documents Qwen 3.5 and 3.6 (Plus and Flash) with NO implicit prompt
cache in any region, only an explicit one: ``cache_control`` on a content part,
written at 125 % and read at 10 % for five minutes. Measured 2026-09-23 on LIA's
workspace with qwen3.5-plus: two identical requests read nothing; marked, the
first wrote 11,940 tokens and the second read 11,940. The write comes back as
``prompt_tokens_details.cache_creation_input_tokens``, a field langchain does not
map — so a write billed at 1.25x reached the ledger at 1x.

Every payload here is built by the real client, never a hand-written imitation.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.infrastructure.llm.providers.qwen_chat import ChatQwenCached, uses_explicit_cache

pytestmark = pytest.mark.unit

STATIC = "You are LIA. A static rule every call repeats. " * 40
MARKER_LINE = f"{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---"
PROMPT = f"{STATIC}\n{MARKER_LINE}\n<TemporalContext>2026-09-23 19:00</TemporalContext>"
MARK = {"type": "ephemeral"}


def _payload(model: str, messages: list[Any]) -> dict[str, Any]:
    llm = ChatQwenCached(model=model, api_key="sk-test", base_url="https://example.invalid/v1")
    return llm._get_request_payload(messages)


def _marked_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        part
        for message in payload["messages"]
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if isinstance(part, dict) and "cache_control" in part
    ]


class TestWhichModels:
    @pytest.mark.parametrize(
        "model", ["qwen3.5-plus", "qwen3.6-plus", "qwen3.5-flash", "qwen3.6-flash"]
    )
    def test_a_model_with_only_an_explicit_cache_is_marked(self, model: str) -> None:
        assert uses_explicit_cache(model)

    @pytest.mark.parametrize("model", ["qwen3.7-plus", "qwen3.8-flash", "qwen-max", "qwen3-max"])
    def test_a_model_with_an_implicit_cache_keeps_it(self, model: str) -> None:
        """A marker switches a request to the explicit mode (125 % write, 10 % read),
        which only beats the implicit one (no write surcharge, 20 % read) from four
        reads per five minutes."""
        assert not uses_explicit_cache(model)
        payload = _payload(model, [SystemMessage(content=PROMPT), HumanMessage("Hi")])
        assert "cache_control" not in json.dumps(payload)

    def test_a_dated_snapshot_belongs_to_its_family(self) -> None:
        assert uses_explicit_cache("qwen3.5-plus-2026-02-15")


class TestTheStaticPrefix:
    def test_it_ends_on_the_markers_line_and_carries_the_one_marker(self) -> None:
        payload = _payload("qwen3.5-plus", [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        parts = _marked_parts(payload)
        assert len(parts) == 1
        assert parts[0]["cache_control"] == MARK
        assert parts[0]["text"].endswith(MARKER_LINE)

    def test_the_model_reads_the_same_text(self) -> None:
        payload = _payload("qwen3.5-plus", [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        system = payload["messages"][0]["content"]
        assert "".join(part["text"] for part in system).split() == PROMPT.split()

    def test_a_prompt_without_the_marker_is_left_alone(self) -> None:
        payload = _payload("qwen3.5-plus", [SystemMessage(content=STATIC), HumanMessage("Hi")])

        assert payload["messages"][0]["content"] == STATIC


class TestTheToolLoop:
    def test_the_last_tool_result_carries_a_rolling_marker(self) -> None:
        messages = [
            SystemMessage(content=PROMPT),
            HumanMessage("Weather?"),
            AIMessage(content="", tool_calls=[{"name": "w", "args": {}, "id": "c1"}]),
            ToolMessage(content="Sunny.", tool_call_id="c1"),
        ]

        payload = _payload("qwen3.5-plus", messages)

        last = payload["messages"][-1]
        assert last["role"] == "tool"
        assert last["content"][-1]["cache_control"] == MARK
        assert len(_marked_parts(payload)) == 2

    def test_a_single_call_carries_no_rolling_marker(self) -> None:
        payload = _payload("qwen3.5-plus", [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        assert payload["messages"][-1]["content"] == "Hi"


class TestTheWriteIsRead:
    _USAGE = {
        "prompt_tokens": 11958,
        "completion_tokens": 1,
        "total_tokens": 11959,
        "prompt_tokens_details": {
            "cached_tokens": 0,
            "cache_write_tokens": None,
            "cache_creation_input_tokens": 11940,
        },
    }

    def _llm(self) -> ChatQwenCached:
        return ChatQwenCached(
            model="qwen3.5-plus", api_key="sk-test", base_url="https://example.invalid/v1"
        )

    def test_a_plain_call_reports_the_write(self) -> None:
        response = {
            "id": "r1",
            "object": "chat.completion",
            "created": 0,
            "model": "qwen3.5-plus",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": self._USAGE,
        }

        result = self._llm()._create_chat_result(response)

        details = result.generations[0].message.usage_metadata["input_token_details"]  # type: ignore[attr-defined]
        assert details["cache_creation"] == 11940

    def test_a_streamed_call_reports_the_write(self) -> None:
        chunk = {"id": "r1", "choices": [], "usage": self._USAGE}

        generation = self._llm()._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)

        assert generation is not None
        details = generation.message.usage_metadata["input_token_details"]  # type: ignore[attr-defined]
        assert details["cache_creation"] == 11940


class TestTheAdapterBuildsIt:
    def test_a_qwen_slot_is_built_on_the_client_that_marks_the_cache(self) -> None:
        from unittest.mock import patch

        from src.infrastructure.llm.providers.adapter import ProviderAdapter

        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
            return_value="sk-test",
        ):
            llm = ProviderAdapter.create_llm(
                provider="qwen",
                model="qwen3.5-plus",
                temperature=0.3,
                max_tokens=1000,
                streaming=True,
                llm_type="response",
            )

        assert isinstance(llm, ChatQwenCached)
