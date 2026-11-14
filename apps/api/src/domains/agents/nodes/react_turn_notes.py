"""The person's notes in a ReAct turn: recorded, shown in place, folded at the exit (ADR-385).

The door (``agents/api/turn_notes``) opens the notes, reads what joined and closes
them; this module is what the loop does with what it read:

- **recorded**: each note read becomes a record of the turn (``react_turn_notes``),
  placed after the last message the loop had and after the recovery passes already
  taken — plain values a checkpoint keeps, reset at the turn's start;
- **shown**: every later call shows it as the person's message at that place,
  stamped with when it was written (ADR-381) and framed by one versioned line, never
  written into ``messages`` (``react_shown``);
- **folded**: at the loop's exit the turn's question (the same message, by its id)
  receives each note after its text, so the response, the extractions and the later
  turns read the request as the person completed it. Folding mid-loop would change
  the history before the loop's thinking (ADR-306).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.time_utils import resolve_zone
from src.domains.agents.api.turn_notes import TakenNote, close_turn_notes, read_turn_notes
from src.domains.agents.nodes.react_recovery import recovery_shown
from src.domains.agents.nodes.react_shown import Shown, note_order
from src.domains.shared.extraction_targets import find_last_user_message
from src.infrastructure.llm.message_view import WRITTEN_AT_KEY, with_written_at, written_prefix

#: The state key holding the turn's notes (declared in ``MessagesState``).
TURN_NOTES_KEY = "react_turn_notes"


def _note_template() -> str:
    """The versioned framing line of a note (the store caches the file)."""
    return dict(parse_prompt_sections(read_prompt_file("react_turn_note_lines"), 2))["note"]


def _note_text(text: str) -> str:
    """The note as the model reads it, framed: the person's words are a value, never a template."""
    return _note_template().format(text=text)


def note_record(note: TakenNote, *, anchor_id: str, passes_before: int) -> dict[str, Any]:
    """The turn's record of one note read: plain values a checkpoint keeps.

    Args:
        note: The note, as the door archived it.
        anchor_id: The id of the last message the loop had when it read it.
        passes_before: How many recovery passes the turn had taken then.

    Returns:
        The record, keyed by stable names.
    """
    return {
        "id": str(note.message_id),
        "text": note.text,
        "written_at": note.written_at.isoformat(),
        "anchor_id": anchor_id,
        "passes_before": passes_before,
    }


def _message(record: Mapping[str, Any]) -> HumanMessage:
    """The person's message a record stands for, carrying when it was written."""
    return HumanMessage(
        content=_note_text(str(record["text"])),
        additional_kwargs={WRITTEN_AT_KEY: str(record["written_at"])},
    )


def notes_shown(records: Sequence[Mapping[str, Any]], zone: str | None) -> list[Shown]:
    """What each note shows a call: the person's message, stamped, at its place.

    Args:
        records: The turn's notes.
        zone: The person's display zone (``user_timezone``).

    Returns:
        One item per note.
    """
    person_zone = resolve_zone(zone)
    return [
        Shown(
            anchor_id=str(record["anchor_id"]),
            order=note_order(int(record["passes_before"])),
            messages=tuple(with_written_at([_message(record)], person_zone)),
        )
        for record in records
    ]


def _suffix(records: Sequence[Mapping[str, Any]], zone: str | None) -> str:
    """The notes as they follow the turn's request: each stamped, after a blank line."""
    person_zone = resolve_zone(zone)
    return "".join(
        f"\n\n{written_prefix(_message(record), person_zone)}{_note_text(str(record['text']))}"
        for record in records
    )


