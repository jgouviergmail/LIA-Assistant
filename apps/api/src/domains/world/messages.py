"""Bounded literal text and the live, mutual world visibility boundary."""

import hmac
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, field_validator

from src.domains.world.collision import private_home
from src.domains.world.schemas import ActorState, StrictModel, WorldState

MESSAGE_CHARS = 1000
MESSAGE_BYTES = 4096
TRANSLATION_CHARS = 3000
TRANSLATION_BYTES = 12288
MESSAGE_TTL = 1800
MESSAGE_INBOX_LIMIT = 100
MESSAGE_FRESH_SECONDS = 60
UUID_PATTERN = r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$"


def literal_text(value: str, *, chars: int = MESSAGE_CHARS, size: int = MESSAGE_BYTES) -> str:
    """Normalize bounded literal correspondence, rejecting empty, oversized or control-character text."""
    value = unicodedata.normalize("NFC", value.strip())
    if not value or len(value) > chars or len(value.encode("utf-8")) > size:
        raise ValueError("world_message_text_limit")
    if any(
        unicodedata.category(char) in {"Cc", "Cf"} and char not in {"\n", "\t", "\u200c", "\u200d"}
        for char in value
    ):
        raise ValueError("world_message_control_text")
    return value


class MailboxScope(StrictModel):
    epoch: str = Field(
        pattern=UUID_PATTERN,
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )
    controller: str = Field(
        min_length=16,
        max_length=128,
        description="Opaque controlling-tab fence; never a URL credential or public identity.",
    )


class MessageStatusRequest(MailboxScope):
    id: str = Field(
        pattern=UUID_PATTERN,
        description="Stable identifier within this model contract.",
    )


class TimedMessageRequest(MessageStatusRequest):
    created_at: float = Field(
        ge=0,
        description="Intent or message creation time as Unix seconds; client intents have a freshness bound.",
    )

    def require_fresh(self, now: float) -> None:
        """Reject stale intents and client timestamps beyond the allowed future-clock tolerance."""
        if not -5 <= now - self.created_at <= MESSAGE_FRESH_SECONDS:
            raise ValueError("world_message_expired")


class MessageRequest(TimedMessageRequest):
    recipient: str = Field(
        pattern=UUID_PATTERN,
        description="Opaque public actor identifier of the intended live recipient.",
    )
    text: str = Field(
        min_length=1,
        max_length=MESSAGE_CHARS,
        description="Bounded literal human or translated text; never instructions or executable markup.",
    )
    translation_consent: bool = Field(
        default=False,
        description="Explicit permission to spend the sender or recipient native translation quota.",
    )

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        """Validate human correspondence as bounded literal text, never executable instructions."""
        return literal_text(value)


class RetranslateRequest(TimedMessageRequest):
    message_id: str = Field(
        pattern=UUID_PATTERN,
        description="Identifier of an existing private message for an explicit retranslation request.",
    )
    translation_consent: Literal[True] = Field(
        description="Explicit permission to spend the sender or recipient native translation quota."
    )

    @field_validator("translation_consent", mode="before")
    @classmethod
    def explicit_consent(cls, value: object) -> object:
        """Require literal consent before a new recipient-requested translation can spend tokens."""
        if value is not True:
            raise ValueError("explicit_translation_consent_required")
        return value


@dataclass(frozen=True)
class MessageScope:
    account: str
    binding: str
    controller: str
    epoch: str
    eligible: frozenset[str]
    blocked: frozenset[str]
    idle_seconds: float


def _live(actor: ActorState, scope: MessageScope, now: float) -> bool:
    """Check account eligibility and both the actor's lease and idle deadline."""
    return (
        actor.account_id in scope.eligible
        and actor.expires_at > now
        and actor.activity_at + scope.idle_seconds > now
    )


def mailbox_actor(state: WorldState, scope: MessageScope, now: float) -> ActorState:
    """Require a live sender with the exact epoch, controller and constant-time cookie binding."""
    own = state.actors.get(scope.account)
    if (
        state.epoch != scope.epoch
        or own is None
        or not _live(own, scope, now)
        or not hmac.compare_digest(own.controller, scope.controller)
        or not hmac.compare_digest(own.binding, scope.binding)
    ):
        raise ValueError("world_message_unavailable")
    return own


def message_pair(
    state: WorldState, scope: MessageScope, public_id: str, now: float
) -> tuple[ActorState, ActorState]:
    """Resolve an eligible live pair outside private homes; reject blocked or self recipients."""
    own = mailbox_actor(state, scope, now)
    other = next((actor for actor in state.actors.values() if actor.public_id == public_id), None)
    if (
        other is None
        or other.account_id == own.account_id
        or other.account_id in scope.blocked
        or not _live(other, scope, now)
        or private_home(own.position)
        or private_home(other.position)
    ):
        raise ValueError("world_message_unavailable")
    return own, other
