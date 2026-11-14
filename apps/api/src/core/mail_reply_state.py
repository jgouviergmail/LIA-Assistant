"""Where an e-mail stands in its conversation: a closed annotation and its model view.

A message reached every reader ALONE until 2026-11-11: a qualification judged its
text (« a reply is expected »), a digest listed what it asked for, and nothing said
what happened next — so the assistant offered to answer mail the person had answered.
The annotation is the missing fact, read from the mailbox when the message is listed:
did the person answer, what did they say, did the other side answer a message they
sent. It rides beside ``classification`` under :data:`REPLY_STATE_KEY`.

What a MODEL is told follows the contract of ``classification_projection``: the fact
and never the instants of the reading. Two statuses are FACTS — an answer that was
sent stays sent — and are told whenever they are read. The three others are the
reading of a moment (« no reply yet »): past their validity they are told as
``not_checked``, which says nothing either way, so an earlier turn's reading is never
repeated as current. An instant a model does read — when the reply was sent — is
stored in the account's own zone, the zone of the clock the model is given.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

#: The key under which a published e-mail carries its annotation.
REPLY_STATE_KEY: Final = "reply_state"

ReplyStatus = Literal[
    "answered",  # received: the person answered its sender afterwards
    "answer_drafted",  # received: an unsent answer of the person's sits in the mailbox
    "unanswered",  # received: nothing from the person after it
    "reply_received",  # sent by the person: someone wrote in the conversation afterwards
    "awaiting_reply",  # sent by the person: nobody wrote after it
]
ReplyStateVersion = Literal["mail-reply-state-v1"]
REPLY_STATE_VERSION: Final[ReplyStateVersion] = "mail-reply-state-v1"

#: What stays true once observed; every other status is the reading of a moment.
DURABLE_STATUSES: Final[frozenset[ReplyStatus]] = frozenset({"answered", "reply_received"})
#: The statuses that are nothing without the message that settles them.
_STATUSES_NAMING_A_MESSAGE: Final[frozenset[ReplyStatus]] = frozenset(
    {"answer_drafted", "reply_received"}
)
#: The statuses that say nothing was found.
_STATUSES_OF_NOTHING: Final[frozenset[ReplyStatus]] = frozenset({"unanswered", "awaiting_reply"})

#: What a model is told of a reading too old to repeat.
NOT_CHECKED: Final = "not_checked"


class ReplyMessage(BaseModel):
    """The message that settles a status: the person's answer, their draft, or the reply they got."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: str = Field(description="Provider id of that message, for a reader to open it.")
    at: AwareDatetime = Field(
        description="When it was sent, saved or received, in the account's own zone."
    )
    correspondents: str = Field(
        default="", description="Who it went to, or who wrote it: display names, bounded."
    )
    excerpt: str = Field(default="", description="Its first line, bounded.")


