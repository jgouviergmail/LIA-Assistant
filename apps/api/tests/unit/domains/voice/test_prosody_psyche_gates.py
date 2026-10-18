"""A switched-off psyche never bends the voice (ADR-237).

The mood read used to fetch — and CREATE — the psyche state without asking
whether the person had the psyche on: a person who switched it off still heard
the direct readout follow a mood frozen when they did, and one who switched it
off before any state existed was given a state row by their first direct
readout. The psyche is on by default; the read is reached from the direct
readout alone (``stream_direct_tts``) — the spoken comment never bends prosody.
The read now asks the two gates the psyche's own prompt block asks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.voice.factory import TTSConfig
from src.domains.voice.service import VoiceCommentService

pytestmark = pytest.mark.unit

BASE_SETTINGS = {"stability": 0.5, "style": 0.3}
EXCITED = SimpleNamespace(mood_pleasure=0.6, mood_arousal=0.9)


def _flags(*, psyche: bool = True) -> SimpleNamespace:
    return SimpleNamespace(voice_psyche_prosody_enabled=True, psyche_enabled=psyche)


def _session(psyche_enabled: bool | None) -> MagicMock:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=psyche_enabled)
    return db


def _opens(db: MagicMock) -> MagicMock:
    @asynccontextmanager
    async def _context() -> AsyncIterator[MagicMock]:
        yield db

    return MagicMock(side_effect=_context)


async def _resolve(
    *, flags: SimpleNamespace, opens: MagicMock, state_read: AsyncMock
) -> dict[str, Any] | None:
    service = VoiceCommentService(tts_client=MagicMock(), user_id=str(uuid4()))
    with (
        patch("src.domains.voice.service.settings", flags),
        patch("src.infrastructure.database.session.get_db_context", opens),
        patch("src.domains.psyche.service.PsycheService.get_or_create_state", state_read),
    ):
        return await service._resolve_prosody_settings(
            TTSConfig(
                provider="elevenlabs",
                model="eleven_multilingual_v2",
                voice_male="male",
                voice_female="female",
                voice_settings=dict(BASE_SETTINGS),
            )
        )


async def test_a_person_with_the_psyche_off_hears_no_mood_and_gets_no_state() -> None:
    state_read = AsyncMock(return_value=EXCITED)
    result = await _resolve(flags=_flags(), opens=_opens(_session(False)), state_read=state_read)

    assert result is None
    state_read.assert_not_awaited()


async def test_a_deployment_without_the_psyche_never_opens_a_session() -> None:
    opens = _opens(_session(True))
    state_read = AsyncMock(return_value=EXCITED)
    result = await _resolve(flags=_flags(psyche=False), opens=opens, state_read=state_read)

    assert result is None
    opens.assert_not_called()
    state_read.assert_not_awaited()


async def test_a_person_with_the_psyche_on_hears_the_mood() -> None:
    state_read = AsyncMock(return_value=EXCITED)
    result = await _resolve(flags=_flags(), opens=_opens(_session(True)), state_read=state_read)

    state_read.assert_awaited_once()
    assert result is not None
    assert result["stability"] < BASE_SETTINGS["stability"]
    assert result["style"] > BASE_SETTINGS["style"]
