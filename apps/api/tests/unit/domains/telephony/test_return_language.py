"""Post-call failures and unanswered calls keep the account's language and outcome."""

from __future__ import annotations

from asyncio import CancelledError
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_telephony import get_return_phrases
from src.domains.telephony import owner_call, return_synthesis
from src.domains.telephony.models import (
    CallKind,
    NotificationStatus,
    PhoneCall,
    PhoneCallOutcome,
    PhoneCallStatus,
)
from src.domains.telephony.payload import map_status
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import StructuredCallData
from src.domains.voice_sessions.session import VoiceSessionMode
from src.infrastructure.scheduler.phone_relay_runner import RelayOutcome, fallback_text

_LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")
_VENDOR_SUMMARY = "The agent reached an automated voicemail and left a message."


def _call(mode: VoiceSessionMode = "direct") -> PhoneCall:
    """Build a real mapped row without opening a database connection."""
    return PhoneCall(
        id=uuid4(),
        user_id=uuid4(),
        call_kind=CallKind.SELF,
        call_mode=mode,
        status=PhoneCallStatus.DIALING,
        objective="Catch up",
        callee_display="Test contact",
    )


@pytest.mark.unit
@pytest.mark.parametrize("language", _LANGUAGES)
@pytest.mark.parametrize("mode", ["direct", "delegated"])
@pytest.mark.parametrize("interruption", [RuntimeError, CancelledError])
@pytest.mark.parametrize(
    ("status", "phrase_key"),
    [
        (PhoneCallStatus.NO_ANSWER, "relay_unanswered"),
        (PhoneCallStatus.VOICEMAIL, "relay_unanswered"),
        (PhoneCallStatus.FAILED, "relay_call_failed"),
    ],
)
async def test_unanswered_return_is_correct_even_if_cleanup_crashes_before_settlement(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    mode: VoiceSessionMode,
    interruption: type[RuntimeError] | type[CancelledError],
    status: PhoneCallStatus,
    phrase_key: str,
) -> None:
    """The durable outbox must already say what happened before any later wait."""
    db = AsyncMock(spec=AsyncSession)
    repo = TelephonyRepository(db)
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(repo, "mark_completed", claim)
    monkeypatch.setattr(
        owner_call, "detach_live_tools", AsyncMock(side_effect=interruption("cleanup unavailable"))
    )
    synthesize = AsyncMock(side_effect=AssertionError("An unanswered call needs no model"))
    monkeypatch.setattr(owner_call, "synthesize_relay", synthesize)

    with pytest.raises(interruption, match="cleanup unavailable"):
        await owner_call.process_owner_call(
            db=db,
            repo=repo,
            call=_call(mode),
            payload={"data": {"analysis": {"transcript_summary": _VENDOR_SUMMARY}}},
            user=None,
            language=language,
            user_timezone="UTC",
            status=status,
            call_seconds=None,
        )

    assert claim.await_count == 1
    assert claim.await_args is not None
    stored = claim.await_args.kwargs
    expected = get_return_phrases(language)[phrase_key]
    assert stored["notification_content"] == expected
    assert stored["summary"] == expected
    assert stored["notification_status"] is NotificationStatus.RELAYING
    assert stored["outcome"] is PhoneCallOutcome.UNREACHABLE
    synthesize.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("language", _LANGUAGES)
async def test_owner_synthesis_failure_never_presents_vendor_prose_as_a_localized_summary(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """A failed translation/synthesis cannot forward English as the account's recap."""
    monkeypatch.setattr(
        owner_call, "synthesize_relay", AsyncMock(side_effect=TimeoutError("provider unavailable"))
    )
    relay, usage, synthesized = await owner_call._synthesize(
        call=_call(),
        payload={"data": {"analysis": {"transcript_summary": _VENDOR_SUMMARY}}},
        language=language,
        user_timezone="UTC",
    )
    assert synthesized is False and usage is None
    assert relay.owner_confirmed is False
    assert relay.relay_message == "" and relay.summary == ""
    assert (
        fallback_text(relay, RelayOutcome.FAILED, language)
        == get_return_phrases(language)["relay_failed"]
    )


@pytest.mark.unit
@pytest.mark.parametrize("language", _LANGUAGES)
async def test_third_party_synthesis_failure_uses_the_localized_refusal(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """The third-party return has the same language boundary as an owner call."""
    monkeypatch.setattr(
        return_synthesis,
        "synthesize_return",
        AsyncMock(side_effect=TimeoutError("provider unavailable")),
    )
    expected = get_return_phrases(language)["fallback"]
    proposal, usage = await return_synthesis._synthesize_with_fallback(
        call_id=uuid4(),
        transcript="An automated voicemail greeting.",
        transcript_summary=_VENDOR_SUMMARY,
        structured=StructuredCallData(),
        objective="Catch up",
        callee_display="Test contact",
        language=language,
        user_timezone="UTC",
        fallback_phrase=expected,
    )
    assert usage is None
    assert proposal.proposal_text == expected
    assert proposal.summary == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"metadata": {"phone_call": {"call_result": "voicemail"}}}, PhoneCallStatus.VOICEMAIL),
        (
            {
                "transcript": [
                    {
                        "role": "agent",
                        "tool_calls": [
                            {"tool_name": "voicemail_detection", "tool_has_been_called": True}
                        ],
                    }
                ]
            },
            PhoneCallStatus.VOICEMAIL,
        ),
        (
            {
                "transcript": [
                    {
                        "role": "agent",
                        "tool_calls": [
                            {"tool_name": "voicemail_detection", "tool_has_been_called": False}
                        ],
                    }
                ]
            },
            PhoneCallStatus.COMPLETED,
        ),
        (
            {"analysis": {"transcript_summary": _VENDOR_SUMMARY}},
            PhoneCallStatus.COMPLETED,
        ),
        (
            {"transcript": [None, {"role": "agent", "tool_calls": [None]}]},
            PhoneCallStatus.COMPLETED,
        ),
    ],
)
def test_voicemail_status_uses_vendor_facts_and_never_guesses_from_prose(
    data: dict[str, object], expected: PhoneCallStatus
) -> None:
    """Both explicit provider signals survive a generic completed-call status."""
    assert map_status({"data": {"status": "done", **data}}) is expected
