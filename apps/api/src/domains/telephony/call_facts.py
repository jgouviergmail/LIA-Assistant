"""What the provider recorded about a third-party call, read once and said plainly.

Production 2026-11-14: two calls reached a voicemail. The provider recorded
it in so many words (``call_result: voicemail``, the voicemail tool's result
carrying the message it played), yet the return synthesis was never told, and
when it failed the person read « I placed your call but could not produce a
detailed summary ». The facts are now read by the code, from ONE reading of
the payload (``payload.py``):

- the synthesis receives them as authoritative (``CallFacts.context_line``):
  whether a message was left is a fact to state, never a guess from prose;
- a call nobody answered is told what happened (``unreachable_notice``),
  in the account's language, when the synthesis fails and when nothing was
  heard on the line at all — then no model is asked anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from src.core.i18n_telephony import get_return_phrases
from src.domains.telephony.models import PhoneCallStatus
from src.domains.telephony.payload import callee_spoke, map_status, voicemail_message_left


class VoicemailMessage(StrEnum):
    """Whether the provider left its voicemail message, as its tool result says."""

    LEFT = "yes"
    NOT_LEFT = "no"
    UNKNOWN = "unknown"
    #: The call did not reach a voicemail: the question does not arise.
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class CallFacts:
    """The provider's own record of a call, read by the code.

    Attributes:
        status: The terminal status (``payload.map_status``).
        voicemail: Whether the voicemail message was left (voicemail only).
        callee_spoke: Whether anything was heard from the other side.
    """

    status: PhoneCallStatus
    voicemail: VoicemailMessage
    callee_spoke: bool

    def context_line(self) -> str:
        """The facts, for the synthesis model to state and never contradict."""
        line = f"CALL FACTS: status={self.status.value}"
        if self.status is PhoneCallStatus.VOICEMAIL:
            line += f"; voicemail_message_left={self.voicemail.value}"
        return line


def _voicemail_of(payload: dict[str, Any]) -> VoicemailMessage:
    left = voicemail_message_left(payload)
    if left is None:
        return VoicemailMessage.UNKNOWN
    return VoicemailMessage.LEFT if left else VoicemailMessage.NOT_LEFT


def read_call_facts(payload: dict[str, Any]) -> CallFacts:
    """Read what the provider recorded about the call.

    Args:
        payload: The post-call webhook payload.

    Returns:
        The call's facts.
    """
    status = map_status(payload)
    return CallFacts(
        status=status,
        voicemail=(
            _voicemail_of(payload)
            if status is PhoneCallStatus.VOICEMAIL
            else VoicemailMessage.NOT_APPLICABLE
        ),
        callee_spoke=callee_spoke(payload),
    )


#: The sentence a voicemail return says, by what the tool result recorded.
_VOICEMAIL_PHRASE_KEYS: Final[dict[VoicemailMessage, str]] = {
    VoicemailMessage.LEFT: "voicemail_left",
    VoicemailMessage.NOT_LEFT: "voicemail_not_left",
    VoicemailMessage.UNKNOWN: "voicemail_unknown",
    VoicemailMessage.NOT_APPLICABLE: "voicemail_unknown",
}

#: The sentence of the other calls nobody answered.
_UNREACHABLE_PHRASE_KEYS: Final[dict[PhoneCallStatus, str]] = {
    PhoneCallStatus.NO_ANSWER: "no_answer",
    PhoneCallStatus.FAILED: "line_failed",
}


def unreachable_notice(facts: CallFacts, *, callee: str, language: str) -> str | None:
    """What the person is told when the call reached nobody to talk to.

    Args:
        facts: The call's facts.
        callee: How the call names the callee (``phone_calls.callee_display``).
        language: The account's backend-canonical language.

    Returns:
        The localized sentence, or None for a call that connected (its
        failure keeps the generic refusal: something was said, and only a
        synthesis could tell it).
    """
    if facts.status is PhoneCallStatus.VOICEMAIL:
        key = _VOICEMAIL_PHRASE_KEYS[facts.voicemail]
    elif facts.status in _UNREACHABLE_PHRASE_KEYS:
        key = _UNREACHABLE_PHRASE_KEYS[facts.status]
    else:
        return None
    return get_return_phrases(language)[key].format(callee=callee)


__all__ = ["CallFacts", "VoicemailMessage", "read_call_facts", "unreachable_notice"]
