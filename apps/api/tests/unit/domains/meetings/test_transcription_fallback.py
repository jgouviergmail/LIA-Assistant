"""The engine chain is walked at processing time (ADR-258).

Measured 2026-09-03 on the dev instance: the stored ElevenLabs key is a key ID,
the provider refuses it, and without this walk every meeting dead-lettered
while an OpenAI key sat one step further down the chain.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from src.domains.meetings import transcription
from src.domains.meetings.engine import ResolvedEngine
from src.domains.meetings.models import MeetingSttEnginePreference, MeetingSttProvider
from src.domains.meetings.transcription import (
    TranscriptionError,
    TranscriptionOutcome,
    transcribe_with_fallback,
)

pytestmark = pytest.mark.unit


def _engine(provider: MeetingSttProvider) -> ResolvedEngine:
    return ResolvedEngine(
        provider=provider,
        model=None if provider is MeetingSttProvider.LOCAL else f"{provider.value}-model",
        diarized=provider is not MeetingSttProvider.LOCAL,
        api_key=None if provider is MeetingSttProvider.LOCAL else "key",
        cost_per_hour_eur=None,
        local_rtf_estimate=1.5 if provider is MeetingSttProvider.LOCAL else None,
    )


def _outcome(provider: MeetingSttProvider) -> TranscriptionOutcome:
    return TranscriptionOutcome(
        turns=[],
        language_code=None,
        audio_duration_seconds=1.0,
        provider=provider,
        model=None,
        diarized=False,
        cost_usd=0.0,
        cost_eur=0.0,
    )


async def _noop() -> None:
    return None


@pytest.fixture
def chain(monkeypatch: pytest.MonkeyPatch):
    """A scripted chain: which engine each exclusion set resolves to, and what each does."""
    state: dict[str, Any] = {"order": [], "behaviour": {}, "resolved": []}

    def _resolve(preference, *, exclude=frozenset()):
        for provider in state["order"]:
            if provider not in exclude:
                state["resolved"].append(provider)
                return _engine(provider)
        return None

    async def _transcribe(engine, **kwargs):
        behaviour = state["behaviour"][engine.provider]
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    monkeypatch.setattr(transcription, "resolve_engine", _resolve)
    monkeypatch.setattr(transcription, "transcribe_meeting", _transcribe)
    return state


def _call(preference=MeetingSttEnginePreference.AUTO):
    return transcribe_with_fallback(
        preference,
        audio_path=Path("/tmp/a.webm"),
        mime_type="audio/webm",
        duration_seconds=10.0,
        language_hint=None,
        user_id=uuid.uuid4(),
        heartbeat=_noop,
    )


async def test_a_refused_key_hands_over_to_the_next_engine(chain: dict[str, Any]) -> None:
    chain["order"] = [
        MeetingSttProvider.ELEVENLABS,
        MeetingSttProvider.OPENAI,
        MeetingSttProvider.LOCAL,
    ]
    chain["behaviour"] = {
        MeetingSttProvider.ELEVENLABS: TranscriptionError(
            "invalid_api_key", "refused", transient=False
        ),
        MeetingSttProvider.OPENAI: _outcome(MeetingSttProvider.OPENAI),
    }
    outcome = await _call()
    assert outcome.provider is MeetingSttProvider.OPENAI
    assert chain["resolved"] == [MeetingSttProvider.ELEVENLABS, MeetingSttProvider.OPENAI]


async def test_a_transient_fault_is_raised_at_once_for_the_retry_budget(
    chain: dict[str, Any],
) -> None:
    chain["order"] = [MeetingSttProvider.ELEVENLABS, MeetingSttProvider.OPENAI]
    chain["behaviour"] = {
        MeetingSttProvider.ELEVENLABS: TranscriptionError(
            "provider_rate_limited", "429", transient=True
        ),
    }
    with pytest.raises(TranscriptionError) as exc:
        await _call()
    assert exc.value.code == "provider_rate_limited"
    assert chain["resolved"] == [MeetingSttProvider.ELEVENLABS]


async def test_silence_is_final_whatever_the_engine(chain: dict[str, Any]) -> None:
    chain["order"] = [MeetingSttProvider.ELEVENLABS, MeetingSttProvider.LOCAL]
    chain["behaviour"] = {
        MeetingSttProvider.ELEVENLABS: TranscriptionError("no_speech", "silence", transient=False),
    }
    with pytest.raises(TranscriptionError) as exc:
        await _call()
    assert exc.value.code == "no_speech" and chain["resolved"] == [MeetingSttProvider.ELEVENLABS]


async def test_when_every_engine_fails_the_last_error_is_reported(chain: dict[str, Any]) -> None:
    chain["order"] = [MeetingSttProvider.ELEVENLABS, MeetingSttProvider.OPENAI]
    chain["behaviour"] = {
        MeetingSttProvider.ELEVENLABS: TranscriptionError(
            "invalid_api_key", "refused", transient=False
        ),
        MeetingSttProvider.OPENAI: TranscriptionError(
            "provider_file_too_large", "413", transient=False
        ),
    }
    with pytest.raises(TranscriptionError) as exc:
        await _call()
    assert exc.value.code == "provider_file_too_large"
    assert chain["resolved"] == [MeetingSttProvider.ELEVENLABS, MeetingSttProvider.OPENAI]


async def test_no_engine_at_all_is_its_own_code(chain: dict[str, Any]) -> None:
    chain["order"] = []
    with pytest.raises(TranscriptionError) as exc:
        await _call()
    assert exc.value.code == "no_engine_available" and exc.value.transient is False
