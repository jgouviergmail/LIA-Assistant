"""The exchanges of a voice session, as one shape whichever carrier held them (ADR-301).

The phone's vendor hands the whole conversation over after the call (the
post-call webhook: ``data.transcript``, one entry per turn with ``role``,
``message``, ``time_in_call_secs`` and the tool calls between them — measured
2026-09-20). A browser session in direct mode accumulates its own turns in
its record. Both become a :class:`VoiceTranscript`: what the closing archives
as voice-only rows, what the relay synthesis reads, what the learning sees.

A **delegated exchange** is already in the thread: the graph archived the
turn when it ran. An exchange is what the browser buffers — the person's
turn and everything the voice said until the person's next turn — and an
exchange in which the voice called the delegation function is delegated
WHOLE, exactly as the browser skips a buffer it flagged ``delegated``
(``session-controller.ts``): the request, the announce, the small talk while
LIA worked and the restitution. Measured on the vendor's real engine
(2026-09-20, ADR-301 lot 4): an ASYNC call is written as a separate agent
entry with an empty message and ``tool_calls``, followed by an empty entry
with the acknowledging ``tool_results``, then — when the answer arrives —
a SECOND pair of the same shape and the restitution; the person's request
is the nearest USER entry before, never the entry before the call.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

#: The vendor names the agent ``agent``; the thread names it ``assistant``.
_ROLES: Final[dict[str, str]] = {"agent": "assistant", "assistant": "assistant", "user": "user"}
#: The relay prompt's vocabulary for a transcript line.
_PROMPT_ROLES: Final[dict[str, str]] = {"assistant": "agent", "user": "user"}


@dataclass(frozen=True, slots=True)
class VoiceTurn:
    """One turn of a voice session.

    Attributes:
        role: ``user`` or ``assistant``.
        text: What was said, stripped.
        offset_seconds: Seconds since the session started (0 when unknown).
        delegated: Part of an exchange the chat already holds.
    """

    role: str
    text: str
    offset_seconds: int = 0
    delegated: bool = False


@dataclass(frozen=True, slots=True)
class VoiceTranscript:
    """The turns of a session, in order."""

    turns: tuple[VoiceTurn, ...]

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[str, str]]) -> VoiceTranscript:
        """Turns from ``(role, text)`` pairs (a session record, archived rows).

        Args:
            rows: The pairs, in order; blank texts are dropped.

        Returns:
            The transcript.
        """
        turns = [
            VoiceTurn(role=_ROLES.get(role, role), text=text.strip())
            for role, text in rows
            if text and text.strip()
        ]
        return cls(turns=tuple(turns))

    @classmethod
    def from_vendor_payload(
        cls, payload: dict[str, Any], *, delegation_tool: str
    ) -> VoiceTranscript:
        """Turns from a post-call webhook payload, delegated exchanges marked.

        Args:
            payload: The vendor's post-call payload.
            delegation_tool: The name of the tool a delegation is made through.

        Returns:
            The transcript; empty when the payload carries none.
        """
        data = payload.get("data")
        raw = data.get("transcript") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return cls(turns=())
        entries = [entry for entry in raw if isinstance(entry, dict)]
        delegated = _delegated_indexes(entries, delegation_tool)
        turns: list[VoiceTurn] = []
        for index, entry in enumerate(entries):
            text = entry.get("message") or entry.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                continue
            # An entry of a role we do not know is DROPPED: words of unknown
            # authorship must never be archived as the person's own.
            role = _ROLES.get(str(entry.get("role") or ""))
            if role is None:
                continue
            turns.append(
                VoiceTurn(
                    role=role,
                    text=text.strip(),
                    offset_seconds=_offset(entry.get("time_in_call_secs")),
                    delegated=index in delegated,
                )
            )
        return cls(turns=tuple(turns))

    def voice_only(self) -> tuple[VoiceTurn, ...]:
        """The turns the chat never saw."""
        return tuple(turn for turn in self.turns if not turn.delegated)

    def voice_only_exchanges(self) -> tuple[tuple[VoiceTurn, ...], ...]:
        """The voice-only turns grouped as the browser archives them: by EXCHANGE.

        An exchange opens on the person's turn and holds the voice's turns
        that follow it; the voice's opening words (a greeting) form one of
        their own. The two rows of one exchange share a stamp, so the
        closing card's count (distinct stamps, ADR-185) reads a phone call
        exactly as it reads a browser session.
        """
        exchanges: list[list[VoiceTurn]] = []
        for turn in self.voice_only():
            if turn.role == "user" or not exchanges:
                exchanges.append([turn])
            else:
                exchanges[-1].append(turn)
        return tuple(tuple(exchange) for exchange in exchanges)

    def lines(self) -> list[str]:
        """``role: text`` per turn — the projection the relay synthesis reads.

        The relay prompt names the assistant ``agent`` (the vendor's word, the
        one its examples use); the thread names it ``assistant``. The turn
        keeps the thread's role, the line speaks the prompt's.
        """
        return [f"{_PROMPT_ROLES.get(turn.role, turn.role)}: {turn.text}" for turn in self.turns]

    def __bool__(self) -> bool:
        return bool(self.turns)


def _offset(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return int(value) if value >= 0 else 0


def _names(entries: Sequence[dict[str, Any]], index: int, field: str) -> set[str]:
    items = entries[index].get(field)
    if not isinstance(items, list):
        return set()
    return {str(item.get("tool_name") or "") for item in items if isinstance(item, dict)}


def _delegated_indexes(entries: Sequence[dict[str, Any]], tool: str) -> set[int]:
    """The entries of every delegated exchange — the whole exchange, by construction.

    An exchange runs from a user entry to the next user entry (the opening
    words before the first user entry form one of their own); one that holds
    a call of the delegation tool is delegated from its first entry to its
    last, as the browser's turn buffer is.
    """
    marked: set[int] = set()
    start = 0
    for index in range(len(entries) + 1):
        at_boundary = index == len(entries) or (
            index > start and entries[index].get("role") == "user"
        )
        if not at_boundary:
            continue
        exchange = range(start, index)
        if any(tool in _names(entries, j, "tool_calls") for j in exchange):
            marked.update(exchange)
        start = index
    return marked


__all__ = ["VoiceTranscript", "VoiceTurn"]
