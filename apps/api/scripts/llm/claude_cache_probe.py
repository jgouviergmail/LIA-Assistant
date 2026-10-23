"""Measure Claude's prompt cache against the ADR-362 design (NETWORK, the instance key).

A MEASUREMENT, never a gate (ADR-155): CI holds no provider key, and a paid call
on a path someone must pass to merge is not a build verdict. Run it inside the
API container, which holds the instance key (never printed)::

    task llm:cache:probe -- --budget 1.0

What it settles, each on the vendor's real API (every prefix opens on a fresh
nonce, so no earlier entry can answer for a later request):

* H1 -- does a five-minute breakpoint read an entry written for the hour, and
  the reverse (is the lifetime part of the cache key)?
* H2 -- does a STREAMED response report the lifetime breakdown of its writes at
  its start, and only there?
* H3 -- is a request mixing the two lifetimes billed span by span (the hour up
  to the last one-hour breakpoint, five minutes after it)?
* H4 -- does the next frequent ReAct turn, built by LIA's own code, read the
  whole history back from the history-end breakpoint -- and nothing past the
  static prefix without it?
* H5 -- does a generation that keeps prior-turn thinking accept that thinking
  replayed in LIA's history shape (two assistant messages per ReAct turn), what
  does it cost in input tokens, and what does another model do with it?

The spend is computed by LIA's own pricing door from each response's usage; a
request is refused once the spend has reached the budget, so a run passes it by
one request at most, and the report carries the total.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

from anthropic import APIStatusError, AsyncAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.nodes.react_history import window_messages_for_react
from src.domains.agents.nodes.react_turn_layout import compose_turn_messages
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur, refresh_pricing_cache
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.providers.adapter import configured_api_key
from src.infrastructure.llm.providers.anthropic_hooks import install_claude_hooks

FIVE_MINUTES: dict[str, str] = {"type": "ephemeral"}
ONE_HOUR: dict[str, str] = {"type": "ephemeral", "ttl": "1h"}
TOOLS = [
    {
        "name": name,
        "description": f"Look up the person's {topic}.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }
    for name, topic in (("get_events_tool", "calendar"), ("get_emails_tool", "mailbox"))
]


class BudgetExceededError(RuntimeError):
    """The next request would pass the approved envelope."""


class Probe:
    """One client, one budget, and the observations of the run."""

    def __init__(self, client: AsyncAnthropic, budget_usd: float) -> None:
        self.client = client
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.requests = 0

    def check_budget(self) -> None:
        """Refuse the next request once the spend has reached the envelope."""
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceededError(f"spent {self.spent_usd:.4f} of {self.budget_usd}")

    async def send(self, **request: Any) -> dict[str, Any]:
        """One non-streamed request; its usage, its content types and its price."""
        self.check_budget()
        try:
            response = await self.client.messages.create(**request)
        except APIStatusError as exc:
            return {"status": exc.status_code, "error": str(exc.message)[:300]}
        self.requests += 1
        usage = _usage(response.usage)
        self.spent_usd += _price(request["model"], usage, response.usage.output_tokens)
        return {
            "status": 200,
            "usage": usage,
            "content": [block.type for block in response.content],
            "message": response,
        }


def _usage(usage: Any) -> dict[str, int]:
    breakdown = getattr(usage, "cache_creation", None)
    return {
        "input": usage.input_tokens or 0,
        "cache_read": usage.cache_read_input_tokens or 0,
        "cache_write": usage.cache_creation_input_tokens or 0,
        "write_5m": getattr(breakdown, "ephemeral_5m_input_tokens", 0) or 0,
        "write_1h": getattr(breakdown, "ephemeral_1h_input_tokens", 0) or 0,
    }


def _price(model: str, usage: dict[str, int], output_tokens: int) -> float:
    """What LIA's own pricing door says the request cost (USD)."""
    prompt = usage["input"] + usage["cache_write"]
    usd, _eur = get_cached_cost_usd_eur(
        model,
        prompt,
        output_tokens,
        usage["cache_read"],
        cache_write_tokens=usage["cache_write"],
        cache_write_extended_tokens=usage["write_1h"],
    )
    return usd