def fold_notes(
    question: BaseMessage, records: Sequence[Mapping[str, Any]], zone: str | None
) -> BaseMessage:
    """The turn's question with each note after its text, once.

    Args:
        question: The person's message that opened the turn.
        records: The turn's notes.
        zone: The person's display zone.

    Returns:
        A copy carrying the notes (same id, same keyword arguments), or the question
        itself when there is nothing to fold or it already carries them.
    """
    if not records:
        return question
    suffix = _suffix(records, zone)
    content = question.content
    if isinstance(content, str):
        if content.endswith(suffix):
            return question
        return question.model_copy(update={"content": f"{content}{suffix}"})
    part = {"type": "text", "text": suffix.lstrip("\n")}
    if content and content[-1] == part:
        return question
    return question.model_copy(update={"content": [*content, part]})


def with_turn_notes(text: str, state: Mapping[str, Any]) -> str:
    """The turn's request as the person completed it, for a reader given it as text.

    Args:
        text: The request as the reader holds it (the router's reading of it, or the
            question's text).
        state: The turn's state.

    Returns:
        The text followed by the turn's notes, once.
    """
    records = state.get(TURN_NOTES_KEY) or []
    if not records:
        return text
    suffix = _suffix(records, state.get("user_timezone"))
    return text if text.endswith(suffix) else f"{text}{suffix}"


def shown_this_call(state: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> list[Shown]:
    """Everything one call is shown beside the thread: the recovery passes, then the notes.

    Args:
        state: The turn's state.
        records: The turn's notes, those read for this call included.

    Returns:
        The items, ordered among themselves by ``react_shown``.
    """
    return [
        *recovery_shown(state.get("react_recovery_passes") or []),
        *notes_shown(records, state.get("user_timezone")),
    ]


def notes_update(state: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The state update recording the notes read at this call; nothing when none was.

    Args:
        state: The turn's state at the start of the call.
        records: The turn's notes after this call's read.

    Returns:
        ``{"react_turn_notes": records}``, or an empty update.
    """
    if len(records) == len(state.get(TURN_NOTES_KEY) or []):
        return {}
    return {TURN_NOTES_KEY: list(records)}


def merge_settled(update: Mapping[str, Any], settled: Mapping[str, Any]) -> dict[str, Any]:
    """A node's update with the folded question of the loop's exit appended to its messages.

    Args:
        update: What the exiting node writes.
        settled: What :func:`settle_turn_notes` returned.

    Returns:
        One update: the node's messages, then the folded question (which replaces the
        question in place, by its id).
    """
    folded = list(settled.get("messages") or [])
    if not folded:
        return dict(update)
    earlier = update.get("messages")
    return {**update, "messages": [*(earlier if isinstance(earlier, list) else []), *folded]}


async def take_turn_notes(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read what joined since the last call, and record it after the loop's last message.

    Args:
        state: The turn's state at the start of a model call.

    Returns:
        The turn's notes, those just read included.
    """
    records = list(state.get(TURN_NOTES_KEY) or [])
    taken = await read_turn_notes()
    if not taken:
        return records
    messages = state.get("messages") or []
    anchor_id = str(messages[-1].id) if messages else ""
    passes_before = len(state.get("react_recovery_passes") or [])
    return [
        *records,
        *(note_record(note, anchor_id=anchor_id, passes_before=passes_before) for note in taken),
    ]


async def settle_turn_notes(state: Mapping[str, Any]) -> dict[str, Any]:
    """At the loop's exit: stop taking notes, and fold the turn's into its request.

    Args:
        state: The turn's state when the loop ends.

    Returns:
        The state update: the folded question, or nothing.
    """
    await close_turn_notes()
    records = state.get(TURN_NOTES_KEY) or []
    question, _ = find_last_user_message(list(state.get("messages") or []))
    if not records or question is None:
        return {}
    folded = fold_notes(question, records, state.get("user_timezone"))
    return {} if folded is question else {"messages": [folded]}


__all__ = [
    "TURN_NOTES_KEY",
    "fold_notes",
    "merge_settled",
    "note_record",
    "notes_shown",
    "notes_update",
    "settle_turn_notes",
    "shown_this_call",
    "take_turn_notes",
    "with_turn_notes",
]
