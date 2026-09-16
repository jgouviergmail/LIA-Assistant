"""Token budgets for what an owner call carries and returns (lot 4).

Two things travel to a model under a budget: the context block the voice
agent receives, and the transcript the relay synthesis reads. Both are cut at
LINE boundaries — a cut line is unusable, an oversized one merely costs — and
the first line always passes whole, the ADR-286 rule applied to text rather
than to items. The count is tiktoken's, the encoding the chat's own budgets
use; the vendor's model is settings-driven and a few percent off is the
price of not depending on it.
"""

from __future__ import annotations

from typing import Final

from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

#: A widely available encoding; only the count matters here, never the model.
_COUNT_MODEL: Final = "gpt-4o"
_counter = OpenAITokenCounter()


def token_count(text: str) -> int:
    """How many tokens a text costs.

    Args:
        text: Any text.

    Returns:
        The tiktoken count (a characters-based estimate when tiktoken is out).
    """
    return _counter.count(text, _COUNT_MODEL)


def fit_lines(lines: list[str], *, budget_tokens: int) -> tuple[str, bool]:
    """Keep whole lines, in order, until the budget is spent.

    Args:
        lines: The candidate lines, most important first.
        budget_tokens: What the result may cost.

    Returns:
        The kept text and whether anything was left out. The first line is
        always kept whole, even over budget.
    """
    kept: list[str] = []
    spent = 0
    for index, line in enumerate(lines):
        cost = token_count(line) + 1  # the newline
        if index > 0 and spent + cost > budget_tokens:
            return "\n".join(kept), True
        kept.append(line.rstrip())
        spent += cost
    return "\n".join(kept), False


__all__ = ["fit_lines", "token_count"]
