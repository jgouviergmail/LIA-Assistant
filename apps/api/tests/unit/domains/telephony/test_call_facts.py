"""What the provider recorded about a call that reached nobody to talk to.

Production 2026-11-14: two third-party calls reached a voicemail; the provider
recorded it explicitly (``call_result: voicemail``, the voicemail tool's result
carrying the message it played), yet the person read « I placed your call but
could not produce a detailed summary ». These facts are now read by the code,
handed to the synthesis as authoritative, and spoken by the return itself when
the synthesis fails or when nobody was heard on the line.

The payloads below keep the vendor's real shape (measured on the production
account's conversations), every personal value replaced.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.core.i18n_telephony import get_return_phrases
from src.domains.telephony.call_facts import (
    CallFacts,
    VoicemailMessage,
    read_call_facts,
    unreachable_notice,
)
from src.domains.telephony.models import PhoneCallStatus
from src.domains.telephony.payload import callee_spoke, voicemail_message_left

pytestmark = pytest.mark.unit

_LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")


def _tool_result(message: str | None, *, as_text: bool = False, error: bool = False) -> dict:
    body: dict[str, Any] = {
        "result_type": "voicemail_detection_success",
        "status": "success",
        "reason": "Automated greeting asking to leave a message after the beep",
    }
    if message is not None:
        body["voicemail_message"] = message
    result: dict[str, Any] = {
        "request_id": "voicemail_detection_1",
        "tool_name": "voicemail_detection",
        "tool_id": "__system_voicemail_detection",
        "is_error": error,
        "type": "system",
    }
    if as_text:
        result["result_value"] = json.dumps(body)
    else:
        result["result_value"] = json.dumps(body)
        result["result"] = body
    return result


def _voicemail_payload(*results: dict) -> dict:
    """The measured order: greeting, the voicemail greeting, the call, then its result."""
    return {
        "data": {
            "status": "done",
            "metadata": {
                "phone_call": {"call_result": "voicemail"},
                "termination_reason": "voicemail_detection tool was called.",
            },
            "transcript": [
                {"role": "agent", "message": "Hello, this is the assistant.", "tool_results": []},
                {"role": "user", "message": "Please leave a message after the tone."},
                {
                    "role": "agent",
                    "tool_calls": [
                        {"tool_name": "voicemail_detection", "tool_has_been_called": True}
                    ],
                    "tool_results": [],
                },
                {"role": "agent", "tool_calls": [], "tool_results": list(results)},
            ],
        }
    }


# ----------------------------------------------------------- voicemail_message_left


def test_a_played_message_is_a_message_left() -> None:
    assert voicemail_message_left(_voicemail_payload(_tool_result("Please call back."))) is True


def test_the_result_is_also_read_from_its_text_form() -> None:
    payload = _voicemail_payload(_tool_result("Please call back.", as_text=True))
    assert voicemail_message_left(payload) is True


@pytest.mark.parametrize("message", ["", "   ", None])
def test_a_voicemail_with_no_message_to_play_left_none(message: str | None) -> None:
    assert voicemail_message_left(_voicemail_payload(_tool_result(message))) is False


def test_a_failed_tool_left_no_message() -> None:
    payload = _voicemail_payload(_tool_result("Please call back.", error=True))
    assert voicemail_message_left(payload) is False


def test_no_result_of_the_tool_says_nothing_either_way() -> None:
    assert voicemail_message_left(_voicemail_payload()) is None
    assert voicemail_message_left({"data": {"transcript": [None, {"role": "agent"}]}}) is None
    assert voicemail_message_left({}) is None


def test_an_unreadable_text_result_says_nothing() -> None:
    result = {"tool_name": "voicemail_detection", "result_value": "not json"}
    assert voicemail_message_left(_voicemail_payload(result)) is None


# -------------------------------------------------------------------- callee_spoke


def test_a_line_where_the_other_side_said_something() -> None:
    assert callee_spoke(_voicemail_payload()) is True


@pytest.mark.parametrize(
    "transcript",
    [
        [],
        [{"role": "agent", "message": "Hello?"}],
        [{"role": "user", "message": "   "}, {"role": "user", "message": None}],
        [None, "noise", {"role": "user"}],
    ],
)
def test_a_line_where_nobody_answered_the_agent(transcript: list[Any]) -> None:
    assert callee_spoke({"data": {"transcript": transcript}}) is False


def test_a_payload_without_a_transcript_heard_nobody() -> None:
    assert callee_spoke({"data": {}}) is False


# ------------------------------------------------------------------ read_call_facts


def test_the_facts_of_a_voicemail_where_the_message_was_left() -> None:
    facts = read_call_facts(_voicemail_payload(_tool_result("Please call back.")))
    assert facts == CallFacts(
        status=PhoneCallStatus.VOICEMAIL, voicemail=VoicemailMessage.LEFT, callee_spoke=True
    )


def test_the_voicemail_fact_is_only_read_for_a_voicemail() -> None:
    answered = {"data": {"status": "done", "transcript": [{"role": "user", "message": "Hi"}]}}
    facts = read_call_facts(answered)
    assert facts.status is PhoneCallStatus.COMPLETED
    assert facts.voicemail is VoicemailMessage.NOT_APPLICABLE


def test_the_context_line_states_what_the_provider_recorded() -> None:
    left = read_call_facts(_voicemail_payload(_tool_result("Please call back.")))
    assert left.context_line() == "CALL FACTS: status=voicemail; voicemail_message_left=yes"
    unknown = read_call_facts(_voicemail_payload())
    assert unknown.context_line() == "CALL FACTS: status=voicemail; voicemail_message_left=unknown"
    answered = read_call_facts({"data": {"status": "done"}})
    assert answered.context_line() == "CALL FACTS: status=completed"


# --------------------------------------------------------------- unreachable_notice


@pytest.mark.parametrize("language", _LANGUAGES)
@pytest.mark.parametrize(
    ("status", "voicemail", "key"),
    [
        (PhoneCallStatus.VOICEMAIL, VoicemailMessage.LEFT, "voicemail_left"),
        (PhoneCallStatus.VOICEMAIL, VoicemailMessage.NOT_LEFT, "voicemail_not_left"),
        (PhoneCallStatus.VOICEMAIL, VoicemailMessage.UNKNOWN, "voicemail_unknown"),
        (PhoneCallStatus.NO_ANSWER, VoicemailMessage.NOT_APPLICABLE, "no_answer"),
        (PhoneCallStatus.FAILED, VoicemailMessage.NOT_APPLICABLE, "line_failed"),
    ],
)
def test_an_unreachable_call_is_told_what_happened(
    language: str, status: PhoneCallStatus, voicemail: VoicemailMessage, key: str
) -> None:
    facts = CallFacts(status=status, voicemail=voicemail, callee_spoke=False)
    notice = unreachable_notice(facts, callee="Test contact", language=language)
    assert notice == get_return_phrases(language)[key].format(callee="Test contact")
    assert "Test contact" in notice


@pytest.mark.parametrize("language", _LANGUAGES)
def test_a_connected_call_has_no_unreachable_notice(language: str) -> None:
    facts = CallFacts(
        status=PhoneCallStatus.COMPLETED,
        voicemail=VoicemailMessage.NOT_APPLICABLE,
        callee_spoke=True,
    )
    assert unreachable_notice(facts, callee="Test contact", language=language) is None


@pytest.mark.parametrize("language", _LANGUAGES)
def test_the_notices_never_reuse_the_vague_refusal(language: str) -> None:
    """Each outcome has its own sentence; none is the « no detailed summary » refusal."""
    phrases = get_return_phrases(language)
    keys = ("voicemail_left", "voicemail_not_left", "voicemail_unknown", "no_answer", "line_failed")
    sentences = {phrases[key] for key in keys}
    assert len(sentences) == len(keys)
    assert phrases["fallback"] not in sentences
