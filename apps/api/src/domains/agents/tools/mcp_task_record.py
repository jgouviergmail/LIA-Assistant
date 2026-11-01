"""What an iterative MCP task tells the model, written by the code (spec 2026-10-29 D5, D6).

Two texts, both from ``prompts/v1/mcp_sub_loop_lines.txt``:

- the line the SUB-AGENT reads for a call that owes the person's approval — the
  call was not performed, the person is asked after the task, and the answer
  lists it as awaiting (measured best of three wordings, 2026-10-29);
- the RECORD appended to the task's answer: which calls were performed and which
  await the person's approval. A narrative is the model's word, and measured
  11 times in 50 it said « done » about a call that was not; the record is the
  code's, and introduced as authoritative over the narrative.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from src.core.prompt_store import parse_prompt_sections, read_prompt_file


def _lines() -> dict[str, str]:
    """The scaffolds, read from the store (the store caches the file)."""
    return dict(parse_prompt_sections(read_prompt_file("mcp_sub_loop_lines"), 2))


def pending_approval_line() -> str:
    """What the sub-agent reads for a call queued for the person's approval."""
    return _lines()["pending_approval"]


def with_record(message: str, performed: Sequence[str], awaiting: Sequence[str]) -> str:
    """The task's answer followed by the record of its calls.

    Args:
        message: The sub-agent's own answer (or the failure the code wrote).
        performed: The readable name of every call that succeeded, in call order.
        awaiting: The readable name of every call queued for approval, in call order.

    Returns:
        The message alone when the task called nothing; otherwise the message,
        a blank line and the record — each line present only when it has content.
    """
    if not performed and not awaiting:
        return message
    lines = _lines()
    record = [lines["record_heading"]]
    if performed:
        record.append(lines["record_performed"].format(actions=_counted(performed, lines)))
    if awaiting:
        record.append(lines["record_awaiting"].format(actions=_counted(awaiting, lines)))
    return "\n\n".join(part for part in (message, "\n".join(record)) if part)


def settled_line(performed: Sequence[str]) -> str:
    """What a task's step reads once the person approved its queued acts (spec D7).

    Args:
        performed: The registered name of each act that ran after the answers.

    Returns:
        One line for the step's result.
    """
    lines = _lines()
    return lines["record_settled"].format(actions=_counted(performed, lines))


def _counted(names: Sequence[str], lines: dict[str, str]) -> str:
    """Each name once, in first-call order, with its count when it repeats."""
    return ", ".join(
        name if count == 1 else lines["record_repeated"].format(action=name, count=count)
        for name, count in Counter(names).items()
    )
