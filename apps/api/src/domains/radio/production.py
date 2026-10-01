"""One segment, from its facts to its mixed audio.

The grid chose the format and the editor gathered the facts; the rest runs the
same way for every format:

1. WRITE — the writer (a model, behind :class:`ScriptWriter`) turns the facts
   into a script;
2. VERIFY — the deterministic verifier keeps what the facts support and refuses
   a script it would have to rewrite; when the listener asked for it, a model
   then reads every sourced line against the facts it cites, and what it cannot
   support is dropped under the same refusal rules — a check that could not run
   airs nothing, since airing it unchecked is what the listener asked not to hear;
3. VOICE — every kept line is spoken by the cast's voice for its role, with the
   delivery the writer asked for; lines are voiced in parallel under a bound and
   every paid call is billed to the listener through the ledger (a free engine
   records nothing, as the tracker's contract says);
4. MIX — the lines are joined, with their pauses, and loudness-normalised; the
   station's music is the player's, under the whole session.

Out comes the audio file, its duration and a TRANSCRIPT: every line with where
it starts in the audio and the sources it rests on — what the player shows under
the voice, so a listener can always see where a sentence comes from.

A segment that cannot be produced says why with a bounded outcome (a metric
label) and the antenna moves on; only a defect raises. The lines' temporary
files never outlive the call. A synthesis cancelled in flight (the listener
stopped) is not recorded: no usage report exists for it, and a guess would
bill a call that may never have been completed.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from src.core.exceptions import MaxRetriesExceededError
from src.domains.radio.aired import HeardLine
from src.domains.radio.audio import AudioAssemblyError, assemble_segment
from src.domains.radio.cast import Cast
from src.domains.radio.constants import TTS_RATE_LIMIT_BASE_WAIT_SECONDS
from src.domains.radio.delivery import StylePhrases, delivery_kwargs
from src.domains.radio.facts import FactPack, SourceRef
from src.domains.radio.formats import JournalEdition, RadioFormat, RadioRole
from src.domains.radio.script import ScriptDraft, ScriptPart
from src.domains.radio.verification import (
    Refusal,
    VerificationResult,
    VerifiedLine,
    Violation,
    announce_subject,
    drop_unsupported,
    verify_script,
)
from src.domains.voice.billing import SynthesisResult, synthesize_billed
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.families import TtsBilling, family_of
from src.domains.voice.protocol import TTSClient
from src.infrastructure.utils.retry import retry_async


@dataclass(frozen=True, slots=True)
class WritingRequest:
    """Everything the writer is given for one segment.

    Attributes:
        format: The programme to write.
        pack: The facts it may voice.
        language: The listener's language (backend-canonical code).
        local_now: The listener's local time when the segment airs.
        station_id: Whether the segment must name the station.
        station_name: The station's name — any line may say it, and a mention
            of it states none of its numbers (a station called « Radio 42 »).
        clock_mark: The hour or mark it is announced as (a bulletin « at nine »).
        previous: The programme before it, for the way in.
        following: The programme after it when its audio is already ready, to announce it.
        listener_name: How the host may address the listener, if at all.
        on_air: The titles of the news programmes this session already aired,
            oldest first — what a news writer must not tell again.
        roles: The roles that speak — the format's, less a commentator the cast
            could not give a voice of its own (``Cast.voiced_roles``); empty for
            the format's own.
        edition: The journal's edition, for the journal alone (ADR-324 decision 41):
            decided once from the programme's air time, read by the desk that chose
            the facts and by the writer alike.
    """

    format: RadioFormat
    pack: FactPack
    language: str
    local_now: datetime
    station_id: bool
    station_name: str
    clock_mark: datetime | None = None
    previous: RadioFormat | None = None
    following: RadioFormat | None = None
    listener_name: str | None = None
    on_air: tuple[str, ...] = ()
    roles: tuple[RadioRole, ...] = ()
    edition: JournalEdition | None = None

    def __post_init__(self) -> None:
        if (self.format is RadioFormat.JOURNAL) != (self.edition is not None):
            raise ValueError("the journal carries its edition, and no other programme does")


class ScriptWriter(Protocol):
    """Writes a segment's script; ``None`` when no usable script came back."""

    async def write(self, request: WritingRequest) -> ScriptDraft | None:
        """Write the script for ``request``."""
        ...