def _static(tag: str, lines: int = 260) -> str:
    """A static prefix of about 3,000 tokens that no earlier request can share."""
    body = "".join(f"Rule {index}: answer briefly and stay factual.\n" for index in range(lines))
    return f"probe {tag} {uuid.uuid4().hex}\n{body}"


def _strip(content: list[Any]) -> list[Any]:
    return [block for block in content if block.type not in ("thinking", "redacted_thinking")]


async def h1_lifetime_is_not_the_key(probe: Probe, model: str) -> dict[str, Any]:
    """Write for the hour then read with five minutes, and the reverse."""
    results: dict[str, Any] = {}
    for first, second, label in (
        (ONE_HOUR, FIVE_MINUTES, "1h_then_5m"),
        (FIVE_MINUTES, ONE_HOUR, "5m_then_1h"),
    ):
        static = _static(label)
        rounds = []
        for marker in (first, second):
            reply = await probe.send(
                model=model,
                max_tokens=0,
                system=[{"type": "text", "text": static, "cache_control": marker}],
                messages=[{"role": "user", "content": "ok"}],
            )
            rounds.append(reply.get("usage") or reply)
        results[label] = rounds
    return results


async def h2_stream_reports_the_breakdown_at_its_start(probe: Probe, model: str) -> dict[str, Any]:
    probe.check_budget()
    stream = await probe.client.messages.create(
        model=model,
        max_tokens=8,
        stream=True,
        system=[{"type": "text", "text": _static("stream"), "cache_control": ONE_HOUR}],
        messages=[{"role": "user", "content": "Reply with the word ok."}],
        cache_control=FIVE_MINUTES,
    )
    start: dict[str, Any] = {}
    end: dict[str, Any] = {}
    async for event in stream:
        if event.type == "message_start":
            start = event.message.usage.model_dump()
        elif event.type == "message_delta":
            end = event.usage.model_dump()
    probe.requests += 1
    probe.spent_usd += _price(model, _usage(_Obj(start)), int(end.get("output_tokens") or 0))
    return {
        "start_usage_keys": sorted(start),
        "start": start,
        "end_usage_keys": sorted(end),
        "end": end,
    }


class _Obj:
    """Attribute access over a usage dict (for the shared readers)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        value = self._data.get(name)
        return _Obj(value) if isinstance(value, dict) else value


async def h3_mixed_lifetimes_are_billed_by_span(probe: Probe, model: str) -> dict[str, Any]:
    reply = await probe.send(
        model=model,
        max_tokens=0,
        system=[
            {"type": "text", "text": _static("mixed-hour"), "cache_control": ONE_HOUR},
            {"type": "text", "text": _static("mixed-minutes", 140), "cache_control": FIVE_MINUTES},
        ],
        messages=[{"role": "user", "content": "ok"}],
    )
    return reply.get("usage") or reply


def _thread(turns: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(1, turns + 1):
        messages += [
            HumanMessage(content=f"Question {turn}: what is on my agenda for day {turn}?"),
            AIMessage(content=f"Day {turn}: " + "a meeting, then a call. " * 40),
        ]
    return messages


def _lia_turn(static: str, turn: int, *, extended: bool) -> dict[str, Any]:
    """The first ReAct call of a frequent turn, built by LIA's own code."""
    messages = [*_thread(turn - 1), HumanMessage(content=f"Question {turn}: and tomorrow?")]
    windowed = window_messages_for_react(messages, turn_id=turn, blocks=True)
    composed = compose_turn_messages(
        [
            f"{static}{DYNAMIC_CONTEXT_MARKER}\nToday is day {turn}.",
            f"<Memories>day {turn}</Memories>",
        ],
        windowed,
        context_after_question=True,
        provider="anthropic",
    )
    llm = ChatAnthropic(model="claude-probe", api_key="unused", max_tokens=64)
    install_claude_hooks(llm)
    from src.infrastructure.llm.prompt_cache_horizon import extended_prompt_cache_horizon

    with extended_prompt_cache_horizon(extended):
        payload = llm._get_request_payload(composed, tools=TOOLS)
    payload.pop("stream", None)
    return payload


