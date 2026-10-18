"""One segment from facts to audio: written, verified, voiced, billed, mixed — or why not."""

from __future__ import annotations

import asyncio
import dataclasses
import io
import threading
import wave
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domains.radio import audio as audio_module
from src.domains.radio import production as production_module
from src.domains.radio.audio import AssembledAudio, AudioAssemblyError, LineAudio
from src.domains.radio.cast import Cast
from src.domains.radio.constants import TTS_RATE_LIMIT_BASE_WAIT_SECONDS
from src.domains.radio.delivery import StylePhrases
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat, RadioRole
from src.domains.radio.production import (
    ProductionLimits,
    ProductionOutcome,
    VoicedLine,
    VoiceEngine,
    WritingRequest,
    produce_segment,
)
from src.domains.radio.script import (
    LineKind,
    RadioDelivery,
    ScriptDraft,
    ScriptLine,
    ScriptPart,
    Tone,
)
from src.domains.radio.verification import Refusal, VerifiedLine, Violation
from src.domains.voice.billing import SynthesisResult
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.protocol import DialogueAudio, DialogueTurn, RawAudioSpec
from src.infrastructure.observability.metrics_radio import radio_dialogue_takes_total

pytestmark = pytest.mark.unit

SOURCE = SourceRef(label="Example News", url="https://news.example.org/budget")
PACK = FactPack(
    format=RadioFormat.BRIEF,
    facts=(
        RadioFact(
            id="n1",
            kind=FactKind.NEWS,
            text="The parliament adopted the budget by 312 votes.",
            key="news:budget",
            sensitivity=Sensitivity.PUBLIC,
            source=SOURCE,
        ),
    ),
)
REQUEST = WritingRequest(
    format=RadioFormat.BRIEF,
    pack=PACK,
    language="en",
    local_now=datetime(2026, 9, 26, 9, 5, tzinfo=UTC),
    station_name="LIA Radio",
    station_id=False,
)
CAST = Cast(voices=dict.fromkeys(RadioRole, "voice-a") | {RadioRole.ANCHOR: "voice-b"})
PHRASES = StylePhrases(
    roles={RadioRole.HOST: "a warm host", RadioRole.ANCHOR: "a news anchor"},
    qualities={"tone.serious": "serious"},
    template="Read as {role}: {qualities}.",
    template_plain="Read as {role}.",
)
LIMITS = ProductionLimits(
    quote_max_chars=120,
    tts_concurrency=2,
    mix_timeout_s=30.0,
    tts_attempts=3,
    tts_rate_limit_wait_max_s=30.0,
)


def line(part: ScriptPart, kind: LineKind, text: str, *refs: str) -> ScriptLine:
    return ScriptLine(
        role=RadioRole.ANCHOR,
        part=part,
        kind=kind,
        text=text,
        delivery=RadioDelivery(tone=Tone.SERIOUS),
        refs=list(refs),
    )


DRAFT = ScriptDraft(
    title="Budget",
    lines=[
        line(ScriptPart.INTRO, LineKind.TRANSITION, "Here is the news."),
        line(
            ScriptPart.BODY,
            LineKind.FACT,
            "The parliament adopted the budget by 312 votes.",
            "n1",
            "n1",
        ),
        line(ScriptPart.OUTRO, LineKind.TRANSITION, "That was the brief."),
    ],
)
SPOKEN_INTRO = "Budget. Here is the news."


class FakeWriter:
    def __init__(self, draft: ScriptDraft | None) -> None:
        self.draft = draft
        self.requests: list[WritingRequest] = []

    async def write(self, request: WritingRequest) -> ScriptDraft | None:
        self.requests.append(request)
        return self.draft


class FakeClient:
    """A character-billed engine: ``synthesize`` only."""

    def __init__(
        self,
        provider: str = "openai",
        fail_on: str | None = None,
        failures: dict[str, list[TTSProviderError]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str | None, dict[str, object]]] = []
        self.fail_on = fail_on
        self.failures = failures or {}
        self.provider = provider

    @property
    def provider_name(self) -> str:
        return self.provider

    @property
    def audio_format(self) -> str:
        return "mp3"

    async def close(self) -> None:
        return None

    async def synthesize(self, text: str, voice_name: str | None = None, **kwargs: object) -> bytes:
        self.calls.append((text, voice_name, kwargs))
        await asyncio.sleep(0)
        if text == self.fail_on:
            raise TTSProviderError("provider_rate_limited")
        if self.failures.get(text):
            raise self.failures[text].pop(0)
        return b"audio:" + text.encode()