class LineChecker(Protocol):
    """The model verifier: which lines the facts they cite do not support."""

    async def unsupported(
        self, lines: Sequence[VerifiedLine], pack: FactPack
    ) -> frozenset[int] | None:
        """Places in ``lines`` not supported; ``None`` when no usable verdict came back."""
        ...


class TtsLedger(Protocol):
    """Where a paid synthesis is billed (the tracker of the session's run)."""

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
        """Record one synthesis."""
        ...


@dataclass(frozen=True, slots=True)
class VoiceEngine:
    """The voice engine the radio speaks with.

    The provider and the audio container are the client's own statements,
    never restated beside it.

    Attributes:
        client: The TTS client.
        model: Its model, as the tariff table names it.
        phrases: The style phrases for an engine directed in words.
        base_voice_settings: The administrator's settings a delivery adjusts.
    """

    client: TTSClient
    model: str
    phrases: StylePhrases
    base_voice_settings: Mapping[str, Any] | None = None

    @property
    def provider(self) -> str:
        """The provider (a key of the voice families)."""
        return self.client.provider_name

    @property
    def billable(self) -> bool:
        """Whether a synthesis is billed (an unknown family is, to be safe)."""
        family = family_of(self.provider)
        return family is None or family.billing is not TtsBilling.FREE


@dataclass(frozen=True, slots=True)
class ProductionLimits:
    """The bounds of one production.

    Attributes:
        quote_max_chars: The longest quotation the verifier lets through.
        tts_concurrency: Lines voiced at once.
        mix_timeout_s: The mix's deadline.
        tts_attempts: Attempts per line while its failure is transient
            (1 = never tried again).
        tts_rate_limit_wait_max_s: The longest a line waits after a
            provider's rate limit.
    """

    quote_max_chars: int
    tts_concurrency: int
    mix_timeout_s: float
    tts_attempts: int
    tts_rate_limit_wait_max_s: float


class ProductionOutcome(StrEnum):
    """How a production ended — a bounded vocabulary (a metric label)."""

    PRODUCED = "produced"
    WRITER_REFUSED = "writer_refused"
    SCRIPT_REFUSED = "script_refused"
    CHECK_FAILED = "check_failed"
    VOICE_FAILED = "voice_failed"
    MIX_FAILED = "mix_failed"


@dataclass(frozen=True, slots=True)
class TranscriptLine:
    """One spoken line, where it starts and what it rests on."""

    role: RadioRole
    text: str
    offset_s: float
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class VoicedLine:
    """A line as it airs: where it starts in its segment, and the facts it cites (each once)."""

    offset_s: float
    refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProducedSegment:
    """A segment ready to air.

    Attributes:
        title: The programme title shown to the listener.
        audio_path: The mixed audio.
        duration_s: Its duration.
        transcript: The lines, in air order, with their offsets and sources.
        dropped_lines: Lines the verifier dropped (counted, never voiced).
        unrendered: Delivery qualities the engine could not express.
        memory: What each line tells the listener, in air order — the server's
            own, filed as heard once the player has passed the line (ADR-324
            decision 35), never sent to the player.
    """

    title: str
    audio_path: Path
    duration_s: float
    transcript: tuple[TranscriptLine, ...]
    dropped_lines: int
    unrendered: tuple[str, ...]
    memory: tuple[HeardLine, ...] = ()


@dataclass(frozen=True, slots=True)
class NothingAired:
    """A production that ended with nothing to air, and nothing broken.

    Nothing to say, or a script its editor refused: the station worked and
    chose silence over a programme it cannot stand behind. Unlike a failure
    it says nothing of the station's health — its format rests, and the stop
    on failures never counts it (ADR-324 decision 33).

    Attributes:
        outcome: How it ended (the metric's outcome label).
    """

    outcome: str

    def __bool__(self) -> bool:
        """Falsy, like the ``None`` of a failure: nothing aired either way."""
        return False


