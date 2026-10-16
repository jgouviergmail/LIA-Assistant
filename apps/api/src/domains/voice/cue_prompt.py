"""The prompt block that tells a spoken-comment writer which cues its engine performs (ADR-345).

A prompt states what the code enforces, and nothing else (ADR-284): the block
is rendered only when the engine that will speak performs at least one cue and
the budget is above zero, it lists exactly the cues the engine performs — in
LIA's canonical words, spelled the engine's way later by
:class:`~src.domains.voice.expressive_cues.AuthoredCues` — its example shows a
cue the engine performs, and the budget it publishes is the one the renderer
enforces, from ONE setting.
"""

from __future__ import annotations

from collections.abc import Set
from typing import Final

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.voice.expressive_cues import DELIVERY_CUES, EVENT_CUES, Cue, CueDialect

#: The versioned lines file the block is read from.
CUE_PROMPT_LINES: Final[str] = "voice_expressive_cues_lines"

#: The cue each example sentence is written for, shown when the engine performs it.
_EXAMPLE_DELIVERY: Final[Cue] = Cue.WARM
_EXAMPLE_EVENT: Final[Cue] = Cue.SIGHS


def _listed(cues: Set[Cue]) -> str:
    """The cues in the canonical syntax, in the vocabulary's own order."""
    return ", ".join(f"[{cue.value}]" for cue in Cue if cue in cues)


def _example_cue(performed: Set[Cue], written_for: Cue) -> Cue:
    """The cue an example shows: the one it was written for, else the first performed."""
    if written_for in performed:
        return written_for
    return next(cue for cue in Cue if cue in performed)


def expressive_cues_block(dialect: CueDialect, budget: int) -> str:
    """The block for a writer whose words ``dialect``'s engine will speak.

    Args:
        dialect: The dialect of the engine that will speak the comment.
        budget: The most cues the comment may carry (the renderer's own bound).

    Returns:
        The block, or an empty string when the engine performs nothing or the
        budget is spent before it starts.
    """
    performed = dialect.performs()
    if budget <= 0 or not performed:
        return ""
    delivery = performed & DELIVERY_CUES
    events = performed & EVENT_CUES
    lines = dict(parse_prompt_sections(read_prompt_file(CUE_PROMPT_LINES), 2))
    parts = [lines["open"], lines["intro"]]
    if delivery:
        parts.append(lines["delivery"].format(cues=_listed(delivery)))
    if events:
        parts.append(lines["events"].format(cues=_listed(events)))
    parts.append(lines["rules"].format(max_cues=budget))
    parts.append(lines["never"])
    if delivery:
        cue = _example_cue(delivery, _EXAMPLE_DELIVERY)
        parts.append(lines["example.delivery"].format(cue=f"[{cue.value}]"))
    else:
        cue = _example_cue(events, _EXAMPLE_EVENT)
        parts.append(lines["example.events"].format(cue=f"[{cue.value}]"))
    parts.append(lines["close"])
    return "\n".join(parts)


__all__ = ["CUE_PROMPT_LINES", "expressive_cues_block"]
