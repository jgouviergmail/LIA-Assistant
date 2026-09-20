"""Unit tests for the voice-start gate ``_should_start_voice`` (ADR-117 Lot 2).

Voice synthesis is a pure per-character cost: with a detached run and no
subscriber, it must be skipped. Probe=None (legacy/scheduled/channels)
keeps the historical behavior; probe errors fail OPEN (a Redis hiccup must
never mute a listening user).

The gate lives in the voice_stream_helpers module since the B2 voice
extraction (ADR-122) — formerly ``AgentService._should_start_voice``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.streaming.voice_stream_helpers import (
    _should_start_voice,
    voice_listens,
    voice_preference_of,
)


def _user(voice_enabled: bool = True) -> MagicMock:
    user = MagicMock()
    user.voice_enabled = voice_enabled
    return user


@pytest.mark.unit
class TestVoicePreferenceOf:
    """ONE reading of the preference, shared by the voice start points and the
    response node's HTML gate (through the runtime context): they cannot
    disagree on whether a voice listens."""

    def test_no_profile_is_false(self):
        assert voice_preference_of(None) is False

    def test_reads_the_profile_flag(self):
        assert voice_preference_of(_user(voice_enabled=True)) is True
        assert voice_preference_of(_user(voice_enabled=False)) is False


@pytest.mark.unit
class TestVoiceListens:
    """A turn a live session delegated is spoken by the session's own voice
    (ADR-299): no comment, whatever the account's preference — the TTS was
    platform spend for a sound nobody heard (wave 2 spec A2)."""

    def test_the_preference_alone_decides_off_a_live_session(self):
        assert voice_listens(_user(True), live_session_id=None) is True
        assert voice_listens(_user(False), live_session_id=None) is False

    def test_a_live_session_silences_the_comment(self):
        assert voice_listens(_user(True), live_session_id="a" * 32) is False

    async def test_no_voice_start_point_speaks_over_a_live_session(self):
        async def probe() -> bool:
            return True

        assert (
            await _should_start_voice(
                _user(), probe, "r", "chat_progressive", live_session_id="a" * 32
            )
            is False
        )


@pytest.mark.unit
class TestShouldStartVoice:
    async def test_no_user_is_false(self):
        assert await _should_start_voice(None, None, "r", "sync_fallback") is False

    async def test_voice_disabled_is_false(self):
        assert (
            await _should_start_voice(_user(voice_enabled=False), None, "r", "sync_fallback")
            is False
        )

    async def test_no_probe_keeps_legacy_behavior(self):
        # Legacy inline SSE / scheduled actions / channels: no presence
        # tracking — voice starts exactly as before.
        assert await _should_start_voice(_user(), None, "r", "agent_parallel") is True

    async def test_probe_true_starts_voice(self):
        async def probe() -> bool:
            return True

        assert await _should_start_voice(_user(), probe, "r", "chat_progressive") is True

    async def test_probe_false_skips_voice(self):
        async def probe() -> bool:
            return False

        assert await _should_start_voice(_user(), probe, "r", "chat_progressive") is False

    async def test_probe_error_fails_open(self):
        async def probe() -> bool:
            raise RuntimeError("redis down")

        assert await _should_start_voice(_user(), probe, "r", "sync_fallback") is True
