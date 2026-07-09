"""Unit tests for AgentService._should_start_voice (ADR-117 Lot 2).

Voice synthesis is a pure per-character cost: with a detached run and no
subscriber, it must be skipped. Probe=None (legacy/scheduled/channels)
keeps the historical behavior; probe errors fail OPEN (a Redis hiccup must
never mute a listening user).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.domains.agents.api.service import AgentService


def _user(voice_enabled: bool = True) -> MagicMock:
    user = MagicMock()
    user.voice_enabled = voice_enabled
    return user


@pytest.mark.unit
class TestShouldStartVoice:
    async def test_no_user_is_false(self):
        assert await AgentService._should_start_voice(None, None, "r", "sync_fallback") is False

    async def test_voice_disabled_is_false(self):
        assert (
            await AgentService._should_start_voice(
                _user(voice_enabled=False), None, "r", "sync_fallback"
            )
            is False
        )

    async def test_no_probe_keeps_legacy_behavior(self):
        # Legacy inline SSE / scheduled actions / channels: no presence
        # tracking — voice starts exactly as before.
        assert await AgentService._should_start_voice(_user(), None, "r", "agent_parallel") is True

    async def test_probe_true_starts_voice(self):
        async def probe() -> bool:
            return True

        assert (
            await AgentService._should_start_voice(_user(), probe, "r", "chat_progressive") is True
        )

    async def test_probe_false_skips_voice(self):
        async def probe() -> bool:
            return False

        assert (
            await AgentService._should_start_voice(_user(), probe, "r", "chat_progressive") is False
        )

    async def test_probe_error_fails_open(self):
        async def probe() -> bool:
            raise RuntimeError("redis down")

        assert await AgentService._should_start_voice(_user(), probe, "r", "sync_fallback") is True
