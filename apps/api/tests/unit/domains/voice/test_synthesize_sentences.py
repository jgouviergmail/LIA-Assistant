"""The synthesis loops of the voice service: the readout, the comment, the progressive stream.

Rules they share with the progressive streamer: a sentence with nothing to
pronounce is never sent (a provider refuses it, after billing the call), a
failure is logged by its facts, never its message (ADR-303), and every SERVED
sentence is recorded once, as the engine that spoke bills it (ADR-345).
"""

from __future__ import annotations

import asyncio
import base64
import io
import wave
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from structlog.testing import capture_logs

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import service as voice_service
from src.domains.voice.client import EdgeTTSClient
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.factory import TTSConfig
from src.domains.voice.protocol import RawAudioSpec
from src.domains.voice.schemas import VoiceAudioChunk
from src.domains.voice.service import VoiceCommentService, _SynthesisMetrics
from tests.support.structlog_capture import fresh_module_logger
from tests.support.voice_clock import retirement_day, speak_on

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    yield from fresh_module_logger(voice_service)


@dataclass
class _Ledger:
    """What the turn's tracker was asked to record."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def record_tts_call(
        self, provider: str, model: str, characters: int, duration_ms: float = 0.0, **units: Any
    ) -> None:
        self.calls.append({"provider": provider, "model": model, "characters": characters})


def _client(synthesize: AsyncMock, provider: str = "openai", **extra: object) -> SimpleNamespace:
    return SimpleNamespace(
        synthesize=synthesize, provider_name=provider, audio_format="mp3", **extra
    )


def _service(
    client: SimpleNamespace, ledger: _Ledger | None = None, *, model: str = "tts-model"
) -> VoiceCommentService:
    service = VoiceCommentService(tts_client=client, tracker=ledger)  # type: ignore[arg-type]
    config = SimpleNamespace(provider=client.provider_name, model=model, voice_settings={})
    service._serve_tts = AsyncMock(return_value=(config, client))  # type: ignore[method-assign]
    service._get_voice_for_language = AsyncMock(return_value="voice")  # type: ignore[method-assign]
    service._resolve_prosody_settings = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return service


async def _direct(service: VoiceCommentService, sentences: list[str]) -> list[VoiceAudioChunk]:
    return [
        chunk
        async for chunk in service._synthesize_sentences(
            sentences, "fr", _SynthesisMetrics(), "direct_tts"
        )
    ]


async def _progressive(service: VoiceCommentService, text: str) -> list[VoiceAudioChunk]:
    queue: asyncio.Queue[VoiceAudioChunk | None] = asyncio.Queue()
    streamer, drain = await service.start_progressive_chat_stream("fr", queue)
    streamer.feed(text)
    streamer.close_input()
    await drain
    chunks: list[VoiceAudioChunk] = []
    while (chunk := await queue.get()) is not None:
        chunks.append(chunk)
    return chunks


async def _comment(service: VoiceCommentService, text: str) -> list[VoiceAudioChunk]:
    async def astream(prompt: str, config: object = None) -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(content=text)

    llm = SimpleNamespace(astream=astream)
    service._build_voice_llm_invocation = AsyncMock(  # type: ignore[method-assign]
        return_value=(llm, "prompt", None)
    )
    return [chunk async for chunk in service.stream_voice_comment("context", "", "fr")]


async def test_a_sentence_with_nothing_to_say_is_not_sent() -> None:
    synthesize = AsyncMock(return_value=b"audio")

    chunks = await _direct(
        _service(_client(synthesize)), ["Bonjour.", "🎉 [laughs] ✨.", "Au revoir.", "🙂"]
    )

    assert [call.args[0] for call in synthesize.await_args_list] == ["Bonjour.", "Au revoir."]
    assert [(c.phrase_index, c.phrase_text, c.is_last) for c in chunks] == [
        (0, "Bonjour.", False),
        (1, "Au revoir.", True),
    ]


async def test_a_refusal_is_logged_by_its_code_never_its_message() -> None:
    refusal = TTSProviderError(
        "provider_http_error",
        "HTTP 400: refused « the words of the answer »",
        details={"status_code": 400},
    )

    with capture_logs() as logs:
        chunks = await _direct(_service(_client(AsyncMock(side_effect=refusal))), ["Bonjour."])

    assert chunks == []
    errors = [entry for entry in logs if entry["event"] == "direct_tts_chunk_error"]
    assert [(e["error_code"], e["status_code"], e["transient"]) for e in errors] == [
        ("provider_http_error", 400, False)
    ]
    assert "the words of the answer" not in repr(logs)


@pytest.mark.parametrize("path", ["direct", "progressive", "comment"])
async def test_each_served_sentence_is_recorded_once_and_a_refused_one_never(path: str) -> None:
    """One record per served sentence, on the engine that spoke — never a
    total computed after the fact, which billed refused sentences (2026-09-20)."""

    async def synthesize(text: str, voice_name: str | None = None, **_: object) -> bytes:
        if text.startswith("Refused"):
            raise TTSProviderError("provider_http_error", details={"status_code": 400})
        return b"audio"

    ledger = _Ledger()
    service = _service(_client(AsyncMock(side_effect=synthesize)), ledger)
    text = "Served one. Refused two. Served three. "

    if path == "direct":
        chunks = await _direct(service, ["Served one.", "Refused two.", "Served three."])
    elif path == "progressive":
        chunks = await _progressive(service, text)
    else:
        chunks = await _comment(service, text)

    assert [c.phrase_text for c in chunks] == ["Served one.", "Served three."]
    assert sorted(call["characters"] for call in ledger.calls) == [11, 13]
    assert {(call["provider"], call["model"]) for call in ledger.calls} == {("openai", "tts-model")}


async def test_the_free_engine_is_never_recorded() -> None:
    ledger = _Ledger()

    await _direct(
        _service(_client(AsyncMock(return_value=b"mp3"), provider="edge"), ledger), ["Oui."]
    )

    assert ledger.calls == []


@pytest.mark.parametrize("progressive", [False, True])
async def test_browser_pcm_comment_carries_its_rate_and_mime_without_resynthesis(
    progressive: bool,
) -> None:
    samples = b"\x00\x01" * 2400
    client = _client(AsyncMock(return_value=samples), raw_audio_spec=RawAudioSpec(24000))
    client.audio_format = "pcm"
    service = _service(client)

    if progressive:
        chunks = await _progressive(service, "Bonjour. ")
    else:
        chunks = await _direct(service, ["Bonjour."])

    assert len(chunks) == 1
    assert chunks[0].mime_type == "audio/wav"
    with wave.open(io.BytesIO(base64.b64decode(chunks[0].audio_base64)), "rb") as reader:
        assert reader.getframerate() == 24000
        assert reader.readframes(2400) == samples
    client.synthesize.assert_awaited_once()


async def test_edge_standing_in_speaks_with_its_own_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured engine's voice ids mean nothing to Edge: read from the
    configuration the service asked for, they made the stand-in speak nothing."""
    configured = TTSConfig(
        provider="elevenlabs",
        model="eleven_v4",
        voice_male="male-voice-id",
        voice_female="female-voice-id",
    )
    monkeypatch.setattr(voice_service, "get_tts_config", AsyncMock(return_value=configured))
    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: None)
    )
    service = VoiceCommentService(lia_gender="female")
    try:
        assert isinstance(await service._get_tts_client(), EdgeTTSClient)
        voice = await service._get_voice_for_language("fr")
        assert voice != "female-voice-id"
        assert voice.endswith("Neural")
        assert (await service._get_tts_config()).model == "edge-tts"
    finally:
        await service.close()


