"""Measure what counting a compiled agent's history costs before each model call (lot 26).

A MEASUREMENT, never a gate, and free: no model is called. ``MessageHistoryMiddleware``
(the browser and query agents, ``graphs/base_agent_builder.py``) runs before EVERY model
call of those agents: it keeps the last messages, counts their tokens with tiktoken —
every message, every call, nothing remembered from the previous call — and, when the
history is over its token budget, drops the oldest unit and counts the WHOLE history
again, unit after unit.

This times the real middleware on histories shaped like a browser agent's (a system
prompt, then tool rounds whose results are page snapshots), counts the tiktoken encode
calls and characters it makes, and sets beside it what a per-message memo would encode
(each message once over the agent's life). It decides whether a memo is worth code.

Run on the host or in the API container::

    python -m scripts.agents.measure_history_token_counting
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Any, Final

import tiktoken
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.domains.agents.middleware.message_history import MessageHistoryMiddleware

#: Page snapshot sizes (characters) and tool rounds the bench crosses.
SNAPSHOT_CHARS: Final = (4_000, 16_000, 40_000)
ROUNDS: Final = (5, 15, 30)
REPEATS: Final = 5
_WORDS = "the quick brown fox jumps over the lazy dog while the page lists links forms buttons "


def history(rounds: int, snapshot_chars: int) -> list[BaseMessage]:
    """A browser agent's history: its instructions, the ask, then tool rounds."""
    snapshot = (_WORDS * (snapshot_chars // len(_WORDS) + 1))[:snapshot_chars]
    messages: list[BaseMessage] = [
        SystemMessage(content=_WORDS * 150),
        HumanMessage(content="Find the opening hours on the museum's website."),
    ]
    for index in range(rounds):
        call_id = f"call-{index}"
        messages.append(
            AIMessage(
                content="",
                tool_calls=[{"id": call_id, "name": "browser_snapshot", "args": {"step": index}}],
            )
        )
        messages.append(ToolMessage(content=f"{index} {snapshot}", tool_call_id=call_id))
    return messages


@dataclass
class _Counter:
    calls: int = 0
    chars: int = 0


def _counting_encode(counter: _Counter) -> Any:
    original = tiktoken.Encoding.encode

    def encode(self: tiktoken.Encoding, text: str, *args: Any, **kwargs: Any) -> list[int]:
        counter.calls += 1
        counter.chars += len(text)
        return original(self, text, *args, **kwargs)

    return original, encode


def measure_once(messages: list[BaseMessage], max_tokens: int | None) -> dict[str, float]:
    """One ``before_model`` call on the real middleware: its wait and its encodes."""
    middleware = MessageHistoryMiddleware(max_tokens=max_tokens)
    counter = _Counter()
    original, encode = _counting_encode(counter)
    tiktoken.Encoding.encode = encode  # type: ignore[method-assign]
    try:
        started = time.perf_counter()
        middleware.before_model({"messages": messages}, None)
        elapsed = time.perf_counter() - started
    finally:
        tiktoken.Encoding.encode = original  # type: ignore[method-assign]
    return {"ms": elapsed * 1000, "encodes": counter.calls, "chars": counter.chars}


def memo_chars(messages: list[BaseMessage]) -> int:
    """What a per-message memo encodes for a NEW model call: the newest round only."""
    return sum(len(str(message.content)) for message in messages[-2:])


def run(max_tokens: int | None) -> list[dict[str, Any]]:
    """Every size and round count, ``REPEATS`` times each (the median is kept)."""
    rows: list[dict[str, Any]] = []
    for snapshot_chars in SNAPSHOT_CHARS:
        for rounds in ROUNDS:
            messages = history(rounds, snapshot_chars)
            samples = [measure_once(messages, max_tokens) for _ in range(REPEATS)]
            rows.append(
                {
                    "snapshot_chars": snapshot_chars,
                    "rounds": rounds,
                    "ms_median": round(statistics.median(s["ms"] for s in samples), 2),
                    "encodes": int(samples[0]["encodes"]),
                    "chars_encoded": int(samples[0]["chars"]),
                    "chars_with_memo": memo_chars(messages),
                }
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="the middleware's token budget (default: the setting; small forces the trim loop)",
    )
    args = parser.parse_args(argv)
    json.dump(run(args.max_tokens), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
