"""One segment from facts to audio: written, verified, voiced, billed, mixed — or why not."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domains.radio import production as production_module
from src.domains.radio.audio import AssembledAudio, AudioAssemblyError
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

    async def synthesize_base64(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> str:
        raise NotImplementedError


class FakeTokenClient(FakeClient):
    """A token-billed engine: it reports its usage."""

    async def synthesize_with_usage(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> SynthesisResult:
        audio = await self.synthesize(text, voice_name, **kwargs)
        return SynthesisResult(audio, len(text), input_tokens=9, output_tokens=350)


class Ledger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int | None, int | None]] = []

    def record_tts_call(
        self,
        provider: str,
        model: str,
        characters: int,
        duration_ms: float = 0.0,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.calls.append((provider, model, characters, input_tokens, output_tokens))


class FakeMixer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.received: list[tuple[ScriptPart, bytes]] = []

    async def __call__(
        self,
        lines: Sequence[tuple[ScriptPart, Path]],
        out: Path,
        *,
        timeout_s: float,
    ) -> AssembledAudio:
        self.received = [(part, path.read_bytes()) for part, path in lines]
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
