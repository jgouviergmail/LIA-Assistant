"""The voice session value: one key, one run id, one mode, whichever carrier (ADR-301).

The key is the value both carriers write in the ``live_session_id`` metadata of
every row they file — the delegated turns, the voice-only ``live_turn`` rows,
the closing card — so the summary queries (:mod:`summary`) read one field
whatever the line was. For the browser it is the session id; for the phone it
is the call's run id (``phone_call_<hex>``), the id ADR-290 already files
every euro of a call under, minted HERE so that ``telephony`` reads it from
this module rather than the other way round (``telephony`` imports this
package; this package imports no carrier).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal, get_args
from uuid import UUID

#: How a session runs: every request delegated to the chat (HITL, actions,
#: registers), or the voice reading LIA's tools itself and never acting.
VoiceSessionMode = Literal["delegated", "direct"]
VOICE_SESSION_MODES: Final[tuple[str, ...]] = get_args(VoiceSessionMode)

#: The prefix of a phone call's run id (and session key): stable for the call's
#: whole life, so a retried relay and a late lookup land on the same summary row.
PHONE_CALL_RUN_PREFIX: Final = "phone_call_"


class VoiceCarrier(str, Enum):
    """Which line carries the session — decides where the record lives, nothing else."""

    BROWSER = "browser"
    PHONE = "phone"


#: The origin kind each carrier stamps on the rows of a delegated turn (the
#: ``RunOrigin.kind`` and the metadata key), and the decision route.
_ORIGIN_KIND: Final[dict[VoiceCarrier, str]] = {
    VoiceCarrier.BROWSER: "live_session",
    VoiceCarrier.PHONE: "phone_call",
}


def as_voice_session_mode(value: str) -> VoiceSessionMode:
    """Narrow a stored string to the mode vocabulary — a cast-free reading.

    Args:
        value: What a record or a column holds.

    Returns:
        The mode.

    Raises:
        ValueError: A value off the vocabulary — only our own writers fill
            those records, so this is a programming error, never a fallback.
    """
    if value == "delegated":
        return "delegated"
    if value == "direct":
        return "direct"
    raise ValueError(f"unknown voice session mode: {value!r}")


def phone_session_key(call_id: UUID) -> str:
    """The run id — and session key — of a phone call.

    Args:
        call_id: The ``phone_calls`` row.

    Returns:
        ``phone_call_<hex>``.
    """
    return f"{PHONE_CALL_RUN_PREFIX}{call_id.hex}"


@dataclass(frozen=True, slots=True)
class VoiceSession:
    """One voice session, as the shared rules see it.

    Attributes:
        carrier: The line.
        key: The value filed in ``live_session_id`` by every row of the session.
        run_id: The session's own run id — what the tool host and the learning
            file their spend under (the phone: the same as the key).
        origin_id: The carrier's own id, as a string (a session id, a call id).
        mode: ``delegated`` or ``direct``.
        user_id: The account.
        conversation_id: The person's conversation.
        language: Backend-canonical language.
        timezone: IANA zone.
    """

    carrier: VoiceCarrier
    key: str
    run_id: str
    origin_id: str
    mode: VoiceSessionMode
    user_id: UUID
    conversation_id: UUID
    language: str
    timezone: str

    def __post_init__(self) -> None:
        as_voice_session_mode(self.mode)

    @property
    def origin_kind(self) -> str:
        """The origin kind of the carrier (``live_session`` / ``phone_call``)."""
        return _ORIGIN_KIND[self.carrier]

    @property
    def delegated(self) -> bool:
        """Whether every request goes to the chat."""
        return self.mode == "delegated"

    @classmethod
    def browser(
        cls,
        *,
        session_id: str,
        run_id: str,
        mode: VoiceSessionMode,
        user_id: UUID,
        conversation_id: UUID,
        language: str,
        timezone: str,
    ) -> VoiceSession:
        """A browser session: the session id is the key, the run id its own."""
        return cls(
            carrier=VoiceCarrier.BROWSER,
            key=session_id,
            run_id=run_id,
            origin_id=session_id,
            mode=mode,
            user_id=user_id,
            conversation_id=conversation_id,
            language=language,
            timezone=timezone,
        )

    @classmethod
    def phone(
        cls,
        *,
        call_id: UUID,
        mode: VoiceSessionMode,
        user_id: UUID,
        conversation_id: UUID,
        language: str,
        timezone: str,
    ) -> VoiceSession:
        """A phone call: the call's run id is both the key and the run id."""
        key = phone_session_key(call_id)
        return cls(
            carrier=VoiceCarrier.PHONE,
            key=key,
            run_id=key,
            origin_id=str(call_id),
            mode=mode,
            user_id=user_id,
            conversation_id=conversation_id,
            language=language,
            timezone=timezone,
        )


__all__ = [
    "PHONE_CALL_RUN_PREFIX",
    "VOICE_SESSION_MODES",
    "VoiceCarrier",
    "VoiceSession",
    "VoiceSessionMode",
    "as_voice_session_mode",
    "phone_session_key",
]
