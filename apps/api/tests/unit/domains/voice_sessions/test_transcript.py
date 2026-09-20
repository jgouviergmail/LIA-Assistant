"""The voice-only exchanges of a session, whichever carrier held the transcript.

The phone's vendor sends the whole conversation after the call — the person's
words, the agent's, and the tool calls between them (measured 2026-09-20:
``tool_calls[{tool_name, params_as_json}]`` on the agent's turn that called,
``tool_results`` on the turn that received). A delegated exchange is already
in the thread (the graph archived the turn), so the closing keeps only the
voice-only ones — the mirror of the browser skipping ``turn.delegated``.
"""

from __future__ import annotations

import pytest

from src.domains.voice_sessions.transcript import VoiceTranscript, VoiceTurn

pytestmark = pytest.mark.unit

_DELEGATION_TOOL = "send_to_lia"


def _payload(turns: list[object]) -> dict[str, object]:
    return {"type": "post_call_transcription", "data": {"transcript": turns}}


def test_a_vendor_payload_becomes_turns_with_their_offsets() -> None:
    payload = _payload(
        [
            {"role": "agent", "message": "Hello, am I speaking with Alex?", "time_in_call_secs": 0},
            {"role": "user", "message": "Yes, it's me.", "time_in_call_secs": 3},
            {"role": "agent", "message": "Great. What can I do?", "time_in_call_secs": 5},
        ]
    )
    transcript = VoiceTranscript.from_vendor_payload(payload, delegation_tool=_DELEGATION_TOOL)
    assert [t.role for t in transcript.turns] == ["assistant", "user", "assistant"]
    assert transcript.turns[1] == VoiceTurn(role="user", text="Yes, it's me.", offset_seconds=3)
    assert not any(t.delegated for t in transcript.turns)


def test_a_delegated_exchange_is_whole_as_the_vendor_really_writes_it() -> None:
    """Measured on the vendor's engine (2026-09-20): the call is a separate empty
    agent entry, its acknowledgement another, the small talk while LIA works
    follows, then a second pair and the restitution. The whole exchange —
    request to restitution — is the graph's; the next exchange is voice-only,
    exactly as the browser skips a buffer it flagged ``delegated``."""
    payload = _payload(
        [
            {"role": "agent", "message": "Hello, is this you?", "time_in_call_secs": 0},
            {"role": "user", "message": "Yes.", "time_in_call_secs": 2},
            {"role": "agent", "message": "What can I do for you?", "time_in_call_secs": 2},
            {"role": "user", "message": "What is on my agenda tomorrow?", "time_in_call_secs": 4},
            {"role": "agent", "message": "Let me check.", "time_in_call_secs": 4},
            {
                "role": "agent",
                "message": "",
                "time_in_call_secs": 4,
                "tool_calls": [{"tool_name": _DELEGATION_TOOL, "params_as_json": "{}"}],
            },
            {
                "role": "agent",
                "message": "",
                "time_in_call_secs": 4,
                "tool_results": [{"tool_name": _DELEGATION_TOOL, "result_value": "started"}],
            },
            {"role": "agent", "message": "Anything else while we wait?", "time_in_call_secs": 5},
            {
                "role": "agent",
                "message": "",
                "time_in_call_secs": 33,
                "tool_calls": [{"tool_name": _DELEGATION_TOOL, "params_as_json": "{}"}],
            },
            {
                "role": "agent",
                "message": "",
                "time_in_call_secs": 33,
                "tool_results": [{"tool_name": _DELEGATION_TOOL, "result_value": "..."}],
            },
            {"role": "agent", "message": "You have a meeting at three.", "time_in_call_secs": 34},
            {"role": "user", "message": "Perfect, bye.", "time_in_call_secs": 49},
            {"role": "agent", "message": "Goodbye.", "time_in_call_secs": 50},
        ]
    )
    transcript = VoiceTranscript.from_vendor_payload(payload, delegation_tool=_DELEGATION_TOOL)
    delegated = [t.text for t in transcript.turns if t.delegated]
    voice_only = [t.text for t in transcript.voice_only()]
    assert delegated == [
        "What is on my agenda tomorrow?",
        "Let me check.",
        "Anything else while we wait?",
        "You have a meeting at three.",
    ]
    assert voice_only == [
        "Hello, is this you?",
        "Yes.",
        "What can I do for you?",
        "Perfect, bye.",
        "Goodbye.",
    ]