@dataclass(frozen=True, slots=True)
class ProductionResult:
    """What a production gave: a segment, or why there is none.

    Attributes:
        outcome: How it ended.
        segment: The segment, when produced.
        refusal: Why the verifier refused the script, when it did.
        dropped: Why each dropped line went, when a script was refused — the
            rule's code, never the line (a refusal named alone cannot say why).
        error_code: The voice provider's code, when a voice failed.
        lines: The voiced lines, in air order: where each starts and the facts
            it cites — what the listener hears as the player passes them, never
            the whole pack the writer chose from.
    """

    outcome: ProductionOutcome
    segment: ProducedSegment | None = None
    refusal: Refusal | None = None
    dropped: tuple[Violation, ...] = ()
    error_code: str | None = None
    lines: tuple[VoicedLine, ...] = ()

    @property
    def aired(self) -> tuple[str, ...]:
        """The facts the voiced lines cite, first cited first."""
        return tuple(dict.fromkeys(ref for line in self.lines for ref in line.refs))


async def _write_file(path: Path, data: bytes) -> None:
    """Write a line's audio off the loop, and never leave the write behind.

    A thread cannot be cancelled. When a sibling line fails, the task group
    cancels this one while its bytes may still be going to disk; returning at
    once would let the segment's cleanup race the write — Windows refuses to
    unlink a file still open (measured: a red unit test), and elsewhere the
    write recreates the file after its removal. So a cancellation waits for the
    write to end, then propagates.
    """
    write = asyncio.ensure_future(asyncio.to_thread(path.write_bytes, data))
    try:
        await asyncio.shield(write)
    except asyncio.CancelledError:
        await asyncio.wait({write})
        if not write.cancelled():
            # Read so a failed write is never reported as an unretrieved error;
            # the cancellation is what this task answers.
            write.exception()
        raise


def _remove(paths: Sequence[Path]) -> None:
    for path in paths:
        # Best effort: a file already gone is exactly the state wanted.
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


@dataclass(slots=True)
class _Cooldown:
    """A quota one line runs into holds back every line of its segment.

    The quota is the engine's, not the line's: a line sent while another waits
    out a rate limit meets the same refusal and spends an attempt on it.
    """

    until: float = 0.0

    async def honour(self) -> None:
        wait = self.until - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

    def hold(self, seconds: float) -> None:
        self.until = max(self.until, time.monotonic() + seconds)


def _rate_limit_wait(error: Exception, attempt: int, *, max_s: float) -> float | None:
    """How long a line refused on a quota waits; ``None`` for any other failure.

    The provider's own delay when it names one, else a backoff that outlasts a
    burst — never beyond ``max_s``.
    """
    if not (isinstance(error, TTSProviderError) and error.rate_limited):
        return None
    named = error.retry_after_seconds
    wait = named if named is not None else TTS_RATE_LIMIT_BASE_WAIT_SECONDS * 2**attempt
    return min(max(wait, 0.0), max_s)


