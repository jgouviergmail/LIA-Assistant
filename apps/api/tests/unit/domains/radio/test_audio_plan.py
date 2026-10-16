"""The mix plan: the voice alone — a breath before, a pause after every line, a longer one between parts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from src.domains.radio import audio as audio_module
from src.domains.radio.audio import (
    AudioAssemblyError,
    LineAudio,
    MixParams,
    VoicedLine,
    assemble_segment,
    plan_segment,
)
from src.domains.radio.script import ScriptPart
from src.infrastructure.media.ffmpeg import FfmpegError

pytestmark = pytest.mark.unit

OUT = Path("/out/segment.mp3")
P = MixParams()


def voiced(part: ScriptPart, index: int, seconds: float) -> VoicedLine:
    return VoicedLine(part, Path(f"/lines/{index}.wav"), seconds)


def filter_graph(args: tuple[str, ...]) -> str:
    return args[args.index("-filter_complex") + 1]


def windows(args: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Every windowed input: its start, its duration, its file."""
    return [
        (args[i + 1], args[i + 3], args[i + 5])
        for i, arg in enumerate(args)
        if arg == "-ss" and args[i + 2] == "-t" and args[i + 4] == "-i"
    ]


class TestTimeline:
    def test_every_line_starts_after_the_lines_and_the_pauses_before_it(self) -> None:
        lines = [
            voiced(ScriptPart.INTRO, 0, 3.0),
            voiced(ScriptPart.BODY, 1, 10.0),
            voiced(ScriptPart.BODY, 2, 5.0),
            voiced(ScriptPart.OUTRO, 3, 2.0),
        ]
        plan = plan_segment(lines, OUT, P)
        gap, breath = P.line_gap_s, P.line_gap_s + P.part_gap_s
        body = P.lead_in_s + 3.0 + breath
        outro = body + 10.0 + gap + 5.0 + breath
        assert plan.line_offsets_s == pytest.approx((P.lead_in_s, body, body + 10.0 + gap, outro))
        assert plan.duration_s == pytest.approx(outro + 2.0 + P.tail_s)

    def test_a_body_alone_is_a_whole_segment(self) -> None:
        plan = plan_segment([voiced(ScriptPart.BODY, 0, 8.0)], OUT, P)
        assert plan.line_offsets_s == (P.lead_in_s,)
        assert plan.duration_s == pytest.approx(P.lead_in_s + 8.0 + P.tail_s)

    def test_a_segment_without_a_body_is_refused(self) -> None:
        with pytest.raises(ValueError, match="body"):
            plan_segment([voiced(ScriptPart.INTRO, 0, 2.0)], OUT, P)


class TestGraph:
    def test_every_line_is_an_input_and_nothing_else_is(self) -> None:
        lines = [voiced(ScriptPart.INTRO, 0, 2.0), voiced(ScriptPart.BODY, 1, 5.0)]
        args = plan_segment(lines, OUT, P).args
        inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
        assert inputs == [str(Path("/lines/0.wav")), str(Path("/lines/1.wav"))]
        assert args[-1] == str(OUT)
        assert args[args.index("-map") + 1] == "[out]"
        assert args[args.index("-b:a") + 1] == f"{P.bitrate_kbps}k"

    def test_the_voice_waits_for_the_music_to_lower_and_is_normalised(self) -> None:
        lines = [voiced(ScriptPart.BODY, 0, 5.0), voiced(ScriptPart.OUTRO, 1, 2.0)]
        graph = filter_graph(plan_segment(lines, OUT, P).args)
        assert f"adelay=delays={round(P.lead_in_s * 1000)}:all=1" in graph
        assert f"apad=pad_dur={P.line_gap_s + P.part_gap_s:.3f}[l0]" in graph
        assert f"apad=pad_dur={P.tail_s:.3f}[l1]" in graph
        assert "concat=n=2:v=0:a=1" in graph
        assert "loudnorm=I=-16" in graph
        assert graph.endswith("[out]")

    @pytest.mark.parametrize(
        "broken",
        [
            pytest.param(lambda: MixParams(lead_in_s=0.0), id="lead_in_s"),
            pytest.param(lambda: MixParams(line_gap_s=-0.1), id="line_gap_s"),
            pytest.param(lambda: MixParams(part_gap_s=-0.1), id="part_gap_s"),
            pytest.param(lambda: MixParams(tail_s=-0.1), id="tail_s"),
        ],
    )
    def test_the_pauses_are_validated(self, broken: Callable[[], MixParams]) -> None:
        with pytest.raises(ValueError, match="pause"):
            broken()


