"""Transcription helpers and engine dispatch (ADR-258).

Pure folding of provider words into speaker turns, the structural
transient/permanent classification, and both engine paths under fakes: the
remote one records its spend, the local one decodes in blocks.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.meetings import transcription
from src.domains.meetings.engine import ResolvedEngine
from src.domains.meetings.models import MeetingSttProvider
from src.domains.meetings.transcription import (
    PERMANENT_STT_CODES,
    TURN_GAP_SECONDS,
    TranscriptionError,
    build_turns,
    is_transient_provider_code,
    speaker_label_map,
    transcribe_meeting,
    transcript_text,
    turns_from_text,
)
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import STTFileResult, TranscriptWord

pytestmark = pytest.mark.unit


def _w(text: str, start: float, end: float, speaker: str | None = None) -> TranscriptWord:
    return TranscriptWord(text=text, start=start, end=end, speaker=speaker)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_speaker_labels_follow_first_appearance_whatever_the_provider_ids() -> None:
    words = [_w("a", 0, 1, "speaker_7"), _w("b", 1, 2, "speaker_0"), _w("c", 2, 3, "speaker_7")]
    assert speaker_label_map(words) == {"speaker_7": "S1", "speaker_0": "S2"}


def test_turns_split_on_speaker_change_and_on_a_long_pause() -> None:
    words = [
        _w("Bonjour", 0.0, 0.5, "A"),
        _w("à", 0.5, 0.6, "A"),
        _w("tous", 0.6, 1.0, "A"),
        _w("Merci", 1.2, 1.6, "B"),
        _w("Reprenons", 1.6 + TURN_GAP_SECONDS + 0.5, 5.0, "B"),
    ]
    turns = build_turns(words)
    assert [(t.speaker, t.text) for t in turns] == [
        ("S1", "Bonjour à tous"),
        ("S2", "Merci"),
        ("S2", "Reprenons"),
    ]
    assert turns[0].start == 0.0 and turns[0].end == 1.0
    assert turns[2].start == pytest.approx(1.6 + TURN_GAP_SECONDS + 0.5)


def test_spacing_words_are_folded_and_unlabelled_words_get_the_fallback_speaker() -> None:
    words = [_w("Un", 0, 0.3), _w(" ", 0.3, 0.3), _w("deux", 0.3, 0.6), _w("", 0.6, 0.6)]
    turns = build_turns(words)
    assert len(turns) == 1
    assert turns[0].speaker == "S1" and turns[0].text == "Un deux"


def test_turns_from_text_covers_the_whole_recording_or_nothing() -> None:
    assert turns_from_text("   ", duration_seconds=10) == []
    (turn,) = turns_from_text("  hello   world ", duration_seconds=42.5)
    assert (turn.speaker, turn.start, turn.end, turn.text) == ("S1", 0.0, 42.5, "hello world")
    assert transcript_text([turn]) == "S1: hello world"


@pytest.mark.parametrize("code", sorted(PERMANENT_STT_CODES))
def test_permanent_codes_are_never_retried(code: str) -> None:
    assert is_transient_provider_code(code) is False


@pytest.mark.parametrize(
    "code", ["provider_timeout", "provider_rate_limited", "provider_http_error"]
)
def test_transport_codes_are_retried(code: str) -> None:
    assert is_transient_provider_code(code) is True


# ---------------------------------------------------------------------------
# Remote engine
# ---------------------------------------------------------------------------


def _remote_engine() -> ResolvedEngine:
    return ResolvedEngine(
        provider=MeetingSttProvider.ELEVENLABS,
        model="scribe_v2",
        diarized=True,
        api_key="sk_test",
        cost_per_hour_eur=0.2,
        local_rtf_estimate=None,
    )


class _FakeTranscriber:
    def __init__(self, result: STTFileResult | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def transcribe_file_async(
        self, path: str, mime_type: str, **kwargs: Any
    ) -> STTFileResult:
        self.calls.append({"path": path, "mime_type": mime_type, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch):
    """Wire a fake transcriber, a fixed price and a spend recorder into the remote path."""
    holder: dict[str, Any] = {"spend": []}

    def install(result: STTFileResult | Exception) -> _FakeTranscriber:
        fake = _FakeTranscriber(result)
        monkeypatch.setattr(
            "src.domains.voice.stt.factory.build_file_transcriber", lambda *a, **k: fake
        )
        return fake

    monkeypatch.setattr(
        transcription, "get_cached_cost_audio_usd_eur", lambda model, seconds: (0.11, 0.10)
    )

    async def _spend(user_id: uuid.UUID, seconds: float, eur: float) -> None:
        holder["spend"].append((user_id, seconds, eur))

    monkeypatch.setattr(transcription, "_record_remote_spend", _spend)
    holder["install"] = install
    return holder


async def _noop() -> None:
    return None


async def test_remote_words_become_turns_and_the_spend_is_recorded(remote: dict[str, Any]) -> None:
    user_id = uuid.uuid4()
    fake = remote["install"](
        STTFileResult(
            text="Bonjour Merci",
            words=[_w("Bonjour", 0, 1, "spk_a"), _w("Merci", 1.2, 2, "spk_b")],
            audio_duration_seconds=120.0,
            language_code="fr",
            diarized=True,
        )
    )
    outcome = await transcribe_meeting(
        _remote_engine(),
        audio_path=Path("/tmp/audio.webm"),
        mime_type="audio/webm",
        duration_seconds=118.0,
        language_hint="auto",
        user_id=user_id,
        heartbeat=_noop,
    )
    assert [t.speaker for t in outcome.turns] == ["S1", "S2"]
    assert outcome.audio_duration_seconds == 120.0  # the provider's figure wins when present
    assert (outcome.cost_usd, outcome.cost_eur) == (0.11, 0.10)
    assert outcome.diarized is True and outcome.language_code == "fr"
    assert remote["spend"] == [(user_id, 120.0, 0.10)]
    # 'auto' is not a language hint the provider should receive
    assert fake.calls[0]["language"] is None and fake.calls[0]["diarize"] is True


async def test_an_unpriced_model_reports_no_cost_rather_than_a_free_one(
    remote: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pricing cache answers (0, 0) for a model it does not know (measured on the dev
    instance before its seed was applied): that is an absence of price, not a price."""
    monkeypatch.setattr(
        transcription, "get_cached_cost_audio_usd_eur", lambda model, seconds: (0.0, 0.0)
    )
    remote["install"](
        STTFileResult(
            text="Bonjour",
            words=[_w("Bonjour", 0, 1, "spk_a")],
            audio_duration_seconds=60.0,
            language_code="fr",
            diarized=True,
        )
    )
    outcome = await transcribe_meeting(
        _remote_engine(),
        audio_path=Path("/tmp/audio.webm"),
        mime_type="audio/webm",
        duration_seconds=60.0,
        language_hint=None,
        user_id=uuid.uuid4(),
        heartbeat=_noop,
    )
    assert outcome.cost_usd is None and outcome.cost_eur is None
    # The spend is still recorded (duration is a fact even when the price is not).
    assert remote["spend"][0][1:] == (60.0, 0.0)