class FakeTokenClient(FakeClient):
    """A token-billed engine: it reports its usage."""

    async def synthesize_with_usage(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> SynthesisResult:
        audio = await self.synthesize(text, voice_name, **kwargs)
        return SynthesisResult(audio, len(text), input_tokens=9, output_tokens=350)


class FakePcmClient(FakeClient):
    def __init__(self, rate: int, audio: bytes = b"\x00\x01" * 20) -> None:
        super().__init__("elevenlabs")
        self.rate = rate
        self.audio = audio

    @property
    def audio_format(self) -> str:
        return "pcm"

    @property
    def raw_audio_spec(self) -> RawAudioSpec:
        return RawAudioSpec(self.rate)

    async def synthesize(self, text: str, voice_name: str | None = None, **kwargs: object) -> bytes:
        self.calls.append((text, voice_name, kwargs))
        return self.audio


class FakeDialogueClient(FakeClient):
    """An engine voicing several speakers in one request, timing every turn."""

    def __init__(self, *, placed: bool = True, refusal: TTSProviderError | None = None) -> None:
        super().__init__("fishaudio")
        self.placed = placed
        self.refusal = refusal
        self.dialogues: list[list[DialogueTurn]] = []

    async def synthesize_dialogue(
        self, turns: Sequence[DialogueTurn], **kwargs: object
    ) -> DialogueAudio:
        self.dialogues.append(list(turns))
        await asyncio.sleep(0)
        if self.refusal is not None:
            raise self.refusal
        sent = "".join(
            f"<|speaker:{n}|>{turn.cue + ' ' if turn.cue else ''}{turn.words}"
            for n, turn in enumerate(turns)
        )
        starts = tuple(1.5 * n + 0.1 for n in range(len(turns))) if self.placed else None
        return DialogueAudio(audio=b"take:" + sent.encode(), sent_text=sent, turn_starts_s=starts)


class Ledger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int | None, int | None, int | None]] = []

    def record_tts_call(
        self,
        provider: str,
        model: str,
        characters: int,
        duration_ms: float = 0.0,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        billed_units: int | None = None,
    ) -> None:
        self.calls.append((provider, model, characters, input_tokens, output_tokens, billed_units))


class FakeMixer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.received: list[tuple[ScriptPart, bytes]] = []
        self.windows: list[tuple[float | None, float | None]] = []

    async def __call__(
        self,
        lines: Sequence[LineAudio],
        out: Path,
        *,
        timeout_s: float,
    ) -> AssembledAudio:
        self.received = [(line.part, line.path.read_bytes()) for line in lines]
        self.windows = [(line.start_s, line.end_s) for line in lines]
        if self.fail:
            raise AudioAssemblyError("segment assembly failed: FfmpegError")
        out.write_bytes(b"mixed")
        offsets = (1.2, 3.0, 9.4) if len(lines) == 3 else tuple(float(i) for i in range(len(lines)))
        return AssembledAudio(duration_s=12.5, line_offsets_s=offsets)


def engine(client: FakeClient) -> VoiceEngine:
    return VoiceEngine(client=client, model="tts-model", phrases=PHRASES)


