"""A news flash: LIA breaks into the programme to say what she just wrote in the chat.

ADR-324 decision 32. When LIA sends the listener a proactive notification while
their radio is on air, the station says it on air too: the host breaks in, says
what was written and what it may mean to them, and hands back to the programme
where it stopped. A flash lives OUTSIDE the running order — the grid never plans
one and its place is a number of its own, from ``FLASH_SEQ_BASE`` — because it
airs as an INTERRUPTION: the player keeps the programme it cut at its position,
plays the flash, and resumes it (``Playhead.flash_heard`` then says it aired).

The loop takes the notifications archived after the watermark — the session's
start, then the newest one a flash took —, at most ``FLASH_NOTES_MAX`` at once,
one flash in production or waiting at a time, and only while the listener hears
the antenna: never before the first sound, never while paused, never once the
farewell is planned. A flash that could not be produced leaves the state and its
notes are not taken again — they stay in the chat, where the personal corner may
still come back to them.

Pure: the state in, the state out; instants are inputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from src.domains.radio.constants import FACT_TEXT_MAX_CHARS, FLASH_NOTES_MAX
from src.domains.radio.facts import (
    FactKind,
    FactPack,
    RadioFact,
    Sensitivity,
    notification_key,
)
from src.domains.radio.formats import RadioFormat
from src.domains.radio.session import SessionState, hearing

#: A flash's place is a number the running order never reaches.
FLASH_SEQ_BASE: Final[int] = 100_000


@dataclass(frozen=True, slots=True)
class FlashNote:
    """A notification LIA just sent the listener, as a flash tells it.

    Attributes:
        id: The archived message.
        sent_at: When it was sent (aware).
        topic: What kind of notification it was (``interest``, ``heartbeat``…).
        excerpt: The beginning of what was said, in plain words.
    """

    id: str
    sent_at: datetime
    topic: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class Flash:
    """One flash of the session.

    Attributes:
        seq: Its place — its audio's name, beyond every slot's.
        notes: The notifications it tells (their message ids).
        produced: Whether its audio is ready.
    """

    seq: int
    notes: tuple[str, ...]
    produced: bool = False


def is_flash_seq(seq: int) -> bool:
    """Whether a place is a flash's rather than a slot's."""
    return seq > FLASH_SEQ_BASE


def flash_watermark(state: SessionState) -> datetime:
    """The instant after which a notification is news to the station."""
    return state.flash_since or state.started_at


def flash_allowed(state: SessionState) -> bool:
    """Whether a flash may start now: the listener hears the antenna, and nothing else flashes."""
    return (
        state.ended is None
        and state.paused_since is None
        and not state.flashes
        and hearing(state)
        and not any(slot.format is RadioFormat.SIGN_OFF for slot in state.slots)
    )


def flash_started(state: SessionState, notes: Sequence[FlashNote]) -> tuple[SessionState, Flash]:
    """A flash starts for ``notes``: the next number, and the newest note as the watermark.

    Args:
        state: The session.
        notes: The notifications it tells, oldest first.

    Returns:
        The new state and the flash.

    Raises:
        ValueError: With no note, or more than ``FLASH_NOTES_MAX``.
    """
    if not notes or len(notes) > FLASH_NOTES_MAX:
        raise ValueError(f"a flash tells one note at least, at most {FLASH_NOTES_MAX}")
    flash = Flash(
        seq=FLASH_SEQ_BASE + state.flashes_made + 1, notes=tuple(note.id for note in notes)
    )
    newest = max(note.sent_at for note in notes)
    return (
        replace(
            state,
            flashes=(*state.flashes, flash),
            flashes_made=state.flashes_made + 1,
            flash_since=max(newest, flash_watermark(state)),
        ),
        flash,
    )


def flash_produced(state: SessionState, seq: int, *, duration_s: float) -> SessionState:
    """The flash's audio is ready: it waits to be heard, and its seconds count as radio."""
    return replace(
        state,
        flashes=tuple(replace(f, produced=True) if f.seq == seq else f for f in state.flashes),
        flash_audio_s=state.flash_audio_s + duration_s,
    )


