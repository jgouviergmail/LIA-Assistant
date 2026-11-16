"""Injected channel-to-assistant boundary; the channel domain owns no agent dependency."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ChannelStreamChunk(Protocol):
    @property
    def type(self) -> str: ...

    @property
    def content(self) -> object: ...

    @property
    def metadata(self) -> Mapping[str, object] | None: ...


class ChannelStop(StrEnum):
    """What a channel's stop gesture found (Telegram lot 33).

    The values key the bot's answers (``stop_<value>``).
    """

    STOPPING = "stopping"  # The discussion's running answer was asked to stop.
    NOTHING = "nothing"  # Nothing runs for the account.
    ELSEWHERE = "elsewhere"  # Something runs that this channel cannot stop.


class ChannelKeep(StrEnum):
    """What became of words written on a channel while the account was busy (lot 34)."""

    KEPT = "kept"  # They wait with the discussion; they leave at its next normal release.
    DEPARTED = "departed"  # The account was free after all: they left as the person's turn.
    TOO_LONG = "too_long"  # Added to what waits, they would exceed one message.
    DEPARTING = "departing"  # What waits is being sent right now and takes no more words.


class WaitingAction(StrEnum):
    """What a person may do on a channel with a message that did not leave (lot 34)."""

    SEND = "send"
    WITHDRAW = "withdraw"


class WaitingActionOutcome(StrEnum):
    """What a waiting action found; the values key the bot's answers (``waiting_<value>``)."""

    SENT = "sent"  # It left now.
    QUEUED = "queued"  # It leaves first when the account is released.
    WITHDRAWN = "withdrawn"
    GONE = "gone"  # That message no longer waits (it left, was withdrawn, or replaced).
    QUESTION = "question"  # A question waits in the discussion: it is answered first.


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """Where the person is, as they shared it on a channel (Telegram lot 8).

    Attributes:
        latitude: Degrees, -90 to 90.
        longitude: Degrees, -180 to 180.
        accuracy_m: The radius of uncertainty in metres, when measured.
    """

    latitude: float
    longitude: float
    accuracy_m: float | None = None


@dataclass(frozen=True)
class ChannelAgentRequest:
    user_message: str
    user_id: UUID
    session_id: str
    user_timezone: str
    user_language: str
    user_memory_enabled: bool
    original_run_id: str | None
    user_display_name: str | None
    user_journals_enabled: bool
    user_psyche_enabled: bool
    #: The mode the person chose (ADR-390): a channel turn runs in it like a chat
    #: turn. Required, never defaulted: a forgotten mode silently meant pipeline.
    user_execution_mode: str
    hitl_decision: Mapping[str, str] | None
    #: The position the person shared with this message: the turn's consented
    #: geolocation. Required, never defaulted: a caller that forgets it drops a pin.
    position: GeoPoint | None
    #: The files received with this message, stored as the chat stores an upload
    #: (lot 11): the turn's attachments. Required for the same reason.
    attachment_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class ChannelAssistantGateway:
    stream: Callable[[ChannelAgentRequest], AsyncGenerator[ChannelStreamChunk]]
    pending: Callable[[UUID, str], Awaitable[dict[str, object] | None]]
    confirmation_text: Callable[[str], str]
    stop: Callable[[UUID], Awaitable[ChannelStop]]
    #: Keep words written on a channel while the account is busy: (person, text, channel).
    keep: Callable[[UUID, str, str], Awaitable[ChannelKeep]]
    #: Send or withdraw the message a release held: (person, waiting message, action).
    act_on_waiting: Callable[[UUID, UUID, WaitingAction], Awaitable[WaitingActionOutcome]]
    #: An answer heard (lot 25): (person, language, answer as Markdown) → its MP3,
    #: or None when nothing is said (no words, a ceiling closed).
    speak: Callable[[UUID, str, str], Awaitable[bytes | None]]


_gateway: ChannelAssistantGateway | None = None


def configure_channel_gateway(
    gateway: ChannelAssistantGateway | None,
) -> ChannelAssistantGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_channel_gateway() -> ChannelAssistantGateway:
    if _gateway is None:
        raise RuntimeError("Channel assistant gateway is not initialized")
    return _gateway
