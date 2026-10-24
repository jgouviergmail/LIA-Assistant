"""A meeting's audio reaches its STT vendor without one read on the event loop (AC-035).

httpx reads a synchronous file handed to ``files=`` chunk by chunk ON the event
loop, so a slow disk held every other request of the worker — the SSE streams
included — for as long as the upload lasted. The three file engines now stream the
audio through :class:`LocalFileRead`. These tests put the audio on a slow disk,
watch a witness task keep running WHILE the disk is being read, and check that the
file is closed on every way out: an answer, a refusal, a cancellation.
"""

from __future__ import annotations

import asyncio
import io
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
import pytest

from src.domains.voice.stt import elevenlabs_stt, fishaudio_stt, openai_stt
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import STTFileResult
from src.infrastructure.file_transfer import LocalFileRead

pytestmark = pytest.mark.unit

Respond = Callable[[httpx.Request], httpx.Response]
READ_DELAY_S = 0.02  # one read on the slow disk
AUDIO = b"OggS" + bytes(range(256)) * 600  # three reads of 64 KiB, then the end of the file


class _FileEngine(Protocol):
    async def transcribe_file_async(
        self,
        path: str,
        mime_type: str,
        *,
        diarize: bool,
        language: str | None,
        timeout_seconds: float,
    ) -> STTFileResult: ...


@dataclass
class _Disk:
    """A slow disk under the audio: every read waits, and records the thread it ran on."""

    read_threads: list[int] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    reading: threading.Event = field(default_factory=threading.Event)
    first_read: threading.Event = field(default_factory=threading.Event)
    hold: threading.Event | None = None


class _SlowFile(io.BufferedReader):
    def __init__(self, path: Path, disk: _Disk) -> None:
        super().__init__(io.FileIO(path, "rb"))
        self._disk = disk

    def read(self, size: int | None = -1, /) -> bytes:
        disk = self._disk
        disk.read_threads.append(threading.get_ident())
        disk.reading.set()
        disk.first_read.set()
        try:
            if disk.hold is not None:
                assert disk.hold.wait(5), "the test never released the held read"
            time.sleep(READ_DELAY_S)
            return super().read(size)
        finally:
            disk.reading.clear()
            disk.events.append("read")

    def close(self) -> None:
        if not self.closed:
            self._disk.events.append("close")
        super().close()


@dataclass(frozen=True)
class _Engine:
    build: Callable[[Respond], _FileEngine]
    answer: dict[str, Any]


def _routed(monkeypatch: pytest.MonkeyPatch, respond: Respond) -> None:
    """Every ``httpx.AsyncClient`` the engine builds answers through ``respond``."""
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(respond))
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@asynccontextmanager
async def _free_slot(provider: str, api_key: str, *, timeout_seconds: float) -> AsyncIterator[None]:
    yield


@pytest.fixture(params=["elevenlabs", "openai", "fishaudio"])
def engine(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> _Engine:
    if request.param == "elevenlabs":

        def eleven(respond: Respond) -> _FileEngine:
            _routed(monkeypatch, respond)
            return elevenlabs_stt.ElevenLabsSttService(api_key="sk_test", timeout_seconds=5.0)

        word = {"text": "Bonjour", "start": 0, "end": 1, "type": "word", "speaker_id": "s0"}
        answer = {"text": "Bonjour", "audio_duration_secs": 2.0, "language_code": "fra"}
        return _Engine(eleven, {**answer, "words": [word]})
    if request.param == "openai":

        def openai(respond: Respond) -> _FileEngine:
            _routed(monkeypatch, respond)
            return openai_stt.OpenAISttService(api_key="sk-test")

        segment = {"text": "Bonjour", "start": 0, "end": 1, "speaker": "A"}
        return _Engine(openai, {"text": "Bonjour", "duration": 2.0, "segments": [segment]})

    monkeypatch.setattr(fishaudio_stt, "provider_slot", _free_slot)

    def fish(respond: Respond) -> _FileEngine:
        return fishaudio_stt.FishAudioSttService(
            "fish-key",
            "transcribe-1",
            timeout_seconds=5.0,
            http_transport=httpx.MockTransport(respond),
        )

    segment = {"text": "Bonjour", "start": 0.0, "end": 0.5}
    return _Engine(fish, {"text": "Bonjour", "duration": 2.0, "segments": [segment]})


@pytest.fixture
def disk(monkeypatch: pytest.MonkeyPatch) -> _Disk:
    """The audio lives on a slow disk for the whole test."""
    disk = _Disk()

    def slow_open(cls: type[LocalFileRead], path: Path) -> LocalFileRead:
        return cls(_SlowFile(path, disk), path)

    monkeypatch.setattr(LocalFileRead, "open", classmethod(slow_open))
    return disk


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "meeting.ogg"
    path.write_bytes(AUDIO)
    return path


def _answering(payload: dict[str, Any]) -> Respond:
    return lambda request: httpx.Response(200, json=payload)


def _refusing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={"detail": "the vendor is resting"})


async def _transcribe(service: _FileEngine, audio: Path) -> STTFileResult:
    return await service.transcribe_file_async(
        str(audio), "audio/ogg", diarize=True, language="fr", timeout_seconds=5.0
    )


async def test_the_loop_keeps_running_while_the_audio_is_read(
    engine: _Engine, disk: _Disk, audio: Path
) -> None:
    ran_during_reads = 0
    finished = asyncio.Event()

    async def witness() -> None:
        nonlocal ran_during_reads
        while not finished.is_set():
            if disk.reading.is_set():
                ran_during_reads += 1
            await asyncio.sleep(0)

    watching = asyncio.create_task(witness())
    try:
        result = await _transcribe(engine.build(_answering(engine.answer)), audio)
    finally:
        finished.set()
        await watching

    assert result.text == "Bonjour"
    assert disk.read_threads, "the upload never read the audio through LocalFileRead"
    assert threading.get_ident() not in disk.read_threads, "a read ran on the event loop"
    assert ran_during_reads > 0, "nothing else ran on the loop while the disk was read"


async def test_the_audio_is_closed_once_the_answer_is_in(
    engine: _Engine, disk: _Disk, audio: Path
) -> None:
    await _transcribe(engine.build(_answering(engine.answer)), audio)

    assert disk.events.count("close") == 1 and disk.events[-1] == "close"


async def test_the_audio_is_closed_when_the_vendor_refuses(
    engine: _Engine, disk: _Disk, audio: Path
) -> None:
    with pytest.raises(STTProviderError):
        await _transcribe(engine.build(_refusing), audio)

    assert disk.events.count("close") == 1 and disk.events[-1] == "close"


async def test_a_cancelled_upload_closes_the_audio_after_the_read_in_flight(
    engine: _Engine, disk: _Disk, audio: Path
) -> None:
    disk.hold = threading.Event()
    upload = asyncio.create_task(_transcribe(engine.build(_answering(engine.answer)), audio))
    try:
        assert await asyncio.to_thread(disk.first_read.wait, 5), "the audio was never read"
        upload.cancel()
        await asyncio.sleep(0.05)
        assert "close" not in disk.events, "the file was closed under a read still running"
    finally:
        disk.hold.set()
        (outcome,) = await asyncio.gather(upload, return_exceptions=True)

    assert isinstance(outcome, asyncio.CancelledError)
    assert disk.events[-2:] == ["read", "close"] and disk.events.count("close") == 1