class ReplyState(BaseModel):
    """Where one message stands in its conversation, as the mailbox said when it was read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: ReplyStateVersion = REPLY_STATE_VERSION
    status: ReplyStatus
    message: ReplyMessage | None = Field(
        default=None,
        description=(
            "The message that settles the status; absent when nothing was found, or when "
            "only the mailbox's own mark says the message was answered."
        ),
    )
    marked_at: AwareDatetime | None = Field(
        default=None,
        description="When the mailbox marked the message answered, when it dates its mark.",
    )
    conversation_size: int | None = Field(
        default=None,
        ge=1,
        description="Messages said in the conversation, drafts apart; None when the read was cut.",
    )
    observed_at: AwareDatetime
    valid_until: AwareDatetime

    @model_validator(mode="after")
    def coherent(self) -> ReplyState:
        """A status carries exactly the evidence it claims, for a positive lifetime."""
        if self.valid_until <= self.observed_at:
            raise ValueError("A reading must have positive validity")
        if self.status in _STATUSES_NAMING_A_MESSAGE and self.message is None:
            raise ValueError("This status names the message that settles it")
        if self.status in _STATUSES_OF_NOTHING and self.message is not None:
            raise ValueError("A status that found nothing carries no message")
        return self


def read_reply_state(value: object) -> ReplyState | None:
    """The annotation a stored value holds, or None when it holds none.

    Args:
        value: A stored annotation (its JSON form or the model).

    Returns:
        The annotation, or None for anything else.
    """
    if isinstance(value, ReplyState):
        return value
    try:
        return ReplyState.model_validate(value)
    except ValidationError:
        return None


def _instant(moment: datetime) -> str:
    """An instant as a model reads it: to the minute, with the offset it was stored in."""
    return moment.isoformat(timespec="minutes")


def _said(prefix: str, message: ReplyMessage, preposition: str) -> str:
    """One line naming when, who and what of the message that settles a status."""
    line = f"{prefix} on {_instant(message.at)}"
    if message.correspondents:
        line += f" {preposition} {message.correspondents}"
    return f"{line} — {message.excerpt}" if message.excerpt else line


def _summary(state: ReplyState) -> str:
    """What happened, in one line; empty when the status says it all."""
    message = state.message
    if state.status == "answered":
        if message is not None:
            return _said("answered", message, "to")
        marked = f" on {_instant(state.marked_at)}" if state.marked_at is not None else ""
        return (
            f"answered (marked by the mailbox{marked}; the reply itself was not found "
            "in the conversation)"
        )
    if message is None:
        return ""
    if state.status == "reply_received":
        return _said("reply received", message, "from")
    return _said("answer drafted, not sent, saved", message, "to")


def reply_state_view(value: object, now: datetime | None = None) -> dict[str, str] | None:
    """What a model is told of one annotation.

    Args:
        value: A stored annotation (its JSON form or the model).
        now: The moment it is shown; the current instant by default.

    Returns:
        The status, one line of what happened when there is something to say, and
        the size of the conversation when it holds several messages — or
        ``{"status": "not_checked"}`` for a reading of a moment past its validity;
        None when the value is no annotation.
    """
    state = read_reply_state(value)
    if state is None:
        return None
    moment = now if now is not None else datetime.now(UTC)
    if state.status not in DURABLE_STATUSES and moment >= state.valid_until:
        return {"status": NOT_CHECKED}
    view: dict[str, str] = {"status": state.status}
    if summary := _summary(state):
        view["summary"] = summary
    if state.conversation_size is not None and state.conversation_size > 1:
        view["conversation_messages"] = str(state.conversation_size)
    return view


def reply_state_fields(value: object, now: datetime | None = None) -> dict[str, str]:
    """The annotation as one field of a compact record; empty when it says nothing.

    Args:
        value: A stored annotation (its JSON form or the model).
        now: The moment it is shown; the current instant by default.

    Returns:
        ``{"reply_state": <what happened, else the status>}``, or an empty mapping
        for no annotation and for a reading too old to repeat.
    """
    view = reply_state_view(value, now)
    if view is None or view["status"] == NOT_CHECKED:
        return {}
    return {REPLY_STATE_KEY: view.get("summary") or view["status"]}


def reply_state_text(value: object, now: datetime | None = None) -> str:
    """The one-line form of :func:`reply_state_view`; empty when it says nothing.

    Args:
        value: A stored annotation (its JSON form or the model).
        now: The moment it is shown; the current instant by default.

    Returns:
        ``Reply state: …``, or an empty string for no annotation and for a reading
        too old to repeat.
    """
    said = reply_state_fields(value, now).get(REPLY_STATE_KEY)
    return f"Reply state: {said}" if said else ""


def answered_words(at: datetime | None) -> str:
    """That a message was answered, and when if it is known — nothing a correspondent wrote.

    Args:
        at: The instant of the answer, or of the mailbox's own mark; None when undated.

    Returns:
        ``answered on <instant>``, or ``answered``.
    """
    return f"answered on {_instant(at)}" if at is not None else "answered"


def answered_when(value: object) -> str | None:
    """When the person answered, in words that carry nothing a correspondent wrote.

    For a line stated OUTSIDE the data it qualifies (a directive of its own): who the
    answer went to and its first words are a correspondent's text, and stay in the
    record, where the data is marked external. An answer stays an answer: the age of
    the reading changes nothing.

    Args:
        value: A stored annotation (its JSON form or the model).

    Returns:
        ``answered on <instant>``, the instant being the answer's or the mailbox's own
        mark's, ``answered`` when neither is dated; None when the value is no
        annotation or says anything but ``answered``.
    """
    state = read_reply_state(value)
    if state is None or state.status != "answered":
        return None
    return answered_words(state.message.at if state.message is not None else state.marked_at)


__all__ = [
    "DURABLE_STATUSES",
    "NOT_CHECKED",
    "REPLY_STATE_KEY",
    "REPLY_STATE_VERSION",
    "ReplyMessage",
    "ReplyState",
    "ReplyStatus",
    "answered_when",
    "answered_words",
    "read_reply_state",
    "reply_state_fields",
    "reply_state_text",
    "reply_state_view",
]