async def test_remote_plain_text_falls_back_to_one_turn_and_the_probe_duration(
    remote: dict[str, Any],
) -> None:
    remote["install"](
        STTFileResult(
            text="only text",
            words=[],
            audio_duration_seconds=0.0,
            language_code=None,
            diarized=False,
        )
    )
    outcome = await transcribe_meeting(
        _remote_engine(),
        audio_path=Path("/tmp/audio.webm"),
        mime_type="audio/webm",
        duration_seconds=33.0,
        language_hint="fr",
        user_id=uuid.uuid4(),
        heartbeat=_noop,
    )
    assert [(t.speaker, t.text, t.end) for t in outcome.turns] == [("S1", "only text", 33.0)]
    assert outcome.audio_duration_seconds == 33.0 and outcome.diarized is False


async def test_remote_silence_is_a_permanent_failure(remote: dict[str, Any]) -> None:
    remote["install"](
        STTFileResult(
            text="   ", words=[], audio_duration_seconds=10.0, language_code=None, diarized=False
        )
    )
    with pytest.raises(TranscriptionError) as exc:
        await transcribe_meeting(
            _remote_engine(),
            audio_path=Path("/tmp/a.webm"),
            mime_type="audio/webm",
            duration_seconds=10.0,
            language_hint=None,
            user_id=uuid.uuid4(),
            heartbeat=_noop,
        )
    assert exc.value.code == "no_speech" and exc.value.transient is False
    # Billed anyway: the provider did the work.
    assert len(remote["spend"]) == 1


