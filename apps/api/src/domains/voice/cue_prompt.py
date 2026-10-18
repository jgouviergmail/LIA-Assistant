"""The prompt block that tells a spoken-comment writer which cues its engine performs (ADR-345).

A prompt states what the code enforces, and nothing else (ADR-284): the block
is rendered only when the engine that will speak performs at least one cue —
inline or as a style — and the budget is above zero; it lists exactly the cues
the engine performs, in LIA's canonical words (spelled the engine's way later
by :class:`~src.domains.voice.expressive_cues.AuthoredCues`), each with the
meaning that says when it fits; its rules speak only of the kinds it lists (a
delivery to open with, a sound, a cue for the night); its example is one of
them; and the budget it publishes is the one the renderer enforces, from ONE
setting.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Final

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.voice.expressive_cues import DELIVERY_CUES, EVENT_CUES, Cue, CueDialect

#: The versioned lines file the block is read from.
CUE_PROMPT_LINES: Final[str] = "voice_expressive_cues_lines"

#: The cue an example is taken from first, of each kind, when the engine performs it.
_EXAMPLE_DELIVERY: Final[Cue] = Cue.WARM
_EXAMPLE_EVENT: Final[Cue] = Cue.SIGHS
#: The cues whose meaning names the night (``meaning.calm``, ``meaning.whispering``):
#: the rules' night clause speaks of them, so it is stated only when one is listed.
_NIGHT_CUES: Final[frozenset[Cue]] = frozenset({Cue.CALM, Cue.WHISPERING})
#: The block's indentation of a listed cue under its kind (layout, not prose).
_LISTED_INDENT: Final[str] = "  "


def _key(cue: Cue) -> str:
    """The suffix of a cue's rows in the lines file (``short pause`` → ``short_pause``)."""
    return cue.name.lower()


def _example_cue(performed: Set[Cue]) -> Cue:
    """The cue the example shows: warm, else the first delivery performed, else a sound."""
    for preferred, kind in ((_EXAMPLE_DELIVERY, DELIVERY_CUES), (_EXAMPLE_EVENT, EVENT_CUES)):
        if preferred in performed:
            return preferred
        first = next((cue for cue in Cue if cue in performed and cue in kind), None)
        if first is not None:
            return first
    raise ValueError("an engine that performs no cue has no example")


def _kind_lines(lines: Mapping[str, str], header: str, cues: list[Cue]) -> list[str]:
    """One kind's header and its cues, each with its meaning, in the vocabulary's order."""
    if not cues:
        return []
    listed = (
        _LISTED_INDENT
        + lines["cue"].format(cue=f"[{cue.value}]", meaning=lines[f"meaning.{_key(cue)}"])
        for cue in cues
    )
    return [lines[header], *listed]


def _rules_line(lines: Mapping[str, str], listed: Set[Cue], budget: int) -> str:
    """The rules row, each clause stated only when the block lists the cues it speaks of.

    ADR-284: a prompt promises only what the turn can run — an engine that
    performs a pause alone is never invited to open a sentence with a delivery,
    nor to soften the night with a cue it does not perform.
    """
    delivery, sound = bool(listed & DELIVERY_CUES), bool(listed & EVENT_CUES)
    if delivery and sound:
        news = lines["rules.news.both"].format(
            delivery=lines["rules.news.delivery"], sound=lines["rules.news.sound"]
        )
    else:
        news = lines["rules.news.delivery" if delivery else "rules.news.sound"]
    night = lines["rules.night"] if listed & _NIGHT_CUES else ""
    return lines["rules"].format(night=night, news=news, max_cues=budget)


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
    lines = dict(parse_prompt_sections(read_prompt_file(CUE_PROMPT_LINES), 2))
    return "\n".join(
        (
            lines["open"],
            lines["intro"],
            *_kind_lines(
                lines, "delivery", [cue for cue in Cue if cue in performed & DELIVERY_CUES]
            ),
            *_kind_lines(lines, "events", [cue for cue in Cue if cue in performed & EVENT_CUES]),
            _rules_line(lines, performed, budget),
            lines["never"],
            lines["example"].format(example=lines[f"example.{_key(_example_cue(performed))}"]),
            lines["close"],
        )
    )


__all__ = ["CUE_PROMPT_LINES", "expressive_cues_block"]