def _spoken(synthesize: AsyncMock) -> list[str]:
    return [call.args[0] for call in synthesize.await_args_list]


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        # The engine's own words, within one budget across the whole comment.
        (
            "elevenlabs",
            "eleven_v4",
            ["[warm] Bonjour.", "[sighs] Encore une.", "Et voilà."],
        ),
        # A fixed set: warm is not in it, so it is dropped and costs nothing.
        (
            "fishaudio",
            "s1",
            ["Bonjour.", "(sighing) Encore une.", "Et (laughing) voilà."],
        ),
        # An engine that reads brackets aloud never receives one.
        ("openai", "gpt-4o-mini-tts", ["Bonjour.", "Encore une.", "Et voilà."]),
    ],
)
async def test_a_comment_written_for_speech_is_spelled_for_its_engine(
    monkeypatch: pytest.MonkeyPatch, provider: str, model: str, expected: list[str]
) -> None:
    monkeypatch.setattr(voice_service.settings, "voice_expressive_cues_max", 2)
    # s1 speaks its own set until its last day; past it, s2.1-pro speaks for it.
    speak_on(monkeypatch, retirement_day("fishaudio", "s1"))
    synthesize = AsyncMock(return_value=b"audio")
    service = _service(_client(synthesize, provider=provider), model=model)

    await _comment(service, "[warm] Bonjour. [sighs] Encore une. Et [laughs] voilà. ")

    assert sorted(_spoken(synthesize)) == sorted(expected)


@pytest.mark.parametrize("path", ["direct", "progressive"])
async def test_an_answer_read_aloud_keeps_its_brackets_as_words(path: str) -> None:
    """An answer was not written for speech: a bracket in it is never a direction."""
    synthesize = AsyncMock(return_value=b"audio")
    service = _service(_client(synthesize, provider="elevenlabs"), model="eleven_v4")
    text = "Voir [la note](https://example.org/a) [1] et [laughs] ici."

    if path == "direct":
        await _direct(service, [text])
    else:
        await _progressive(service, text + " ")

    assert _spoken(synthesize) == ["Voir la note et laughs ici."]


async def test_an_answer_read_by_an_angle_engine_sends_it_no_tag() -> None:
    synthesize = AsyncMock(return_value=b"audio")
    service = _service(_client(synthesize, provider="gemini"), model="gemini-3.8-flash-tts")

    await _progressive(service, "Écris <laugh> dans le <b>champ</b>. ")

    assert _spoken(synthesize) == ["Écris dans le champ ."]
