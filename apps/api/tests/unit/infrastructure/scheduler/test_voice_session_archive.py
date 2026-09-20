"""The phone's transcript is archived at the closing as the browser's rows are (ADR-301).

The browser archives one EXCHANGE at a time: the person's words and the
voice's answer, two rows sharing the ``started_at`` the client measured, so
the closing card counts exchanges as distinct stamps (ADR-185). The phone
holds nothing until the vendor's payload; its voice-only turns are grouped
the same way here — an exchange opens on the person's turn and holds the
voice's turns that follow — so the same aggregate reads both carriers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.voice_sessions.session import VoiceSession
from src.domains.voice_sessions.transcript import VoiceTranscript, VoiceTurn
from src.infrastructure.scheduler.voice_session_closing import (
    archive_voice_turns,
    close_voice_session,
)

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.scheduler.voice_session_closing"
STARTED = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def _session() -> VoiceSession:
    return VoiceSession.phone(
        call_id=uuid.uuid4(),
        mode="delegated",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="fr",
        timezone="Europe/Paris",
    )


async def test_turns_are_grouped_into_exchanges_that_share_one_stamp() -> None:
    transcript = VoiceTranscript(
        turns=(
            VoiceTurn(role="assistant", text="Hello", offset_seconds=0),
            VoiceTurn(role="user", text="Hi there", offset_seconds=3),
            VoiceTurn(role="assistant", text="How are you?", offset_seconds=5),
            VoiceTurn(role="user", text="Remind me", offset_seconds=9, delegated=True),
            VoiceTurn(role="assistant", text="Sure, asking", offset_seconds=10, delegated=True),
            VoiceTurn(role="user", text="Thanks", offset_seconds=20),
            VoiceTurn(role="assistant", text="Welcome", offset_seconds=21),
            VoiceTurn(role="assistant", text="Anything else?", offset_seconds=22),
        )
    )
    with patch(f"{MODULE}.archive_row", AsyncMock()) as archive:
        archived = await archive_voice_turns(
            AsyncMock(), session=_session(), transcript=transcript, started_at=STARTED
        )

    assert archived == 6  # the delegated exchange is the graph's, not archived here
    stamps = [call.kwargs["metadata"]["started_at"] for call in archive.call_args_list]
    roles = [call.kwargs["role"] for call in archive.call_args_list]
    assert roles == ["assistant", "user", "assistant", "user", "assistant", "assistant"]
    # Three exchanges: the greeting alone, then two opened by the person.
    assert len(set(stamps)) == 3
    assert stamps[1] == stamps[2] and stamps[3] == stamps[4] == stamps[5]
    assert stamps[1] == (STARTED.replace(second=3, microsecond=1)).isoformat()
    # An exchange ends when its last turn was said.
    ended = [call.kwargs["metadata"]["ended_at"] for call in archive.call_args_list]
    assert ended[3] == ended[5] == (STARTED.replace(second=22, microsecond=2)).isoformat()


async def test_two_exchanges_at_the_same_second_keep_distinct_stamps() -> None:
    """The vendor counts whole seconds; the greeting and the answer both fall at 0."""
    transcript = VoiceTranscript(
        turns=(
            VoiceTurn(role="assistant", text="Hello, is this you?", offset_seconds=0),
            VoiceTurn(role="user", text="Yes.", offset_seconds=0),
            VoiceTurn(role="assistant", text="What can I do?", offset_seconds=0),
        )
    )
    with patch(f"{MODULE}.archive_row", AsyncMock()) as archive:
        await archive_voice_turns(
            AsyncMock(), session=_session(), transcript=transcript, started_at=STARTED
        )
    stamps = [call.kwargs["metadata"]["started_at"] for call in archive.call_args_list]
    assert len(set(stamps)) == 2
    assert stamps[0] < stamps[1] == stamps[2]


async def test_a_transcript_needs_the_instant_the_session_started() -> None:
    with pytest.raises(ValueError, match="started_at"):
        await close_voice_session(
            AsyncMock(),
            session=_session(),
            memory_enabled=True,
            outcome="ended",
            duration_seconds=10,
            transcript=VoiceTranscript(turns=(VoiceTurn(role="user", text="x"),)),
        )
