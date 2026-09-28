"""The antenna is fed just in time: never dry, never far ahead of a listener who may stop."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domains.radio.constants import LINE_MAX_CHARS, SPEECH_CHARS_PER_MINUTE
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.pacing import (
    Playhead,
    QueuedSegment,
    StageTimings,
    audio_ahead_s,
    must_produce_next,
    production_s,
    ran_late,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
TIMINGS = StageTimings(
    writer_s=6.0, analysis_s=15.0, tts_realtime_factor=0.4, tts_concurrency=3, mix_s=0.5
)


class TestAudioAhead:
    def test_the_rest_of_the_playing_segment_and_what_is_ready_after_it(self) -> None:
        queue = [QueuedSegment(1, 60.0, True), QueuedSegment(2, 90.0, True)]
        playhead = Playhead(seq=1, position_s=20.0, reported_at=NOW)
        assert audio_ahead_s(queue, playhead, NOW) == 130.0

    def test_audio_after_a_segment_in_production_is_not_continuous(self) -> None:
        queue = [
            QueuedSegment(1, 60.0, True),
            QueuedSegment(2, 90.0, False),
            QueuedSegment(3, 45.0, True),
        ]
        playhead = Playhead(seq=1, position_s=0.0, reported_at=NOW)
        assert audio_ahead_s(queue, playhead, NOW) == 60.0

    def test_the_player_keeps_going_between_two_reports(self) -> None:
        queue = [QueuedSegment(1, 60.0, True), QueuedSegment(2, 90.0, True)]
        playhead = Playhead(seq=1, position_s=50.0, reported_at=NOW)
        # 30 s later it is 20 s into segment 2, unreported: 70 s remain.
        assert audio_ahead_s(queue, playhead, NOW + timedelta(seconds=30)) == 70.0

    def test_a_paused_player_does_not_advance(self) -> None:
        queue = [QueuedSegment(1, 60.0, True)]
        playhead = Playhead(seq=1, position_s=10.0, reported_at=NOW, playing=False)
        assert audio_ahead_s(queue, playhead, NOW + timedelta(minutes=5)) == 50.0

    def test_instants_in_other_zones_are_compared_as_instants(self) -> None:
        queue = [QueuedSegment(1, 60.0, True)]
        paris = timezone(timedelta(hours=2))
        playhead = Playhead(seq=1, position_s=0.0, reported_at=NOW.astimezone(paris))
        assert audio_ahead_s(queue, playhead, NOW + timedelta(seconds=10)) == 50.0

    def test_a_silent_antenna_has_nothing_ahead(self) -> None:
        playhead = Playhead(seq=3, position_s=0.0, reported_at=NOW)
        assert audio_ahead_s([], playhead, NOW + timedelta(hours=1)) == 0.0

    def test_a_naive_report_is_refused(self) -> None:
        with pytest.raises(ValueError):
            Playhead(seq=1, position_s=0.0, reported_at=datetime(2026, 9, 26, 9, 0))


class TestProduction:
    def test_an_analysis_costs_its_analyst_call(self) -> None:
        brief = production_s(RadioFormat.BRIEF, TIMINGS, "fr")
        analysis = production_s(RadioFormat.ANALYSIS, TIMINGS, "fr")
        assert analysis > brief + TIMINGS.analysis_s

    def test_a_short_segment_waits_for_its_longest_line(self) -> None:
        # An opening voiced by three workers does not take a third of its
        # length: its one line is as long as the segment.
        target = FORMAT_SPECS[RadioFormat.OPENING].target_seconds
        opening = production_s(RadioFormat.OPENING, TIMINGS, "fr")
        assert opening == pytest.approx(6.0 + target * 0.4 + 0.5)

    def test_a_long_segment_is_voiced_in_parallel(self) -> None:
        target = FORMAT_SPECS[RadioFormat.BULLETIN].target_seconds
        longest_line_s = LINE_MAX_CHARS / (SPEECH_CHARS_PER_MINUTE["fr"] / 60)
        assert target / 3 > longest_line_s  # long enough for the workers to share it
        bulletin = production_s(RadioFormat.BULLETIN, TIMINGS, "fr")
        assert bulletin == pytest.approx(6.0 + target * 0.4 / 3 + 0.5)

    def test_an_unknown_language_is_sized_like_english(self) -> None:
        assert production_s(RadioFormat.BULLETIN, TIMINGS, "pt") == production_s(
            RadioFormat.BULLETIN, TIMINGS, "en"
        )

    def test_what_the_session_saw_its_productions_overrun_is_expected_of_every_format(
        self,
    ) -> None:
        late = replace(TIMINGS, lateness_s=40.0)
        for fmt in (RadioFormat.BRIEF, RadioFormat.DOSSIER, RadioFormat.FLASH):
            assert production_s(fmt, late, "fr") == pytest.approx(
                production_s(fmt, TIMINGS, "fr") + 40.0
            )


class TestLateness:
    """The stage timings are an instance's guess; the session learns its own
    (measured 2026-09-27: a writer slot that thinks writes a programme in 15 to
    65 s where the instance expected 12, and a half-hour heard a minute of music
    alone waiting for the next programme)."""

    def test_a_production_later_than_expected_teaches_by_how_much(self) -> None:
        assert ran_late(0.0, observed_s=70.0, expected_s=30.0) == 40.0

    def test_the_most_a_session_has_seen_stays(self) -> None:
        assert ran_late(40.0, observed_s=45.0, expected_s=30.0) == 40.0
        assert ran_late(40.0, observed_s=90.0, expected_s=30.0) == 60.0

    def test_a_production_on_time_or_early_teaches_nothing(self) -> None:
        assert ran_late(0.0, observed_s=12.0, expected_s=30.0) == 0.0
        assert ran_late(25.0, observed_s=30.0, expected_s=30.0) == 25.0


def test_the_next_segment_starts_once_the_air_ahead_no_longer_covers_it() -> None:
    assert must_produce_next(40.0, 30.0, safety=1.5, margin_s=10.0) is True
    assert must_produce_next(80.0, 30.0, safety=1.5, margin_s=10.0) is False