async def _voice_line(
    line: VerifiedLine,
    path: Path,
    *,
    engine: VoiceEngine,
    cast: Cast,
    ledger: TtsLedger,
    gate: asyncio.Semaphore,
    cooldown: _Cooldown,
    limits: ProductionLimits,
) -> tuple[str, ...]:
    rendered = delivery_kwargs(
        engine.provider,
        line.role,
        line.delivery,
        model=engine.model,
        phrases=engine.phrases,
        base_voice_settings=engine.base_voice_settings,
    )

    def wait_for(error: Exception, attempt: int) -> float | None:
        return _rate_limit_wait(error, attempt, max_s=limits.tts_rate_limit_wait_max_s)

    async def attempt() -> tuple[SynthesisResult, float]:
        # The gate is held per ATTEMPT: a line waiting to try again leaves its
        # slot to the others — which wait out a quota inside the gate, so no
        # line is sent while one is being refused.
        async with gate:
            await cooldown.honour()
            started = time.perf_counter()
            try:
                result = await synthesize_billed(
                    engine.client, line.text, cast.voices[line.role], **rendered.kwargs
                )
            except TTSProviderError as error:
                held = wait_for(error, 0)
                if held is not None:
                    cooldown.hold(held)
                raise
            return result, (time.perf_counter() - started) * 1000

    result, elapsed_ms = await _until_voiced(attempt, limits.tts_attempts, wait_for)
    if engine.billable:
        ledger.record_tts_call(
            engine.provider,
            engine.model,
            result.characters,
            elapsed_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    await _write_file(path, result.audio)
    return rendered.unrendered


def _transient(error: Exception) -> bool:
    return isinstance(error, TTSProviderError) and error.transient


async def _until_voiced(
    attempt: Callable[[], Awaitable[tuple[SynthesisResult, float]]],
    attempts: int,
    wait_for: Callable[[Exception, int], float | None],
) -> tuple[SynthesisResult, float]:
    """One line's synthesis, tried again while its failure is transient.

    Measured 2026-09-26: the free engine answers without audio once in
    twenty-four syntheses, so at fourteen lines about one segment in two was
    lost to a failure a second attempt outlives. A refusal on a QUOTA waits what
    the provider asks, or a backoff that outlasts a burst (``wait_for``). The
    last failure is raised as itself, so the segment's outcome names its code.
    """
    try:
        return await retry_async(
            attempt,
            max_retries=attempts,
            retryable_exceptions=(TTSProviderError,),
            retry_if=_transient,
            operation_name="radio_line_synthesis",
            delay_for=wait_for,
        )
    except MaxRetriesExceededError as exhausted:
        failure = exhausted.last_error
        if isinstance(failure, TTSProviderError):
            # Raised as itself with the provider's own cause: ``from None``
            # would erase it, a bare ``raise`` would chain it to the wrapper.
            raise failure from failure.__cause__
        raise


def _first_code(group: BaseExceptionGroup[TTSProviderError]) -> str | None:
    leaves = [error for error in group.exceptions if isinstance(error, TTSProviderError)]
    return leaves[0].code if leaves else None


def _transcript(
    lines: Sequence[VerifiedLine], offsets: Sequence[float], pack: FactPack
) -> tuple[TranscriptLine, ...]:
    facts = pack.by_id()
    transcript: list[TranscriptLine] = []
    for line, offset in zip(lines, offsets, strict=True):
        sources: list[SourceRef] = []
        for ref in line.refs:
            source = facts[ref].source if ref in facts else None
            if source is not None and source not in sources:
                sources.append(source)
        transcript.append(TranscriptLine(line.role, line.text, offset, tuple(sources)))
    return tuple(transcript)


async def _checked_script(
    draft: ScriptDraft,
    request: WritingRequest,
    *,
    limits: ProductionLimits,
    checker: LineChecker | None,
) -> VerificationResult | ProductionResult:
    """The script the voices may speak, or the outcome saying why there is none.

    The deterministic verifier first; then, when the listener's setting checks
    this format, the model verifier, whose verdict is judged by the SAME
    refusal rules. A check that could not run airs nothing.
    """
    verified = verify_script(
        draft,
        request.pack,
        language=request.language,
        quote_max_chars=limits.quote_max_chars,
        station_name=request.station_name,
        roles=request.roles,
    )
    if not verified.accepted:
        return _refused(verified)
    if checker is None:
        return verified
    flagged = await checker.unsupported(verified.lines, request.pack)
    if flagged is None:
        return ProductionResult(ProductionOutcome.CHECK_FAILED)
    verified = drop_unsupported(draft, request.pack, verified, flagged, language=request.language)
    if not verified.accepted:
        return _refused(verified)
    return verified


def _refused(verified: VerificationResult) -> ProductionResult:
    """A refused script's outcome, with the rule of every line it lost."""
    return ProductionResult(
        ProductionOutcome.SCRIPT_REFUSED,
        refusal=verified.refusal,
        dropped=tuple(violation for _, violation in verified.dropped),
    )


async def produce_segment(
    request: WritingRequest,
    out: Path,
    *,
    writer: ScriptWriter,
    engine: VoiceEngine,
    cast: Cast,
    ledger: TtsLedger,
    limits: ProductionLimits,
    checker: LineChecker | None = None,
) -> ProductionResult:
    """Write, verify, voice and mix one segment.

    Args:
        request: What to write.
        out: Where the mixed audio goes; its directory must exist and holds
            the line files while the segment is voiced.
        writer: The script writer.
        engine: The voice engine.
        cast: The voice of every role.
        ledger: Where every paid synthesis is billed.
        limits: The production's bounds.
        checker: The model verifier, when the listener's setting checks this
            format.

    Returns:
        The segment, or the outcome saying why there is none.
    """
    written = await writer.write(request)
    if written is None:
        return ProductionResult(ProductionOutcome.WRITER_REFUSED)
    draft = announce_subject(written, request.pack)
    verified = await _checked_script(draft, request, limits=limits, checker=checker)
    if isinstance(verified, ProductionResult):
        return verified
    if draft is not written and (
        not verified.lines
        or verified.lines[0].part is not ScriptPart.INTRO
        or verified.title.casefold() not in verified.lines[0].text.casefold()
    ):
        return ProductionResult(
            ProductionOutcome.SCRIPT_REFUSED,
            refusal=Refusal.SUBJECT_NOT_ANNOUNCED,
            dropped=tuple(violation for _, violation in verified.dropped),
        )

    paths = [
        out.with_name(f"{out.stem}.line{index:02d}.{engine.client.audio_format}")
        for index in range(len(verified.lines))
    ]
    gate = asyncio.Semaphore(max(1, limits.tts_concurrency))
    cooldown = _Cooldown()
    # ``return`` is not allowed inside ``except*``: the failure is kept there
    # and answered after it. Anything but a provider failure is a defect and
    # propagates (the line files are removed on the way out all the same).
    voice_failure: BaseExceptionGroup[TTSProviderError] | None = None
    try:
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(
                        _voice_line(
                            line,
                            path,
                            engine=engine,
                            cast=cast,
                            ledger=ledger,
                            gate=gate,
                            cooldown=cooldown,
                            limits=limits,
                        )
                    )
                    for line, path in zip(verified.lines, paths, strict=True)
                ]
        except* TTSProviderError as errors:
            voice_failure = errors
        if voice_failure is not None:
            return ProductionResult(
                ProductionOutcome.VOICE_FAILED, error_code=_first_code(voice_failure)
            )
        parts: list[tuple[ScriptPart, Path]] = [
            (line.part, path) for line, path in zip(verified.lines, paths, strict=True)
        ]
        try:
            audio = await assemble_segment(parts, out, timeout_s=limits.mix_timeout_s)
        except AudioAssemblyError:
            return ProductionResult(ProductionOutcome.MIX_FAILED)
    finally:
        await asyncio.to_thread(_remove, paths)

    unrendered = tuple(sorted({quality for task in tasks for quality in task.result()}))
    return ProductionResult(
        ProductionOutcome.PRODUCED,
        segment=ProducedSegment(
            title=verified.title,
            audio_path=out,
            duration_s=audio.duration_s,
            transcript=_transcript(verified.lines, audio.line_offsets_s, request.pack),
            dropped_lines=len(verified.dropped),
            unrendered=unrendered,
        ),
        lines=tuple(
            VoicedLine(offset_s=offset, refs=tuple(dict.fromkeys(line.refs)))
            for line, offset in zip(verified.lines, audio.line_offsets_s, strict=True)
        ),
    )


__all__ = [
    "LineChecker",
    "NothingAired",
    "ProducedSegment",
    "ProductionLimits",
    "ProductionOutcome",
    "ProductionResult",
    "ScriptWriter",
    "TranscriptLine",
    "TtsLedger",
    "VoiceEngine",
    "VoicedLine",
    "WritingRequest",
    "produce_segment",
]
