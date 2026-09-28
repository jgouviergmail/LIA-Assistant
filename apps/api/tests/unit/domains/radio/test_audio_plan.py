"""The mix plan: the voice alone — a breath before, a pause after every line, a longer one between parts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from src.domains.radio import audio as audio_module
from src.domains.radio.audio import (
    AudioAssemblyError,
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


class TestAssembly:
    async def test_a_failed_probe_cancels_its_siblings_and_leaves_no_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        started: list[str] = []
        cancelled: list[str] = []

        async def probe(path: Path, *, timeout_s: float) -> float:
            started.append(path.name)
            if path.name == "bad.wav":
                raise FfmpegError("ffprobe failed")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(path.name)
                raise
            return 1.0

        monkeypatch.setattr(audio_module, "probe_duration", probe)
        out = tmp_path / "segment.mp3"
        lines = [(ScriptPart.BODY, tmp_path / "slow.wav"), (ScriptPart.BODY, tmp_path / "bad.wav")]
        with pytest.raises(AudioAssemblyError):
            await assemble_segment(lines, out, timeout_s=5)
        assert "slow.wav" in cancelled
        assert not out.exists() and not (tmp_path / "segment.part.mp3").exists()
