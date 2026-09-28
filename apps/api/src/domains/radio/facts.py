"""What a segment is allowed to say: the facts handed to the writer, and nothing else.

Every spoken claim must cite one of these by id, and the verifier checks it. A
fact carries its KIND (which decides the material it belongs to), its
SENSITIVITY (which decides who may voice it) and its KEY (its identity across
sessions, so the station does not tell the same thing twice).

The isolation rule lives here, at construction: a pack for a news format holds
no record of the person, and a pack for a personal format holds no article. An
injected instruction inside an article therefore never shares a prompt with
the person's mail — and the person's mail never leaves the host's mouth.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.radio.constants import (
    FACT_KEY_MAX_CHARS,
    FACT_TEXT_MAX_CHARS,
    SOURCE_LABEL_MAX_CHARS,
)
from src.domains.radio.formats import FORMAT_SPECS, Material, RadioFormat


class FactKind(StrEnum):
    """What a fact is about. Decides which material it belongs to."""

    CLOCK = "clock"
    WEATHER = "weather"
    NEWS = "news"
    ANALYSIS = "analysis"
    EVENT = "event"
    REMINDER = "reminder"
    TASK = "task"
    COMMITMENT = "commitment"
    TICKET = "ticket"
    EMAIL = "email"
    RELATION = "relation"
    BOOKMARK = "bookmark"
    NOTIFICATION = "notification"
    HEALTH = "health"
    SPACE = "space"
    MEETING = "meeting"
    CONVERSATION = "conversation"
    #: What LIA did for the listener — a row of the effect register (ADR-324 decision 41).
    ACTION = "action"
    #: What the listener's newsroom holds for them — the station's own word, never news.
    NEWSROOM = "newsroom"


class Sensitivity(StrEnum):
    """Who may voice a fact: public facts anyone, the person's facts LIA alone."""

    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"


#: Kinds every format may carry: the clock and the weather.
_NEUTRAL: Final[frozenset[FactKind]] = frozenset({FactKind.CLOCK, FactKind.WEATHER})
#: Kinds that FRAME a programme and are never its subject: the clock and the
#: weather frame every segment, an analysis point reads the story it belongs to.
FRAMING_KINDS: Final[frozenset[FactKind]] = _NEUTRAL | {FactKind.ANALYSIS}

#: The kinds each material admits. The listener's taste is never among them: it
#: is the writer's context, never a fact a line may state (``ListenerTaste``).
ALLOWED_KINDS: Final[dict[Material, frozenset[FactKind]]] = {
    Material.NONE: _NEUTRAL | {FactKind.NEWSROOM},
    Material.NEWS: _NEUTRAL | {FactKind.NEWS, FactKind.ANALYSIS},
    Material.PERSONAL: frozenset(FactKind) - {FactKind.NEWS, FactKind.ANALYSIS, FactKind.NEWSROOM},
}


class SourceRef(BaseModel):
    """Where a fact comes from — what the transcript shows next to a sentence."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(
        min_length=1,
        max_length=SOURCE_LABEL_MAX_CHARS,
        description="Outlet name for an article, record family for the person's data.",
    )
    url: str | None = Field(default=None, description="Article URL (public sources only).")
    published_at: datetime | None = Field(default=None, description="Publication instant.")
    record_kind: str | None = Field(
        default=None, description="The person's record family (event, email…), for a record."
    )
    record_id: str | None = Field(default=None, description="The record's own id, for a record.")
    story_key: str | None = Field(
        default=None,
        description="The newsroom story it comes from — the article the radio page opens.",
    )


class RadioFact(BaseModel):
    """One fact a segment may voice, cited by its id."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=8, description="Short id the script cites (n1, p3…).")
    kind: FactKind = Field(description="What the fact is about.")
    text: str = Field(min_length=1, max_length=FACT_TEXT_MAX_CHARS, description="The fact.")
    key: str = Field(
        min_length=1,
        max_length=FACT_KEY_MAX_CHARS,
        description="Identity across sessions, so the station never repeats itself.",
    )
    sensitivity: Sensitivity = Field(description="Who may voice it.")
    source: SourceRef | None = Field(default=None, description="Where it comes from.")
    returning: bool = Field(
        default=False,
        description="A story the listener already heard, an angle programme comes back to.",
    )


class FactPack(BaseModel):
    """The facts one segment may voice — isolated by material at construction."""

    model_config = ConfigDict(frozen=True)

    format: RadioFormat = Field(description="The format the pack feeds.")
    facts: tuple[RadioFact, ...] = Field(description="The facts, in the order offered.")

    @model_validator(mode="after")
    def _isolated_and_unique(self) -> FactPack:
        ids = [fact.id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact ids must be unique inside a pack")
        allowed = ALLOWED_KINDS[FORMAT_SPECS[self.format].material]
        strays = sorted({fact.kind.value for fact in self.facts if fact.kind not in allowed})
        if strays:
            raise ValueError(
                f"a {self.format.value} pack cannot carry {strays}: material isolation"
            )
        return self

    def by_id(self) -> dict[str, RadioFact]:
        """The facts keyed by the id the script cites."""
        return {fact.id: fact for fact in self.facts}

    @property
    def keys(self) -> tuple[str, ...]:
        """The identities of the facts, for the anti-repeat ledger."""
        return tuple(fact.key for fact in self.facts)


#: The id every pack gives its clock, so a line saying the time can cite it.
CLOCK_FACT_ID: Final[str] = "c1"
_WEEKDAYS: Final[tuple[str, ...]] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def notification_key(message_id: object) -> str:
    """The key a notification airs under — the corner's and a news flash's alike.

    One key for both, so what one of them told is heard, and the other never
    tells it again.

    Args:
        message_id: The archived message.

    Returns:
        The fact key.
    """
    return f"notification:{message_id}"[:FACT_KEY_MAX_CHARS]


#: The id every pack gives the newsroom's own fact.
NEWSROOM_FACT_ID: Final[str] = "s1"


def everything_heard_fact(window_hours: int) -> RadioFact:
    """The fact « nothing new » is said from: the listener heard every story left.

    Args:
        window_hours: The window the newsroom's stories are aired from.

    Returns:
        A public fact of the station's own, never an anti-repeat entry.
    """
    return RadioFact(
        id=NEWSROOM_FACT_ID,
        kind=FactKind.NEWSROOM,
        text=(
            f"The listener has already heard every story their sources published in the "
            f"last {window_hours} hours; the news resumes as soon as a new one is published."
        ),
        key="newsroom:everything-heard",
        sensitivity=Sensitivity.PUBLIC,
    )


def local_time_text(moment: datetime) -> str:
    """A local instant written without the process locale: « Saturday 2026-09-26, 05:13 »."""
    return f"{local_day_text(moment)}, {moment:%H:%M}"


def local_day_text(moment: datetime) -> str:
    """A local day written without the process locale: « Saturday 2026-09-26 »."""
    return f"{_WEEKDAYS[moment.weekday()]} {moment.date().isoformat()}"


def clock_fact(local_now: datetime) -> RadioFact:
    """The listener's local day and time, as a fact a line may cite to say them.

    Written without the process locale (an English weekday, an ISO date, a
    24-hour time), so its figures are the ones a line saying the time repeats.

    Args:
        local_now: The listener's local time (aware).

    Returns:
        A public clock fact, keyed by the minute (never an anti-repeat entry).
    """
    return RadioFact(
        id=CLOCK_FACT_ID,
        kind=FactKind.CLOCK,
        text=local_time_text(local_now),
        key=f"clock:{local_now.isoformat(timespec='minutes')}",
        sensitivity=Sensitivity.PUBLIC,
    )