def _without_history_end(payload: dict[str, Any]) -> dict[str, Any]:
    """The same request as LIA built it before ADR-362: no read point in the messages."""
    messages = [
        (
            {
                **message,
                "content": [
                    {key: value for key, value in block.items() if key != "cache_control"}
                    for block in message["content"]
                ],
            }
            if isinstance(message.get("content"), list)
            else message
        )
        for message in payload["messages"]
    ]
    return {**payload, "messages": messages}


async def h4_the_next_turn_reads_the_history(probe: Probe, model: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, shape, extended in (
        ("history_end_5m", lambda payload: payload, False),
        ("history_end_1h", lambda payload: payload, True),
        ("no_history_end", _without_history_end, False),
    ):
        static = _static(label, 200)
        rounds = []
        for turn in (4, 5):
            payload = shape(_lia_turn(static, turn, extended=extended))
            reply = await probe.send(**{**payload, "model": model, "max_tokens": 0})
            rounds.append(reply.get("usage") or reply)
        results[label] = rounds
    return results


async def h5_prior_thinking_replay(
    probe: Probe, preserving_model: str, binding_model: str
) -> dict[str, Any]:
    question = (
        "A train leaves at 9:40 and arrives at 13:05 after a 25-minute stop. "
        "How long was it moving? Answer in one sentence."
    )
    loop = await probe.send(
        model=preserving_model,
        max_tokens=1_500,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": question}],
    )
    response = await probe.send(
        model=preserving_model,
        max_tokens=1_500,
        thinking={"type": "adaptive"},
        system="You write the final answer the person reads.",
        messages=[{"role": "user", "content": question}],
    )
    if loop.get("status") != 200 or response.get("status") != 200:
        return {"loop": loop, "response": response}
    loop_content = list(loop["message"].content)
    response_content = list(response["message"].content)
    follow_up = {"role": "user", "content": "And if the stop had lasted 40 minutes?"}

    def history(*assistant_turns: list[Any]) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": question},
            *({"role": "assistant", "content": content} for content in assistant_turns),
            follow_up,
        ]

    cases = {
        "kept_one_assistant": history(loop_content),
        "stripped_one_assistant": history(_strip(loop_content)),
        "kept_both_assistants": history(loop_content, response_content),
        "kept_first_stripped_second": history(loop_content, _strip(response_content)),
        "stripped_both_assistants": history(_strip(loop_content), _strip(response_content)),
    }
    results: dict[str, Any] = {
        "loop_blocks": loop["content"],
        "response_blocks": response["content"],
    }
    for label, messages in cases.items():
        reply = await probe.send(
            model=preserving_model, max_tokens=0, thinking={"type": "adaptive"}, messages=messages
        )
        results[label] = reply.get("usage") or reply
    other = await probe.send(
        model=binding_model, max_tokens=0, messages=cases["kept_one_assistant"]
    )
    results["kept_one_assistant_to_another_model"] = other.get("usage") or other
    return results


async def _client() -> AsyncAnthropic:
    import_all_models()
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
    await refresh_pricing_cache()
    key = configured_api_key("anthropic")
    if not key:
        raise SystemExit("No Anthropic key configured on this instance.")
    return AsyncAnthropic(api_key=key)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget", type=float, default=1.0, help="USD envelope (default 1.0)")
    parser.add_argument("--binding-model", default="claude-haiku-5-5")
    parser.add_argument("--preserving-model", default="claude-sonnet-5")
    args = parser.parse_args()

    probe = Probe(await _client(), args.budget)
    report: dict[str, Any] = {"models": [args.binding_model, args.preserving_model]}
    steps = [
        ("h1", lambda model: h1_lifetime_is_not_the_key(probe, model)),
        ("h2", lambda model: h2_stream_reports_the_breakdown_at_its_start(probe, model)),
        ("h3", lambda model: h3_mixed_lifetimes_are_billed_by_span(probe, model)),
        ("h4", lambda model: h4_the_next_turn_reads_the_history(probe, model)),
    ]
    try:
        for model in (args.binding_model, args.preserving_model):
            for name, step in steps:
                report[f"{name}:{model}"] = await step(model)
        report["h5"] = await h5_prior_thinking_replay(
            probe, args.preserving_model, args.binding_model
        )
    except BudgetExceededError as exc:
        report["stopped"] = str(exc)
    report["requests"] = probe.requests
    report["spent_usd"] = round(probe.spent_usd, 6)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
