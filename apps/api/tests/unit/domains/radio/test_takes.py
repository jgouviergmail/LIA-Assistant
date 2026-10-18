"""Which lines of a segment are voiced together as one dialogue take (ADR-345).

A take keeps the voices of one exchange in one recording; its bounds are what
makes it safe: one part, one set of controls (a request carries one speaking
rate), a byte ceiling so a failure never costs a whole debate.
"""

from __future__ import annotations

import pytest

from src.domains.radio.script import ScriptPart
from src.domains.radio.takes import TakeLine, plan_takes

pytestmark = pytest.mark.unit

BODY = ScriptPart.BODY


def said(
    voice: str, words: str = "Une phrase.", *, part: ScriptPart = BODY, speed: float = 1.0
) -> TakeLine:
    return TakeLine(part=part, voice=voice, spoken=words, controls={"speed": speed})


def test_an_exchange_of_one_part_is_one_take() -> None:
    lines = [said("anchor"), said("expert"), said("anchor"), said("expert")]

    assert plan_takes(lines, max_bytes=1500) == [(0, 1, 2, 3)]


def test_a_segment_one_voice_reads_keeps_its_lines_apart() -> None:
    lines = [said("anchor"), said("anchor"), said("anchor")]

    assert plan_takes(lines, max_bytes=1500) == [(0,), (1,), (2,)]


def test_a_zero_ceiling_voices_every_line_alone() -> None:
    assert plan_takes([said("a"), said("b")], max_bytes=0) == [(0,), (1,)]


def test_a_take_never_crosses_a_part() -> None:
    lines = [
        said("anchor", part=ScriptPart.INTRO),
        said("anchor", part=ScriptPart.BODY),
        said("expert", part=ScriptPart.BODY),
        said("anchor", part=ScriptPart.OUTRO),
    ]

    assert plan_takes(lines, max_bytes=1500) == [(0,), (1, 2), (3,)]


def test_one_request_carries_one_speaking_rate() -> None:
    lines = [said("a"), said("b"), said("a", speed=1.1), said("b", speed=1.1)]

    assert plan_takes(lines, max_bytes=1500) == [(0, 1), (2, 3)]


def test_the_ceiling_counts_utf8_bytes_and_starts_a_new_take() -> None:
    chinese = "交通罢工将持续到明天早上。"  # 13 characters, 39 bytes
    lines = [said("a", chinese), said("b", chinese), said("a", chinese)]

    assert plan_takes(lines, max_bytes=2 * len(chinese.encode("utf-8"))) == [(0, 1), (2,)]


def test_a_line_longer_than_any_take_is_voiced_alone() -> None:
    lines = [said("a", "x" * 50), said("b", "y" * 200), said("a", "z" * 50)]

    assert plan_takes(lines, max_bytes=120) == [(0,), (1,), (2,)]


def test_a_line_with_nothing_to_say_is_never_part_of_a_take() -> None:
    lines = [said("a"), said("b", "[serious] …"), said("a"), said("b")]

    assert plan_takes(lines, max_bytes=1500) == [(0,), (1,), (2, 3)]


def test_a_take_never_carries_more_voices_than_the_engine_takes() -> None:
    """Production 2026-10-17: a debate take of four voices was refused whole (400)."""
    lines = [said(voice) for voice in ("anchor", "a", "b", "c", "a", "b", "anchor")]

    assert plan_takes(lines, max_bytes=1500, max_voices=3) == [(0, 1, 2), (3, 4, 5), (6,)]


def test_an_engine_declaring_no_voice_limit_keeps_one_take() -> None:
    lines = [said(voice) for voice in ("anchor", "a", "b", "c", "a")]

    assert plan_takes(lines, max_bytes=1500, max_voices=None) == [(0, 1, 2, 3, 4)]