@pytest.fixture(autouse=True)
def backoffs(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The retry's waits, recorded instead of slept (the engine still yields)."""
    real_sleep = asyncio.sleep
    waits: list[float] = []

    async def no_wait(seconds: float) -> None:
        if seconds:
            waits.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    return waits


@pytest.fixture
def mixer(monkeypatch: pytest.MonkeyPatch) -> FakeMixer:
    fake = FakeMixer()
    monkeypatch.setattr(production_module, "assemble_segment", fake)
    return fake


class FakeChecker:
    """The model verifier, answering as told and keeping what it was shown."""

    def __init__(self, answer: frozenset[int] | None) -> None:
        self.answer = answer
        self.shown: list[tuple[str, ...]] = []

    async def unsupported(
        self, lines: Sequence[VerifiedLine], pack: FactPack
    ) -> frozenset[int] | None:
        self.shown.append(tuple(line.text for line in lines))
        return self.answer


async def produce(
    tmp_path: Path,
    client: FakeClient,
    *,
    draft: ScriptDraft | None = DRAFT,
    checker: FakeChecker | None = None,
    request: WritingRequest = REQUEST,
) -> tuple[production_module.ProductionResult, Ledger]:
    ledger = Ledger()
    result = await produce_segment(
        request,
        tmp_path / "0003.mp3",
        writer=FakeWriter(draft),
        engine=engine(client),
        cast=CAST,
        ledger=ledger,
        limits=LIMITS,
        checker=checker,
    )
    return result, ledger


class TestProduced:
    async def test_cancelled_mix_cleans_raw_lines_and_partial_without_touching_old_destination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def probe(path: Path, *, timeout_s: float) -> float:
            return 1.0

        async def mix(args: tuple[str, ...], *, timeout_s: float) -> bytes:
            Path(args[-1]).write_bytes(b"unfinished mix")
            raise asyncio.CancelledError

        monkeypatch.setattr(audio_module, "probe_duration", probe)
        monkeypatch.setattr(audio_module, "run_ffmpeg", mix)
        out = tmp_path / "0003.mp3"
        out.write_bytes(b"previous completed programme")
        client = FakePcmClient(22050)

        with pytest.raises(asyncio.CancelledError):
            await produce(tmp_path, client)

        assert list(tmp_path.iterdir()) == [out]
        assert out.read_bytes() == b"previous completed programme"
        assert len(client.calls) == len(DRAFT.lines)

    @pytest.mark.parametrize("rate", [16000, 22050, 24000, 44100])
    async def test_raw_pcm_is_wrapped_at_its_rate_after_one_billed_synthesis_per_line(
        self, tmp_path: Path, mixer: FakeMixer, rate: int
    ) -> None:
        client = FakePcmClient(rate)
        result, ledger = await produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert len(client.calls) == len(ledger.calls) == len(DRAFT.lines)
        for _, audio in mixer.received:
            with wave.open(io.BytesIO(audio), "rb") as reader:
                assert reader.getframerate() == rate
                assert reader.readframes(reader.getnframes()) == b"\x00\x01" * 20
        assert list(tmp_path.iterdir()) == [tmp_path / "0003.mp3"]

    @pytest.mark.parametrize("audio", [b"", b"\x01"])
    async def test_malformed_paid_pcm_is_accounted_and_never_resynthesized(
        self, tmp_path: Path, mixer: FakeMixer, audio: bytes
    ) -> None:
        client = FakePcmClient(22050, audio)

        result, ledger = await produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.VOICE_FAILED
        assert result.error_code == "provider_invalid_response"
        assert len(client.calls) == len(ledger.calls) > 0
        assert len({text for text, _, _ in client.calls}) == len(client.calls)
        assert mixer.received == []
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize(
        "fmt",
        [
            RadioFormat.BRIEF,
            RadioFormat.ANALYSIS,
            RadioFormat.DOSSIER,
            RadioFormat.COLUMN,
            RadioFormat.DEBATE,
            RadioFormat.DISCUSSION,
            RadioFormat.NUMBER,
        ],
    )
    async def test_a_single_subject_is_announced_before_the_generic_intro(
        self, tmp_path: Path, mixer: FakeMixer, fmt: RadioFormat
    ) -> None:
        role = FORMAT_SPECS[fmt].roles[0]
        request = replace(REQUEST, format=fmt, pack=FactPack(format=fmt, facts=PACK.facts))
        drafted = ScriptDraft(
            title="The budget vote",
            lines=[
                line(ScriptPart.INTRO, LineKind.TRANSITION, "A closer look.").model_copy(
                    update={"role": role}
                ),
                line(
                    ScriptPart.BODY,
                    LineKind.FACT,
                    "The parliament adopted the budget by 312 votes.",
                    "n1",
                ).model_copy(update={"role": role}),
                line(ScriptPart.OUTRO, LineKind.TRANSITION, "That is the story.").model_copy(
                    update={"role": role}
                ),
            ],
        )
        client = FakeClient()

        result, _ = await produce(tmp_path, client, draft=drafted, request=request)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert result.segment is not None
        assert client.calls[0][0].startswith("The budget vote")
        assert result.segment.transcript[0].sources == (SOURCE,)

    async def test_a_missing_intro_still_starts_with_the_story_title(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        drafted = ScriptDraft(title="The budget vote", lines=DRAFT.lines[1:])

        result, _ = await produce(tmp_path, FakeClient(), draft=drafted)

        assert result.segment is not None
        assert result.segment.transcript[0].text == "The budget vote."
        assert result.segment.transcript[0].sources == (SOURCE,)

    async def test_an_already_spoken_title_is_not_repeated(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        named = DRAFT.lines[0].model_copy(update={"text": "Budget. Here is the news."})
        drafted = ScriptDraft(title="Budget", lines=[named, *DRAFT.lines[1:]])
        client = FakeClient()

        result, _ = await produce(tmp_path, client, draft=drafted)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert client.calls[0][0] == "Budget. Here is the news."

    async def test_every_line_is_voiced_billed_and_mixed_in_order(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient()
        result, ledger = await produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.PRODUCED and result.segment is not None
        assert [voice for _, voice, _ in client.calls] == ["voice-b"] * 3
        assert all(kwargs == {"speed": 1.0} for _, _, kwargs in client.calls)
        assert mixer.received == [
            (ScriptPart.INTRO, b"audio:Budget. Here is the news."),
            (ScriptPart.BODY, b"audio:The parliament adopted the budget by 312 votes."),
            (ScriptPart.OUTRO, b"audio:That was the brief."),
        ]
        assert sorted(call[:3] for call in ledger.calls) == sorted(
            ("openai", "tts-model", len(text)) for text, _, _ in client.calls
        )
        assert result.segment.unrendered == ("tone",)  # a speed cannot say « serious »

    @pytest.mark.parametrize(
        ("model", "unrendered"),
        [("gemini-3.8-flash-tts", ()), ("gemini-2.5-flash-preview-tts", ("tone",))],
    )
    async def test_a_direction_reaches_only_a_model_that_takes_one(
        self, tmp_path: Path, mixer: FakeMixer, model: str, unrendered: tuple[str, ...]
    ) -> None:
        """Measured on dev 2026-09-26: a direction sent to a 2.5 preview is a 400 on
        EVERY line — the radio aired nothing but its music. Withheld, the line airs
        and the nuance it lost is reported."""
        client = FakeTokenClient(provider="gemini")
        result = await produce_segment(
            REQUEST,
            tmp_path / "0003.mp3",
            writer=FakeWriter(DRAFT),
            engine=VoiceEngine(client=client, model=model, phrases=PHRASES),
            cast=CAST,
            ledger=Ledger(),
            limits=LIMITS,
        )
        assert result.outcome is ProductionOutcome.PRODUCED and result.segment is not None
        assert len(client.calls) == 3
        directed = not unrendered
        assert all(("style" in kwargs) is directed for _, _, kwargs in client.calls)
        assert result.segment.unrendered == unrendered

    async def test_a_cue_engine_hears_the_delivery_and_never_a_lines_own_bracket(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        """ADR-345: the writer's tone opens the line, spelled the engine's way; a
        bracket the line itself carries (a headline's « [Update] ») is read as words,
        and what is billed is what was sent."""
        client = FakeClient(provider="fishaudio")
        draft = ScriptDraft(
            title="Budget",
            lines=[
                line(ScriptPart.INTRO, LineKind.TRANSITION, "[Update] Here is the news."),
                *DRAFT.lines[1:],
            ],
        )
        ledger = Ledger()
        result = await produce_segment(
            REQUEST,
            tmp_path / "0003.mp3",
            writer=FakeWriter(draft),
            engine=VoiceEngine(client=client, model="s2.1-pro", phrases=PHRASES),
            cast=CAST,
            ledger=ledger,
            limits=LIMITS,
        )

        assert result.outcome is ProductionOutcome.PRODUCED and result.segment is not None
        sent = [text for text, _, _ in client.calls]
        assert sorted(sent) == sorted(
            [
                "[serious] Budget. Update Here is the news.",
                "[serious] The parliament adopted the budget by 312 votes.",
                "[serious] That was the brief.",
            ]
        )
        assert result.segment.unrendered == ()
        assert sorted(call[2] for call in ledger.calls) == sorted(len(text) for text in sent)

    async def test_the_transcript_follows_the_voice_with_its_sources(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        result, _ = await produce(tmp_path, FakeClient())
        assert result.segment is not None
        transcript = result.segment.transcript
        assert [line.offset_s for line in transcript] == [1.2, 3.0, 9.4]
        assert transcript[1].sources == (SOURCE,)  # cited twice, shown once
        assert transcript[0].sources == (SOURCE,)
        assert result.segment.duration_s == 12.5

    async def test_what_aired_is_the_facts_the_voiced_lines_cite(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        """Cited twice by one line, once in what aired; a dropped line airs nothing."""
        phantom = line(ScriptPart.BODY, LineKind.TRANSITION, "And now, the vote.", "n9")
        drafted = ScriptDraft(title="Budget", lines=[*DRAFT.lines, phantom])
        result, _ = await produce(tmp_path, FakeClient(), draft=drafted)
        assert result.outcome is ProductionOutcome.PRODUCED
        assert result.aired == ("n1",)
        refused, _ = await produce(tmp_path, FakeClient(), draft=None)
        assert refused.aired == ()

    async def test_every_voiced_line_says_where_it_starts_and_what_it_cites(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        """What the listener heard is decided line by line, as the player passes each one
        (ADR-324 decision 35): a production says where every voiced line starts in its
        segment and which facts it cites — each once."""
        result, _ = await produce(tmp_path, FakeClient())
        assert result.lines == (
            VoicedLine(offset_s=1.2, refs=("n1",)),
            VoicedLine(offset_s=3.0, refs=("n1",)),
            VoicedLine(offset_s=9.4, refs=()),
        )

    async def test_no_line_file_outlives_the_production(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        await produce(tmp_path, FakeClient())
        assert sorted(path.name for path in tmp_path.iterdir()) == ["0003.mp3"]

    async def test_a_free_engine_bills_nothing(self, tmp_path: Path, mixer: FakeMixer) -> None:
        _, ledger = await produce(tmp_path, FakeClient(provider="edge"))
        assert ledger.calls == []

    async def test_a_passing_failure_is_outlived_and_billed_once(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        """The free engine's missing audio: the line is tried again, the segment airs."""
        no_audio = TTSProviderError("provider_invalid_response")
        client = FakeClient(failures={SPOKEN_INTRO: [no_audio]})
        result, ledger = await produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert [text for text, _, _ in client.calls].count(SPOKEN_INTRO) == 2
        assert len(ledger.calls) == 3  # a failed attempt is not a synthesis
        assert backoffs == [1.0]

    async def test_a_token_billed_engine_bills_its_usage_report(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        _, ledger = await produce(tmp_path, FakeTokenClient(provider="gemini"))
        assert {(call[3], call[4]) for call in ledger.calls} == {(9, 350)}


def _spoken_by(role: RadioRole, part: ScriptPart, text: str, *refs: str) -> ScriptLine:
    kind = LineKind.FACT if refs else LineKind.TRANSITION
    return ScriptLine(
        role=role,
        part=part,
        kind=kind,
        text=text,
        delivery=RadioDelivery(tone=Tone.SERIOUS),
        refs=list(refs),
    )


#: The anchor and the host answer each other in the body: two voices.
EXCHANGE = ScriptDraft(
    title="Budget",
    lines=[
        _spoken_by(RadioRole.ANCHOR, ScriptPart.INTRO, "Here is the news."),
        _spoken_by(
            RadioRole.ANCHOR,
            ScriptPart.BODY,
            "The parliament adopted the budget by 312 votes.",
            "n1",
        ),
        _spoken_by(RadioRole.HOST, ScriptPart.BODY, "The vote closed a long week.", "n1"),
        _spoken_by(RadioRole.ANCHOR, ScriptPart.OUTRO, "That was the brief."),
    ],
)
DIALOGUE_LIMITS = dataclasses.replace(LIMITS, dialogue_max_bytes=1500)
#: A debate's body: the anchor and three commentators answer each other.
DEBATE = ScriptDraft(
    title="Budget",
    lines=[
        _spoken_by(
            RadioRole.ANCHOR,
            ScriptPart.BODY,
            "The parliament adopted the budget by 312 votes.",
            "n1",
        ),
        _spoken_by(RadioRole.SPEAKER_A, ScriptPart.BODY, "The vote closed a long week.", "n1"),
        _spoken_by(RadioRole.SPEAKER_B, ScriptPart.BODY, "The budget passed at last.", "n1"),
        _spoken_by(RadioRole.SPEAKER_C, ScriptPart.BODY, "The parliament has voted.", "n1"),
        _spoken_by(RadioRole.ANCHOR, ScriptPart.BODY, "The budget is adopted.", "n1"),
    ],
)
DEBATE_CAST = Cast(
    voices=dict.fromkeys(RadioRole, "voice-a")
    | {
        RadioRole.ANCHOR: "voice-b",
        RadioRole.SPEAKER_A: "voice-c",
        RadioRole.SPEAKER_B: "voice-d",
        RadioRole.SPEAKER_C: "voice-e",
    }
)


class TestDialogueTakes:
    """An engine that voices several speakers in one request (ADR-345)."""

    async def _produce(
        self,
        tmp_path: Path,
        client: FakeClient,
        *,
        model: str = "s2.1-pro",
        limits: ProductionLimits = DIALOGUE_LIMITS,
    ) -> tuple[production_module.ProductionResult, Ledger]:
        ledger = Ledger()
        result = await produce_segment(
            REQUEST,
            tmp_path / "0003.mp3",
            writer=FakeWriter(EXCHANGE),
            engine=VoiceEngine(client=client, model=model, phrases=PHRASES),
            cast=CAST,
            ledger=ledger,
            limits=limits,
        )
        return result, ledger

    @staticmethod
    def _taken(outcome: str) -> float:
        return radio_dialogue_takes_total.labels(outcome=outcome)._value.get()

    async def test_the_exchange_is_one_take_and_each_line_a_window_of_it(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeDialogueClient()
        voiced_before = self._taken("voiced")

        result, ledger = await self._produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.PRODUCED
        [turns] = client.dialogues
        assert [(turn.voice, turn.cue) for turn in turns] == [
            ("voice-b", "[serious]"),
            ("voice-a", "[serious]"),
        ]
        assert turns[1].words == "The vote closed a long week."
        # Intro and outro read alone; the body's two lines are the take's windows.
        assert len(client.calls) == 2
        assert mixer.windows == [(None, None), (0.0, 1.6), (1.6, None), (None, None)]
        sent = "".join(f"<|speaker:{n}|>[serious] {turn.words}" for n, turn in enumerate(turns))
        # Three requests billed; the take's markers and cues billed with its words.
        assert len(ledger.calls) == 3
        assert len(sent.encode("utf-8")) in {call[5] for call in ledger.calls}
        assert self._taken("voiced") == voiced_before + 1
        assert not list(tmp_path.glob("*.take*"))  # no take file outlives the production

    async def test_an_unplaced_take_is_voiced_line_by_line_and_stays_billed(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeDialogueClient(placed=False)
        unplaced_before = self._taken("unplaced")

        result, ledger = await self._produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert len(client.dialogues) == 1
        assert len(client.calls) == 4  # every line alone
        assert len(ledger.calls) == 5  # the four lines, and the take the vendor billed
        assert mixer.windows == [(None, None)] * 4
        assert self._taken("unplaced") == unplaced_before + 1

    async def test_a_refused_take_is_voiced_line_by_line_and_never_billed(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        refusal = TTSProviderError("provider_http_error", details={"status_code": 400})
        client = FakeDialogueClient(refusal=refusal)
        failed_before = self._taken("failed")

        result, ledger = await self._produce(tmp_path, client)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert len(client.dialogues) == 1  # a refusal is not tried again
        assert len(client.calls) == len(ledger.calls) == 4
        assert self._taken("failed") == failed_before + 1

    async def test_a_take_never_asks_the_engine_for_more_voices_than_it_takes(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        """Production 2026-10-17: a debate take of four voices was refused whole (400)."""
        client = FakeDialogueClient()

        debate = FORMAT_SPECS[RadioFormat.DEBATE]
        result = await produce_segment(
            replace(REQUEST, format=RadioFormat.DEBATE, roles=debate.roles),
            tmp_path / "0004.mp3",
            writer=FakeWriter(DEBATE),
            engine=VoiceEngine(client=client, model="s2.1-pro", phrases=PHRASES),
            cast=DEBATE_CAST,
            ledger=Ledger(),
            limits=DIALOGUE_LIMITS,
        )

        assert result.outcome is ProductionOutcome.PRODUCED
        assert [[turn.voice for turn in turns] for turns in client.dialogues] == [
            ["voice-b", "voice-c", "voice-d"],
            ["voice-e", "voice-b"],
        ]

    @pytest.mark.parametrize(
        ("model", "limits"),
        [
            # s1 voices one speaker per request.
            ("s1", DIALOGUE_LIMITS),
            # A ceiling of 0 voices every line alone.
            ("s2.1-pro", LIMITS),
        ],
    )
    async def test_without_a_dialogue_every_line_is_voiced_alone(
        self, tmp_path: Path, mixer: FakeMixer, model: str, limits: ProductionLimits
    ) -> None:
        client = FakeDialogueClient()

        result, _ = await self._produce(tmp_path, client, model=model, limits=limits)

        assert result.outcome is ProductionOutcome.PRODUCED
        assert client.dialogues == []
        assert len(client.calls) == 4


class TestNoSegment:
    async def test_a_writer_that_returns_nothing_voices_nothing(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient()
        result, ledger = await produce(tmp_path, client, draft=None)
        assert result.outcome is ProductionOutcome.WRITER_REFUSED
        assert client.calls == [] and ledger.calls == []

    async def test_the_station_named_with_its_digits_is_voiced(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        # The editor is told the station's name: « Radio 42 » is a mention, so
        # the line naming it airs instead of being dropped as a number.
        intro = line(ScriptPart.INTRO, LineKind.TRANSITION, "On Radio 42, the news.")
        named = ScriptDraft(title="Budget", lines=[intro, *DRAFT.lines[1:]])
        result, _ = await produce(
            tmp_path,
            FakeClient(),
            draft=named,
            request=replace(REQUEST, station_name="Radio 42"),
        )
        assert result.outcome is ProductionOutcome.PRODUCED
        assert mixer.received[0] == (ScriptPart.INTRO, b"audio:Budget. On Radio 42, the news.")

    async def test_a_script_the_verifier_refuses_voices_nothing(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient()
        no_body = ScriptDraft(title="Empty", lines=[DRAFT.lines[0], DRAFT.lines[2]])
        result, _ = await produce(tmp_path, client, draft=no_body)
        assert (result.outcome, result.refusal) == (
            ProductionOutcome.SCRIPT_REFUSED,
            Refusal.NO_BODY,
        )
        assert client.calls == []

    async def test_a_refused_script_names_the_rules_that_dropped_its_lines(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        # A refusal read as « no_body » alone could not say WHY the body went:
        # the drops' codes travel with it (codes only — never a line's words).
        invented = line(ScriptPart.BODY, LineKind.FACT, "It passed by 999 votes.", "n1", "n1")
        gutted = ScriptDraft(title="Budget", lines=[DRAFT.lines[0], invented, DRAFT.lines[2]])
        result, _ = await produce(tmp_path, FakeClient(), draft=gutted)
        assert (result.outcome, result.refusal) == (
            ProductionOutcome.SCRIPT_REFUSED,
            Refusal.NO_BODY,
        )
        assert result.dropped == (Violation.UNSUPPORTED_NUMBER,)

    async def test_a_line_the_model_flagged_is_named_among_the_drops(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        result, _ = await produce(tmp_path, FakeClient(), checker=FakeChecker(frozenset({1})))
        assert result.outcome is ProductionOutcome.SCRIPT_REFUSED
        assert result.dropped == (Violation.NOT_SUPPORTED,)

    async def test_a_voice_failure_names_its_code_and_leaves_no_file(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient(fail_on="That was the brief.")
        result, ledger = await produce(tmp_path, client)
        assert (result.outcome, result.error_code) == (
            ProductionOutcome.VOICE_FAILED,
            "provider_rate_limited",
        )
        assert list(tmp_path.iterdir()) == []
        assert len(ledger.calls) <= 2  # what was voiced before the failure stays billed

    async def test_a_refusal_is_never_tried_again(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        refused = TTSProviderError("provider_http_error", details={"status_code": 400})
        client = FakeClient(failures={"That was the brief.": [refused]})
        result, _ = await produce(tmp_path, client)
        assert (result.outcome, result.error_code) == (
            ProductionOutcome.VOICE_FAILED,
            "provider_http_error",
        )
        assert [text for text, _, _ in client.calls].count("That was the brief.") == 1
        assert backoffs == []

    async def test_a_line_that_keeps_failing_names_its_last_code(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient(fail_on="That was the brief.")
        result, _ = await produce(tmp_path, client)
        assert result.error_code == "provider_rate_limited"
        attempts = [text for text, _, _ in client.calls].count("That was the brief.")
        assert attempts == LIMITS.tts_attempts

    async def test_a_rate_limited_line_waits_what_the_provider_asks(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        busy = TTSProviderError("provider_rate_limited", retry_after_seconds=12.0)
        client = FakeClient(failures={"That was the brief.": [busy]})
        result, _ = await produce(tmp_path, client)
        assert result.outcome is ProductionOutcome.PRODUCED
        assert 12.0 in backoffs

    async def test_a_rate_limit_without_a_delay_waits_past_a_blip(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        # Measured 2026-09-26: waits of one then two seconds met the same quota
        # three times over, and each lost segment had already paid its voices.
        client = FakeClient(
            failures={"That was the brief.": [TTSProviderError("provider_rate_limited")]}
        )
        result, _ = await produce(tmp_path, client)
        assert result.outcome is ProductionOutcome.PRODUCED
        assert max(backoffs) >= TTS_RATE_LIMIT_BASE_WAIT_SECONDS

    async def test_the_providers_delay_is_bounded(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        busy = TTSProviderError("provider_rate_limited", retry_after_seconds=3600.0)
        client = FakeClient(failures={"That was the brief.": [busy]})
        result, _ = await produce(tmp_path, client)
        assert result.outcome is ProductionOutcome.PRODUCED
        assert max(backoffs) == LIMITS.tts_rate_limit_wait_max_s

    async def test_a_passing_failure_still_backs_off_briefly(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        client = FakeClient(
            failures={"That was the brief.": [TTSProviderError("provider_timeout")]}
        )
        result, _ = await produce(tmp_path, client)
        assert result.outcome is ProductionOutcome.PRODUCED
        assert backoffs == [1.0]

    async def test_a_rate_limit_holds_back_the_lines_not_yet_sent(
        self, tmp_path: Path, mixer: FakeMixer, backoffs: list[float]
    ) -> None:
        """The quota is the engine's, not the line's: the lines still to send wait too."""
        busy = TTSProviderError("provider_rate_limited", retry_after_seconds=7.0)
        client = FakeClient(failures={SPOKEN_INTRO: [busy]})
        result, _ = await produce(tmp_path, client)
        assert result.outcome is ProductionOutcome.PRODUCED
        # The line that was refused waits, and so does every line sent after it.
        assert sum(1 for wait in backoffs if wait >= 6.0) >= 2

    async def test_a_mix_failure_leaves_no_file(self, tmp_path: Path, mixer: FakeMixer) -> None:
        mixer.fail = True
        result, ledger = await produce(tmp_path, FakeClient())
        assert result.outcome is ProductionOutcome.MIX_FAILED
        assert list(tmp_path.iterdir()) == []
        assert len(ledger.calls) == 3  # the voices were paid for all the same


class TestModelCheck:
    async def test_a_model_rejected_subject_intro_does_not_air_as_an_unnamed_dossier(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        request = replace(
            REQUEST,
            format=RadioFormat.DOSSIER,
            pack=FactPack(format=RadioFormat.DOSSIER, facts=PACK.facts),
        )
        drafted = ScriptDraft(
            title="The budget vote",
            lines=[
                line(ScriptPart.INTRO, LineKind.TRANSITION, "A closer look."),
                *[
                    line(ScriptPart.BODY, LineKind.FACT, "The parliament adopted the budget.", "n1")
                    for _ in range(5)
                ],
            ],
        )
        client = FakeClient()

        result, _ = await produce(
            tmp_path, client, draft=drafted, request=request, checker=FakeChecker(frozenset({0}))
        )

        assert (result.outcome, result.refusal) == (
            ProductionOutcome.SCRIPT_REFUSED,
            Refusal.SUBJECT_NOT_ANNOUNCED,
        )
        assert client.calls == []

    async def test_a_script_the_verifier_vouches_for_airs_whole(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        checker = FakeChecker(frozenset())
        result, _ = await produce(tmp_path, FakeClient(), checker=checker)
        assert result.outcome is ProductionOutcome.PRODUCED
        assert checker.shown == [
            (
                SPOKEN_INTRO,
                "The parliament adopted the budget by 312 votes.",
                "That was the brief.",
            )
        ]

    async def test_a_line_it_does_not_support_never_reaches_a_voice(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient()
        result, _ = await produce(tmp_path, client, checker=FakeChecker(frozenset({1})))
        assert (result.outcome, result.refusal) == (
            ProductionOutcome.SCRIPT_REFUSED,
            Refusal.NO_BODY,
        )
        assert client.calls == []

    async def test_a_check_that_could_not_run_airs_nothing(
        self, tmp_path: Path, mixer: FakeMixer
    ) -> None:
        client = FakeClient()
        result, ledger = await produce(tmp_path, client, checker=FakeChecker(None))
        assert result.outcome is ProductionOutcome.CHECK_FAILED
        assert client.calls == [] and ledger.calls == []


class TestLineFiles:
    async def test_a_cancelled_write_ends_before_the_cancellation_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A sibling line's failure cancels this one mid-write: the thread keeps
        # writing, so the cleanup that follows must not see a file still open.
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        real_write = Path.write_bytes

        def slow_write(self: Path, data: bytes) -> int:
            started.set()
            release.wait(5)
            written = real_write(self, data)
            finished.set()
            return written

        monkeypatch.setattr(Path, "write_bytes", slow_write)
        target = tmp_path / "segment.line00.mp3"
        task = asyncio.create_task(production_module._write_file(target, b"audio"))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done()  # still waiting for the write, never abandoning it
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert target.read_bytes() == b"audio"
