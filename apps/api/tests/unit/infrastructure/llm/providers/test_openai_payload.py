"""What LIA does to an OpenAI Responses payload before it leaves (ADR-306).

Every payload here is built by the real client (``create_responses_llm``, then
``_get_request_payload``), so the shaping is checked on the wire format
langchain-openai actually produces, never on a hand-written imitation of it.
No network.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.infrastructure.llm.providers.openai_payload import supports_cache_breakpoints
from src.infrastructure.llm.providers.responses_adapter import create_responses_llm
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

#: Measured on the Responses API on 2026-09-23 with LIA's real ``response``
#: prompt: each accepts a breakpoint on the static prefix, and the next call
#: sharing that prefix reads ~2,832 tokens at 0.1x where it used to rewrite
#: ~2,873 at 1.25x.
ACCEPTS_A_BREAKPOINT = (
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)

#: Measured the same day: each answers 400 « prompt_cache_breakpoint is not
#: supported on this model », so one such field refuses the whole call.
REFUSES_A_BREAKPOINT = (
    "gpt-5.5",
    "gpt-5.4-mini",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "o4-mini",
    "o3",
    "gpt-4.1-mini",
)

STATIC = "You are LIA. A static rule every call repeats. " * 40
DYNAMIC = (
    f"{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---\n"
    "<TemporalContext>2026-09-23 19:00</TemporalContext>\n"
)
PROMPT = f"{STATIC}\n\n{DYNAMIC}"


def _payload(model: str, messages: list[BaseMessage]) -> dict[str, Any]:
    return create_responses_llm(model, api_key="sk-test")._get_request_payload(messages)


def _payload_with_tools(model: str, messages: list[BaseMessage]) -> dict[str, Any]:
    llm = create_responses_llm(model, api_key="sk-test")

    def lookup(query: str) -> str:
        """Look something up."""
        return query

    bound = llm.bind_tools([lookup])
    return llm._get_request_payload(messages, **bound.kwargs)  # type: ignore[attr-defined]


def _system_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in payload["input"] if item.get("role") == "system"]


def _texts(item: dict[str, Any]) -> list[str]:
    content = item["content"]
    return [content] if isinstance(content, str) else [block["text"] for block in content]


def _breakpoints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Every content block, of every input item, that carries a breakpoint."""
    return [
        block
        for item in payload["input"]
        if isinstance(item.get("content"), list)
        for block in item["content"]
        if isinstance(block, dict) and "prompt_cache_breakpoint" in block
    ]


class TestTheStaticPrefixIsMarked:
    def test_the_static_part_ends_on_the_one_breakpoint(self) -> None:
        payload = _payload("gpt-6-luna", [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        [system] = _system_items(payload)
        static, dynamic = system["content"]
        assert static["text"] == f"{STATIC}\n\n"
        assert static["prompt_cache_breakpoint"] == {"mode": "explicit"}
        assert dynamic["text"].startswith(DYNAMIC_CONTEXT_MARKER)
        assert _breakpoints(payload) == [static]

    def test_the_model_reads_exactly_the_text_it_read_before(self) -> None:
        payload = _payload("gpt-6-luna", [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        [system] = _system_items(payload)
        assert "".join(_texts(system)) == PROMPT

    def test_a_marker_opening_a_system_message_marks_the_one_before(self) -> None:
        payload = _payload(
            "gpt-5.6-terra",
            [SystemMessage(content=STATIC), SystemMessage(content=DYNAMIC), HumanMessage("Hi")],
        )

        first, second = _system_items(payload)
        assert first["content"][-1]["prompt_cache_breakpoint"] == {"mode": "explicit"}
        assert _texts(first) == [STATIC]
        assert second["content"] == DYNAMIC

    def test_a_prompt_without_the_marker_is_left_alone(self) -> None:
        """Nothing says where the per-request part starts: a breakpoint at the
        end would pay the write surcharge on content no later call repeats."""
        payload = _payload("gpt-6-luna", [SystemMessage(content=STATIC), HumanMessage("Hi")])

        assert _breakpoints(payload) == []
        assert _system_items(payload)[0]["content"] == STATIC

    def test_a_request_a_tool_loop_can_continue_stays_implicit(self) -> None:
        """Explicit mode looks up explicit breakpoints ONLY (OpenAI's caching
        guide): a tool loop, which reads its previous iteration through the
        implicit breakpoint and the earlier message endings, would lose it."""
        payload = _payload_with_tools(
            "gpt-6-luna", [SystemMessage(content=PROMPT), HumanMessage("Hi")]
        )

        assert payload["tools"]
        assert "prompt_cache_options" not in payload

    def test_a_request_no_loop_can_continue_writes_only_its_breakpoints(self) -> None:
        """With no tool bound, no later call extends this prompt: the implicit
        breakpoint would write the turn's data at 1.25x for nobody to read —
        measured 2026-09-23, every single-call node on gpt-6-luna billed its
        whole unread prompt at exactly 1.25x (ADR-309)."""
        payload = _payload("gpt-6-luna", [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        assert payload["prompt_cache_options"] == {"mode": "explicit"}
        assert len(_breakpoints(payload)) == 1


class TestOnlyTheGenerationThatAcceptsIt:
    @pytest.mark.parametrize("model", ACCEPTS_A_BREAKPOINT)
    def test_each_measured_model_gets_one(self, model: str) -> None:
        payload = _payload(model, [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        assert len(_breakpoints(payload)) == 1

    @pytest.mark.parametrize("model", REFUSES_A_BREAKPOINT)
    def test_an_earlier_model_is_sent_none(self, model: str) -> None:
        payload = _payload(model, [SystemMessage(content=PROMPT), HumanMessage("Hi")])

        assert "prompt_cache_breakpoint" not in json.dumps(payload)
        assert "prompt_cache_options" not in payload

    def test_the_catalogue_offers_one_to_exactly_the_measured_models(self) -> None:
        """Wider, and every call of a model that refuses the field fails; narrower,
        and a model that accepts it rewrites its whole prompt at 1.25x."""
        offered = {
            row["model_name"]
            for row in _catalogue_rows()
            if row["provider"] == "openai" and supports_cache_breakpoints(row["model_name"])
        }

        assert offered == set(ACCEPTS_A_BREAKPOINT)

    def test_a_dated_snapshot_belongs_to_its_generation(self) -> None:
        assert supports_cache_breakpoints("gpt-6-luna-2026-08-15")
