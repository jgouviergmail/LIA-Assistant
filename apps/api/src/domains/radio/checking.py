"""The model verifier's verdict, and what it means for the lines (ADR-324, Q5).

The deterministic verifier cannot see a claim that paraphrases its fact wrongly
without a digit. When the listener asked for it, a model reads every SOURCED
line against the facts it cites and returns a verdict per line — and an omission
counts against the line: a verifier that skipped a line did not vouch for it,
and « not vouched » is what the listener asked not to hear. Two verdicts that
disagree on one line count as « not supported » for the same reason.

A line that cites nothing (a transition) is never sent: there is nothing to
check it against, and the deterministic verifier already bounds it.

Each verdict states what the cited facts say about the line's specific
statements BEFORE it decides (``LineVerdict.evidence``). Measured 2026-09-27 on
a fixed set — the real columns of two measuring rounds, labelled line by line,
and nine claims no digit betrays planted in them (30 scripts, three passes
each): the verifier as first written rejected a supported line 31 % of the time
and refused one column in two; told that a framing covers nothing else and that
other words may say the same thing, and made to say what the facts hold first,
12 to 16 % and one column in four — and it still rejected every planted claim.
Asking it to quote the words it rejects changed nothing measurable, and a rule
reading that quote would drop a true rejection whenever a model quotes loosely:
the verdict is taken as it comes.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from src.domains.radio.verification import VerifiedLine


class LineVerdict(BaseModel):
    """The verifier's word on one line."""

    model_config = ConfigDict(frozen=True)

    line: int = Field(description="The line's number, as the list shows it.")
    # Before the verdict, on purpose: a model writes the fields in order.
    evidence: str = Field(
        description=(
            "Before the verdict: for each specific statement the line makes about the story, "
            "what its cited facts say about it, in a few words, or « nothing »."
        )
    )
    supported: bool = Field(description="Whether the cited facts support every claim of the line.")


class CheckDraft(BaseModel):
    """What the verifier returns: one verdict per line, in order."""

    model_config = ConfigDict(frozen=True)

    verdicts: list[LineVerdict] = Field(
        default_factory=list, description="One verdict for every line, in order."
    )


def checked_positions(lines: Sequence[VerifiedLine]) -> list[int]:
    """The places of the lines the verifier reads: those citing a fact, in order.

    The verifier sees them numbered from 1 in this order.
    """
    return [position for position, line in enumerate(lines) if line.refs]


def unsupported_positions(
    lines: Sequence[VerifiedLine], verdicts: Sequence[LineVerdict]
) -> frozenset[int]:
    """The places of the checked lines the verifier did not vouch for.

    Args:
        lines: The verified lines, as the production holds them.
        verdicts: The verifier's answer (numbers as shown, from 1).

    Returns:
        Every checked line without a verdict, with a « not supported » one, or
        with two that disagree. A number that names no checked line is ignored.
    """
    checked = checked_positions(lines)
    said: dict[int, set[bool]] = {}
    for verdict in verdicts:
        said.setdefault(verdict.line, set()).add(verdict.supported)
    return frozenset(
        position for number, position in enumerate(checked, start=1) if said.get(number) != {True}
    )


__all__ = ["CheckDraft", "LineVerdict", "checked_positions", "unsupported_positions"]