@pytest.mark.parametrize(
    ("code", "transient"),
    [
        ("invalid_api_key", False),
        ("provider_file_too_large", False),
        ("provider_rate_limited", True),
    ],
)
async def test_remote_provider_errors_keep_their_classification(
    remote: dict[str, Any], code: str, transient: bool
) -> None:
    remote["install"](STTProviderError(code=code, message="boom"))
    with pytest.raises(TranscriptionError) as exc:
        await transcribe_meeting(
            _remote_engine(),
            audio_path=Path("/tmp/a.webm"),
            mime_type="audio/webm",
            duration_seconds=10.0,
            language_hint=None,
            user_id=uuid.uuid4(),
            heartbeat=_noop,
        )
    assert (exc.value.code, exc.value.transient) == (code, transient)
    assert remote["spend"] == []


# ---------------------------------------------------------------------------
# Local engine
# ---------------------------------------------------------------------------


async def test_local_engine_decodes_in_blocks_and_heartbeats_between_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decoded: list[float] = []
    beats = 0

    async def _decode(path: Path, *, offset_seconds: float, length_seconds: float) -> bytes:
        decoded.append(offset_seconds)
        return b"\x00\x01" * 16

    class _Service:
        async def transcribe_unbounded_pcm_async(
            self, pcm: bytes, *, language: str | None, on_window=None
        ) -> str:
            assert language == "fr"
            return f"bloc{len(decoded)}"

    async def _beat() -> None:
        nonlocal beats
        beats += 1

    monkeypatch.setattr(transcription, "_decode_block", _decode)
    monkeypatch.setattr("src.domains.voice.stt.sherpa_stt.get_stt_service", lambda: _Service())
    monkeypatch.setattr(transcription, "MEETINGS_LOCAL_BLOCK_SECONDS", 600)
    engine = ResolvedEngine(
        provider=MeetingSttProvider.LOCAL,
        model=None,
        diarized=False,
        api_key=None,
        cost_per_hour_eur=None,
        local_rtf_estimate=1.5,
    )
    outcome = await transcribe_meeting(
        engine,
        audio_path=Path("/tmp/a.webm"),
        mime_type="audio/webm",
        duration_seconds=1500.0,  # 25 min → 3 blocks of 600 s
        language_hint="fr",
        user_id=uuid.uuid4(),
        heartbeat=_beat,
    )
    assert decoded == [0, 600, 1200]
    assert beats == 3
    assert outcome.provider is MeetingSttProvider.LOCAL and outcome.diarized is False
    assert outcome.turns[0].text == "bloc1 bloc2 bloc3" and outcome.cost_eur == 0.0


async def test_local_engine_without_speech_fails_for_good(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _decode(path: Path, **kwargs: Any) -> bytes:
        return b"\x00\x00"

    class _Service:
        async def transcribe_unbounded_pcm_async(self, pcm: bytes, **kwargs: Any) -> str:
            return "   "

    monkeypatch.setattr(transcription, "_decode_block", _decode)
    monkeypatch.setattr("src.domains.voice.stt.sherpa_stt.get_stt_service", lambda: _Service())
    engine = SimpleNamespace(is_remote=False)
    with pytest.raises(TranscriptionError) as exc:
        await transcribe_meeting(
            engine,  # type: ignore[arg-type]
            audio_path=Path("/tmp/a.webm"),
            mime_type="audio/webm",
            duration_seconds=5.0,
            language_hint=None,
            user_id=uuid.uuid4(),
            heartbeat=_noop,
        )
    assert exc.value.code == "no_speech" and exc.value.transient is False