def flash_failed(state: SessionState, seq: int) -> SessionState:
    """The flash could not be produced: it leaves the state (its notes are not taken again)."""
    return replace(state, flashes=tuple(f for f in state.flashes if f.seq != seq))


def flashes_heard(state: SessionState, heard: int) -> SessionState:
    """The player heard every produced flash up to ``heard``: they leave the state."""
    kept = tuple(f for f in state.flashes if not (f.produced and f.seq <= heard))
    return state if kept == state.flashes else replace(state, flashes=kept)


def pending_flash(state: SessionState) -> Flash | None:
    """The produced flash the player has not said it heard, if any."""
    return next((f for f in state.flashes if f.produced), None)


def flash_pack(notes: Sequence[FlashNote]) -> FactPack:
    """The facts a flash is given: each note LIA just sent, the listener's own.

    Keyed like the personal corner's notification (:func:`notification_key`), so
    a note a flash told is heard, and the corner never comes back to it.

    Args:
        notes: The notifications, oldest first.

    Returns:
        The pack, ``f1`` to ``fN``.
    """
    return FactPack(
        format=RadioFormat.FLASH,
        facts=tuple(
            RadioFact(
                id=f"f{index}",
                kind=FactKind.NOTIFICATION,
                text=(
                    f"LIA has just written to the listener in the chat ({note.topic}): "
                    f'"{note.excerpt}"'
                )[:FACT_TEXT_MAX_CHARS],
                key=notification_key(note.id),
                sensitivity=Sensitivity.PERSONAL,
            )
            for index, note in enumerate(notes, start=1)
        ),
    )


def what_it_cuts(state: SessionState, *, now: datetime, ready_in_s: float) -> RadioFormat | None:
    """The programme a flash starting now will cut — None when it will cut none.

    A flash is written when it starts and heard when it is ready: the programme
    on air may be over by then (measured 2026-09-27 — a flash written over the
    welcome, heard after it, said « back to the welcome »). It is named only
    while more of it is left than the flash takes to produce.

    Args:
        state: The session.
        now: The current instant (timezone-aware).
        ready_in_s: When the flash is expected to be ready, from now.

    Returns:
        The programme's format, or None.
    """
    playhead = state.playhead
    if playhead is None or not playhead.playing:
        return None
    slot = next((slot for slot in state.slots if slot.seq == playhead.seq), None)
    if slot is None:
        return None
    heard = playhead.position_s + max(0.0, (now - playhead.reported_at).total_seconds())
    return slot.format if slot.duration_s - heard > ready_in_s else None


def what_resumes(state: SessionState, cuts: RadioFormat | None) -> RadioFormat | None:
    """The programme the station goes on with after a flash — named only when certain.

    The one it cuts (the player holds it where it stopped); else the next one,
    once it is READY — a programme still in production may never air.

    Args:
        state: The session.
        cuts: What the flash cuts (:func:`what_it_cuts`).

    Returns:
        The programme's format, or None.
    """
    if cuts is not None:
        return cuts
    playhead = state.playhead
    if playhead is None:
        return None
    after = playhead.seq + 1 if playhead.playing else playhead.seq
    upcoming = next((slot for slot in state.slots if slot.seq >= after), None)
    return upcoming.format if upcoming and upcoming.seq in state.produced else None


__all__ = [
    "FLASH_NOTES_MAX",
    "FLASH_SEQ_BASE",
    "Flash",
    "FlashNote",
    "flash_allowed",
    "flash_failed",
    "flash_pack",
    "flash_produced",
    "flash_started",
    "flash_watermark",
    "flashes_heard",
    "is_flash_seq",
    "pending_flash",
    "what_it_cuts",
    "what_resumes",
]