def test_a_call_on_the_same_entry_as_the_announce_marks_the_exchange_too() -> None:
    """The simulate-conversation shape (lot 0): the call sits on the announcing turn."""
    payload = _payload(
        [
            {"role": "user", "message": "Remind me to call the bank.", "time_in_call_secs": 4},
            {
                "role": "agent",
                "message": "On it.",
                "time_in_call_secs": 5,
                "tool_calls": [{"tool_name": _DELEGATION_TOOL, "params_as_json": "{}"}],
            },
            {"role": "agent", "message": "Done, it is set.", "time_in_call_secs": 9},
            {"role": "user", "message": "Thanks.", "time_in_call_secs": 12},
        ]
    )
    transcript = VoiceTranscript.from_vendor_payload(payload, delegation_tool=_DELEGATION_TOOL)
    assert [t.delegated for t in transcript.turns] == [True, True, True, False]


def test_another_tool_does_not_mark_a_delegation() -> None:
    payload = _payload(
        [
            {
                "role": "agent",
                "message": "Goodbye.",
                "time_in_call_secs": 30,
                "tool_calls": [{"tool_name": "end_call", "params_as_json": "{}"}],
            },
        ]
    )
    transcript = VoiceTranscript.from_vendor_payload(payload, delegation_tool=_DELEGATION_TOOL)
    assert [t.delegated for t in transcript.turns] == [False]


def test_empty_and_malformed_turns_are_dropped() -> None:
    payload = _payload(
        [
            "not a turn",
            {"role": "agent", "message": "   ", "time_in_call_secs": 0},
            {"role": "user", "message": None},
            {"role": "system", "message": "words of nobody"},
            {"role": "user", "message": "Hi", "time_in_call_secs": "soon"},
            {"role": "user", "message": "There", "time_in_call_secs": True},
        ]
    )
    transcript = VoiceTranscript.from_vendor_payload(payload, delegation_tool=_DELEGATION_TOOL)
    assert transcript.turns == (
        VoiceTurn(role="user", text="Hi", offset_seconds=0),
        VoiceTurn(role="user", text="There", offset_seconds=0),
    )


def test_no_transcript_means_no_turns() -> None:
    assert VoiceTranscript.from_vendor_payload({}, delegation_tool=_DELEGATION_TOOL).turns == ()
    assert (
        VoiceTranscript.from_vendor_payload(
            {"data": {"transcript": "text"}}, delegation_tool=_DELEGATION_TOOL
        ).turns
        == ()
    )


def test_rows_from_a_record_become_turns() -> None:
    transcript = VoiceTranscript.from_rows([("user", "Hi"), ("assistant", "Hello"), ("user", " ")])
    assert [(t.role, t.text) for t in transcript.turns] == [("user", "Hi"), ("assistant", "Hello")]


def test_lines_speak_the_relay_prompt_s_vocabulary() -> None:
    """The prompt says `agent:` for the assistant; the thread says `assistant`."""
    transcript = VoiceTranscript.from_rows(
        [("user", "Remind me to call the bank"), ("assistant", "Noted.")]
    )
    assert transcript.lines() == ["user: Remind me to call the bank", "agent: Noted."]


def test_voice_only_turns_group_into_exchanges_opened_by_the_person() -> None:
    transcript = VoiceTranscript(
        turns=(
            VoiceTurn(role="assistant", text="Hello"),
            VoiceTurn(role="assistant", text="Anyone there?"),
            VoiceTurn(role="user", text="Yes"),
            VoiceTurn(role="assistant", text="Good"),
            VoiceTurn(role="user", text="Book it", delegated=True),
            VoiceTurn(role="assistant", text="Asking", delegated=True),
            VoiceTurn(role="user", text="Thanks"),
        )
    )
    exchanges = transcript.voice_only_exchanges()
    assert [[t.text for t in exchange] for exchange in exchanges] == [
        ["Hello", "Anyone there?"],
        ["Yes", "Good"],
        ["Thanks"],
    ]
    assert VoiceTranscript(turns=()).voice_only_exchanges() == ()
