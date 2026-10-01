"""The landing video's beat map (ADR-330): which beats open a bar.

The bar phase is decided LOCALLY, never by a count from the start of the
piece: the tracker inserts or drops a beat in a breakdown, and a global
``i % 4`` then accents the wrong beat for the rest of the track (measured
2026-10-01 on the shipped video: the chunked vote won phase 0 over the first
55 s, phase 3 from 55 s to 253 s, phase 0 again at the end, with margins up to
64 % — a real accent, moved by the tracker's own insertions). A tie marks no
bar: a quarter stronger on an arbitrary beat is noise, not music.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

# The encoder lives at the REPOSITORY root (``scripts/assets``), not under
# ``apps/api/scripts``, which is what ``scripts.…`` resolves to from here.
_SCRIPT = Path(__file__).resolve().parents[5] / "scripts" / "assets" / "encode_landing_video.py"


def _load_encoder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("encode_landing_video", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE it runs: the script's frozen dataclass resolves its
    # string annotations through `sys.modules[cls.__module__]`, and an
    # unregistered module answers `None` there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


encoder = _load_encoder()
bar_flags = encoder.bar_flags
BAR_VOTE_MIN_MARGIN: float = encoder.BAR_VOTE_MIN_MARGIN

STRONG = 1.0
WEAK = 0.3


def _bars(count: int) -> list[float]:
    return [STRONG, WEAK, WEAK, WEAK] * count


def test_a_marked_pattern_opens_a_bar_every_four_beats() -> None:
    lows = _bars(12)
    flags = bar_flags(lows)
    assert flags == [low == STRONG for low in lows]


def test_a_beat_the_tracker_inserted_moves_the_bar_with_the_music() -> None:
    # Eight bars, one stray weak beat, eight bars: the strong beats keep their
    # place in the MUSIC while their index parity changes.
    lows = _bars(8) + [WEAK] + _bars(8)
    seam = 32
    flags = bar_flags(lows)
    for i, low in enumerate(lows):
        if abs(i - seam) > 8:
            assert flags[i] == (low == STRONG), f"beat {i}"
    assert 14 <= sum(flags) <= 17


def test_a_flat_pulse_marks_no_bar() -> None:
    assert not any(bar_flags([0.5] * 40))


def test_a_breakdown_carries_the_grid_a_while_then_opens_no_bar() -> None:
    # Eight marked bars, twelve bars where nobody plays the low band (a faint
    # accent on the SECOND beat, loud only in proportion), eight marked bars.
    quiet = [0.01, 0.02, 0.01, 0.01]
    lows = _bars(8) + quiet * 12 + _bars(8)
    flags = bar_flags(lows)
    # The grid continues into the breakdown while the window still sees the
    # kick: the accent that would have won on proportion alone is refused.
    assert flags[36] and flags[40] and flags[44]
    assert not any(flags[i] for i in range(49, 64)), "a window of silence opens no bar"
    # ...and resumes with the kick.
    assert flags[80] and flags[84]
    assert not any(flags[i] for i in range(33, 80) if lows[i] == 0.02)


def test_two_bars_never_open_within_two_beats() -> None:
    # A lone loud beat two beats after a bar: the margin is its own, the gap
    # refuses it.
    lows = _bars(10)
    lows[22] = STRONG
    flags = bar_flags(lows)
    assert flags[20] and not flags[22] and flags[24]


def test_a_near_tie_marks_no_bar() -> None:
    margin = BAR_VOTE_MIN_MARGIN / 2
    lows = [0.5 * (1 + margin), 0.5, 0.5, 0.5] * 10
    assert not any(bar_flags(lows))


def test_an_empty_map_has_no_bar() -> None:
    assert bar_flags([]) == []
