"""Reading the post-call webhook payload — one implementation for both mandates.

The third-party return and the owner relay read the same vendor payload: the
duration, the vendor summary, the terminal status, the transcript turns, and
the clock line the synthesis resolves relative dates against. Written once,
here, in a leaf module neither path imports the other through.

spike (P2.0): confirm the field paths against a real ElevenLabs account. All
reads are defensive — a shape drift degrades to a graceful fallback, never a
crash.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from zoneinfo import ZoneInfo

from src.domains.telephony.models import PhoneCallStatus
from src.domains.voice.expressive_cues import strip_transcript_cues


def nested(payload: dict[str, Any], *path: str) -> Any:
    """Walk a dotted path through nested dicts, returning None if any hop misses."""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_call_seconds(payload: dict[str, Any]) -> Decimal | None:
    raw = nested(payload, "data", "metadata", "call_duration_secs")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation, ValueError:
        return None


def extract_transcript_summary(payload: dict[str, Any]) -> str:
    value = nested(payload, "data", "analysis", "transcript_summary")
    return value if isinstance(value, str) else ""


def extract_transcript_text(payload: dict[str, Any], limit: int = 4000) -> str:
    """Join the transcript turns to plain text for synthesis (never persisted)."""
    turns = nested(payload, "data", "transcript")
    if not isinstance(turns, list):
        return ""
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        message = turn.get("message") or turn.get("text") or ""
        if isinstance(message, str) and turn.get("role") == "agent":
            # The audio tags the agent's engine performed are no words of the call (ADR-373).
            message = strip_transcript_cues(message)[0]
        if message:
            lines.append(f"{turn.get('role', '')}: {message}".strip())
    return "\n".join(lines)[:limit]


def _voicemail_tool_called(payload: dict[str, object]) -> bool:
    """Read an executed voicemail tool from the provider's transcript.

    Args:
        payload: The post-call webhook payload.

    Returns:
        Whether an agent actually called the voicemail detection system tool.
    """
    for turn in _turns(payload):
        if turn.get("role") != "agent":
            continue
        tool_calls = turn.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        if any(
            isinstance(call, dict)
            and call.get("tool_name") == "voicemail_detection"
            and call.get("tool_has_been_called") is True
            for call in tool_calls
        ):
            return True
    return False


def _turns(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The transcript's turns that are objects, in order (anything else is skipped)."""
    turns = nested(payload, "data", "transcript")
    if not isinstance(turns, list):
        return []
    return [turn for turn in turns if isinstance(turn, dict)]


def _result_body(result: dict[str, Any]) -> dict[str, Any] | None:
    """A tool result's body: its object, else its JSON text read back, else None."""
    body = result.get("result")
    if isinstance(body, dict):
        return body
    text = result.get("result_value")
    if not isinstance(text, str):
        return None
    try:
        decoded = json.loads(text)
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


def voicemail_message_left(payload: dict[str, Any]) -> bool | None:
    """Whether the provider left the voicemail message, read from the tool's RESULT.

    The voicemail tool's result names the message the provider played (its
    portal's message, its dynamic variables filled). Only the result is read:
    a call of the tool says it was asked for, never that something was left.

    Args:
        payload: The post-call webhook payload.

    Returns:
        True when the result is a success carrying a message; False when the
        tool failed or had no message to play; None when the transcript holds
        no readable result of that tool.
    """
    for turn in _turns(payload):
        results = turn.get("tool_results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict) or result.get("tool_name") != "voicemail_detection":
                continue
            body = _result_body(result)
            if body is None:
                continue
            message = body.get("voicemail_message")
            played = isinstance(message, str) and bool(message.strip())
            return played and result.get("is_error") is not True and body.get("status") != "error"
    return None


def callee_spoke(payload: dict[str, Any]) -> bool:
    """Whether anything at all was heard from the other side of the line.

    A voicemail greeting counts: it is the callee's line speaking.

    Args:
        payload: The post-call webhook payload.

    Returns:
        True when at least one turn of the callee's side carries words.
    """
    for turn in _turns(payload):
        message = turn.get("message")
        if turn.get("role") == "user" and isinstance(message, str) and message.strip():
            return True
    return False


def map_status(payload: dict[str, Any]) -> PhoneCallStatus:
    """Map provider status and executed tools to a terminal call status."""
    status = str(nested(payload, "data", "status") or "").lower()
    reason = str(nested(payload, "data", "metadata", "termination_reason") or "").lower()
    call_result = nested(payload, "data", "metadata", "phone_call", "call_result")
    if (
        call_result == "voicemail"
        or _voicemail_tool_called(payload)
        or "voicemail" in status
        or "voicemail" in reason
    ):
        return PhoneCallStatus.VOICEMAIL
    if "no_answer" in reason or "no-answer" in reason or "unanswered" in reason:
        return PhoneCallStatus.NO_ANSWER
    if status in ("failed", "error") or "failed" in reason:
        return PhoneCallStatus.FAILED
    # A post-call transcription webhook implies the call connected.
    return PhoneCallStatus.COMPLETED


# Deterministic English weekday — `%A` depends on the C locale (a documented
# trap). The model reasons in English on the ISO date, then writes its output in
# the user's language.
_EN_WEEKDAYS: Final = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def current_datetime_line(user_timezone: str) -> str:
    """A 'now' the synthesis resolves relative dates against ('this weekend')."""
    now = datetime.now(ZoneInfo(user_timezone))
    return (
        f"CURRENT DATE AND TIME: {now.strftime('%Y-%m-%d %H:%M')} "
        f"({_EN_WEEKDAYS[now.weekday()]}), timezone {user_timezone}. Resolve every "
        "relative reference (today, this weekend, tomorrow) to an ABSOLUTE "
        "weekday + date against this."
    )


__all__ = [
    "callee_spoke",
    "current_datetime_line",
    "extract_call_seconds",
    "extract_transcript_summary",
    "extract_transcript_text",
    "map_status",
    "nested",
    "voicemail_message_left",
]
