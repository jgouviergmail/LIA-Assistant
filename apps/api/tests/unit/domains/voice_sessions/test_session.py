"""A voice session is one value, two carriers, two modes (ADR-301).

The browser session and the phone call share nothing in storage (a Redis
record, a durable ``phone_calls`` row) and everything in behaviour: the
delegated turns, the voice-only rows, the closing card, the decision, the
learning. What they share travels as this value; where it is filed is ONE
key, written in the same metadata field by both carriers so the summary
queries need no second reader.
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.telephony.spend import phone_call_run_id
from src.domains.voice_sessions.session import (
    VoiceCarrier,
    VoiceSession,
    VoiceSessionMode,
    phone_session_key,
)

pytestmark = pytest.mark.unit


def test_the_phone_key_is_the_call_s_run_id() -> None:
    """One id for everything a call costs and files: the run id ADR-290 minted."""
    call_id = uuid.uuid4()
    assert phone_session_key(call_id) == phone_call_run_id(call_id)


def test_a_browser_session_files_under_its_own_id() -> None:
    session = VoiceSession.browser(
        session_id="s" * 32,
        run_id="live_session_" + "s" * 32,
        mode="delegated",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="fr",
        timezone="Europe/Paris",
    )
    assert session.carrier == VoiceCarrier.BROWSER
    assert session.key == "s" * 32
    assert session.origin_kind == "live_session"


def test_a_phone_session_files_under_the_call_key_and_names_its_origin() -> None:
    call_id = uuid.uuid4()
    session = VoiceSession.phone(
        call_id=call_id,
        mode="direct",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="en",
        timezone="UTC",
    )
    assert session.carrier == VoiceCarrier.PHONE
    assert session.key == phone_call_run_id(call_id)
    assert session.run_id == phone_call_run_id(call_id)
    assert session.origin_kind == "phone_call"
    assert session.origin_id == str(call_id)


def test_the_mode_vocabulary_is_closed() -> None:
    assert set(VoiceSessionMode.__args__) == {"delegated", "direct"}  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        VoiceSession.browser(
            session_id="x",
            run_id="r",
            mode="hybrid",  # type: ignore[arg-type]
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            language="fr",
            timezone="UTC",
        )
