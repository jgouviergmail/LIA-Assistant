"""The prompt block that tells a spoken-comment writer which cues its engine performs (ADR-345).

A prompt states what the code enforces, and nothing else (ADR-284): the block
is rendered only when the engine that will speak performs at least one cue —
inline or as a style — and the budget is above zero; it lists exactly the cues
the engine performs, in LIA's canonical words (spelled the engine's way later
by :class:`~src.domains.voice.expressive_cues.AuthoredCues`), each delivery and
sound with the meaning that says when it fits, each persona cue with what it
sounds like — which manner fits is the personality's business, within the
rules (ADR-373); its rules speak only of the kinds it lists (a cue to open with,
a sound, a cue for the night); its example is one of them; and the budget it
publishes is the one the renderer enforces, from ONE setting.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Final

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.voice.expressive_cues import (
    DELIVERY_CUES,
    EVENT_CUES,
    PERSONA_CUES,
    Cue,
    CueDialect,
)

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
#: The kinds a live voice's block lists, in its order, with each kind's header row.
_LIVE_KINDS: Final[tuple[tuple[str, frozenset[Cue]], ...]] = (
    ("live.delivery", DELIVERY_CUES),
    ("live.persona", PERSONA_CUES),
    ("live.events", EVENT_CUES),
)


def _lines() -> dict[str, str]:
    """The rows of the lines file (cached by the prompt store, parsed per call)."""
    return dict(parse_prompt_sections(read_prompt_file(CUE_PROMPT_LINES), 2))


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


def _kind_lines(
    lines: Mapping[str, str], header: str, cues: list[Cue], described_by: str = "meaning"
) -> list[str]:
    """One kind's header and its cues, each with its ``described_by`` row, in vocabulary order."""
    if not cues:
        return []
    listed = (
        _LISTED_INDENT
        + lines["cue"].format(cue=f"[{cue.value}]", meaning=lines[f"{described_by}.{_key(cue)}"])
        for cue in cues
    )
    return [lines[header], *listed]


def _rules_line(lines: Mapping[str, str], listed: Set[Cue], budget: int) -> str:
    """The rules row, each clause stated only when the block lists the cues it speaks of.

    ADR-284: a prompt promises only what the turn can run — an engine that
    performs a pause alone is never invited to open a sentence with a delivery,
    nor to soften the night with a cue it does not perform.
    """
    # A persona cue opens a sentence like a delivery: « the one cue above that fits ».
    delivery = bool(listed & (DELIVERY_CUES | PERSONA_CUES))
    sound = bool(listed & EVENT_CUES)
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
    lines = _lines()
    return "\n".join(
        (
            lines["open"],
            lines["intro"],
            *_kind_lines(
                lines, "delivery", [cue for cue in Cue if cue in performed & DELIVERY_CUES]
            ),
            *_kind_lines(
                lines, "persona", [cue for cue in Cue if cue in performed & PERSONA_CUES], "sound"
            ),
            *_kind_lines(lines, "events", [cue for cue in Cue if cue in performed & EVENT_CUES]),
            _rules_line(lines, performed, budget),
            lines["never"],
            lines["example"].format(example=lines[f"example.{_key(_example_cue(performed))}"]),
            lines["close"],
        )
    )


def _tagged(dialect: CueDialect, cues: Set[Cue]) -> list[tuple[Cue, str]]:
    """The offered cues the engine performs as a tag (:meth:`CueDialect.tags`), in vocabulary order."""
    tags = dialect.tags()
    return [(cue, tags[cue]) for cue in Cue if cue in cues and cue in tags]


def live_cues_block(dialect: CueDialect, cues: Set[Cue]) -> str:
    """The block for a LIVE voice that writes its own cues (ADR-373).

    Unlike the comment writer's, whose words a renderer spells per engine,
    a live voice speaks straight to its engine: the block lists each offered
    cue in the ENGINE's own spelling, with what it sounds like — never when
    to use it, which is the personality's business (measured 2026-11-07: a
    description written as a trigger was obeyed as one). It publishes no
    count: nothing between the voice and its engine could enforce one
    (ADR-284); the stripping door measures them instead.

    Args:
        dialect: The dialect of the engine the voice speaks through.
        cues: The cues LIA offers this session (the person's, or a stranger's).

    Returns:
        The block, or "" when the engine performs none of the offered cues.
    """
    tagged = _tagged(dialect, cues)
    if not tagged:
        return ""
    lines = _lines()
    rendered = [lines["live.open"], lines["live.intro"]]
    for header, kind in _LIVE_KINDS:
        listed = [(cue, spelled) for cue, spelled in tagged if cue in kind]
        if listed:
            rendered.append(lines[header])
            rendered.extend(
                _LISTED_INDENT
                + lines["live.cue"].format(cue=spelled, sound=lines[f"sound.{_key(cue)}"])
                for cue, spelled in listed
            )
    rendered.extend((lines["live.rules"], lines["live.close"]))
    return "\n".join(rendered)


def palette(dialect: CueDialect, cues: Set[Cue]) -> list[dict[str, str]]:
    """The offered cues as a vendor's suggested-tag palette: the live block, as data.

    Each entry names the tag without its brackets and describes what it
    sounds like, from the same ``sound.<cue>`` row the live block reads —
    the vendor turns the palette into a prompt of its own, so a description
    that said WHEN would be a second, competing instruction.

    Args:
        dialect: The dialect of the agent's speaking engine.
        cues: The cues LIA offers.

    Returns:
        ``[{"tag", "description"}, …]`` in the vocabulary's order; empty when
        the engine performs none of them.
    """
    lines = _lines()
    return [
        {"tag": spelled[1:-1], "description": lines[f"sound.{_key(cue)}"]}
        for cue, spelled in _tagged(dialect, cues)
    ]


__all__ = ["CUE_PROMPT_LINES", "expressive_cues_block", "live_cues_block", "palette"]