class TestTakeWindows:
    """A dialogue take's lines are windows of one file (ADR-345)."""

    TAKE = Path("/lines/take.mp3")

    def test_a_window_is_decoded_from_its_start_for_its_duration_only(self) -> None:
        lines = [
            VoicedLine(ScriptPart.BODY, self.TAKE, 3.1, start_s=0.0),
            VoicedLine(ScriptPart.BODY, self.TAKE, 4.2, start_s=3.1),
        ]
        args = plan_segment(lines, OUT, P).args

        assert windows(args) == [
            ("0.000", "3.100", str(self.TAKE)),
            ("3.100", "4.200", str(self.TAKE)),
        ]

    def test_the_take_keeps_its_own_breath_between_turns(self) -> None:
        lines = [
            VoicedLine(ScriptPart.BODY, self.TAKE, 3.0, start_s=0.0),
            VoicedLine(ScriptPart.BODY, self.TAKE, 4.0, start_s=3.0),
            VoicedLine(ScriptPart.BODY, Path("/lines/alone.wav"), 2.0),
        ]
        plan = plan_segment(lines, OUT, P)

        # Nothing between two turns of the take; the usual gap after it.
        assert plan.line_offsets_s == pytest.approx(
            (P.lead_in_s, P.lead_in_s + 3.0, P.lead_in_s + 7.0 + P.line_gap_s)
        )
        graph = filter_graph(plan.args)
        assert "apad=pad_dur=0.000[l0]" in graph
        assert f"apad=pad_dur={P.line_gap_s:.3f}[l1]" in graph

    async def test_each_file_is_probed_once_and_a_window_runs_to_its_end(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        probed: list[str] = []

        async def probe(path: Path, *, timeout_s: float) -> float:
            probed.append(path.name)
            return 9.0

        captured: list[tuple[str, ...]] = []

        async def mix(args: tuple[str, ...], *, timeout_s: float) -> bytes:
            captured.append(args)
            Path(args[-1]).write_bytes(b"mp3")
            return b""

        monkeypatch.setattr(audio_module, "probe_duration", probe)
        monkeypatch.setattr(audio_module, "run_ffmpeg", mix)
        take = tmp_path / "s.take00.mp3"
        lines = [
            LineAudio(ScriptPart.BODY, take, start_s=0.0, end_s=2.5),
            LineAudio(ScriptPart.BODY, take, start_s=2.5, end_s=None),
        ]

        audio = await assemble_segment(lines, tmp_path / "s.mp3", timeout_s=5)

        assert probed.count(take.name) == 1
        assert windows(captured[0]) == [
            ("0.000", "2.500", str(take)),
            ("2.500", "6.500", str(take)),
        ]
        assert audio.line_offsets_s == pytest.approx((P.lead_in_s, P.lead_in_s + 2.5))

    async def test_a_window_holding_no_audio_is_a_failed_assembly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        async def probe(path: Path, *, timeout_s: float) -> float:
            return 2.0

        monkeypatch.setattr(audio_module, "probe_duration", probe)
        take = tmp_path / "s.take00.mp3"
        lines = [LineAudio(ScriptPart.BODY, take, start_s=3.0, end_s=None)]

        with pytest.raises(AudioAssemblyError):
            await assemble_segment(lines, tmp_path / "s.mp3", timeout_s=5)


class TestAssembly:
    @pytest.mark.parametrize("destination_exists", [False, True])
    async def test_cancelled_mix_removes_only_its_partial_and_propagates_cancellation(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, destination_exists: bool
    ) -> None:
        async def probe(path: Path, *, timeout_s: float) -> float:
            return 1.0

        async def mix(args: tuple[str, ...], *, timeout_s: float) -> bytes:
            Path(args[-1]).write_bytes(b"incomplete mp3")
            raise asyncio.CancelledError

        monkeypatch.setattr(audio_module, "probe_duration", probe)
        monkeypatch.setattr(audio_module, "run_ffmpeg", mix)
        out = tmp_path / "segment.mp3"
        if destination_exists:
            out.write_bytes(b"previous complete mp3")

        with pytest.raises(asyncio.CancelledError):
            await assemble_segment(
                [LineAudio(ScriptPart.BODY, tmp_path / "voice.wav")], out, timeout_s=5
            )

        assert not (tmp_path / "segment.part.mp3").exists()
        if destination_exists:
            assert out.read_bytes() == b"previous complete mp3"
        else:
            assert not out.exists()

    async def test_a_failed_probe_cancels_its_siblings_and_leaves_no_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        started: list[str] = []
        cancelled: list[str] = []

        async def probe(path: Path, *, timeout_s: float) -> float:
            started.append(path.name)
            if path.name == "bad.wav":
                raise FfmpegError("ffprobe failed", kind="failed")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(path.name)
                raise
            return 1.0

        monkeypatch.setattr(audio_module, "probe_duration", probe)
        out = tmp_path / "segment.mp3"
        lines = [
            LineAudio(ScriptPart.BODY, tmp_path / "slow.wav"),
            LineAudio(ScriptPart.BODY, tmp_path / "bad.wav"),
        ]
        with pytest.raises(AudioAssemblyError):
            await assemble_segment(lines, out, timeout_s=5)
        assert "slow.wav" in cancelled
        assert not out.exists() and not (tmp_path / "segment.part.mp3").exists()
