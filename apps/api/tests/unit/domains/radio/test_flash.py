"""A news flash: LIA breaks into the programme to say what she just wrote in the chat."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio.flash import (
    FLASH_NOTES_MAX,
    FLASH_SEQ_BASE,
    Flash,
    FlashNote,
    flash_allowed,
    flash_failed,
    flash_produced,
    flash_started,
    flash_watermark,
    flashes_heard,
    is_flash_seq,
    pending_flash,
    what_it_cuts,
    what_resumes,
)
from src.domains.radio.formats import Frequency, RadioFormat
from src.domains.radio.pacing import Playhead
from src.domains.radio.packs import Desk
from src.domains.radio.programme import Slot
from src.domains.radio.session import EndReason, SessionState
from tests.unit.domains.radio.fakes import voices_by_format

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def slot(seq: int, fmt: RadioFormat, *, reported: bool = False) -> Slot:
    return Slot(
        seq=seq,
        format=fmt,
        station_id=seq == 1,
        air_at=NOW + timedelta(seconds=30 * (seq - 1)),
        duration_s=30.0,
        reported=reported,
    )


ON_AIR = Playhead(seq=1, position_s=12.0, reported_at=NOW, playing=True)


def on_air(
    *,
    slots: tuple[Slot, ...] = (
        slot(1, RadioFormat.OPENING, reported=True),
        slot(2, RadioFormat.BRIEF),
    ),
    produced: frozenset[int] = frozenset({1, 2}),
    playhead: Playhead = ON_AIR,
    paused_since: datetime | None = None,
    ended: EndReason | None = None,
    flashes: tuple[Flash, ...] = (),
) -> SessionState:
    """A session the listener hears: 12 s into a 30 s opening, a brief ready next."""
    return SessionState(
        started_at=NOW - timedelta(minutes=1),
        stop_at=None,
        slots=slots,
        produced=produced,
        playhead=playhead,
        paused_since=paused_since,
        ended=ended,
        flashes=flashes,
    )


def note(ident: str = "m1", *, minutes: int = 1) -> FlashNote:
    return FlashNote(
        id=ident, sent_at=NOW + timedelta(minutes=minutes), topic="interest", excerpt="Hello."
    )


class TestWhenAFlashMayStart:
    def test_while_the_listener_hears_the_antenna(self) -> None:
        assert flash_allowed(on_air())

    def test_never_before_the_first_sound(self) -> None:
        silent = on_air(slots=(slot(1, RadioFormat.OPENING), slot(2, RadioFormat.BRIEF)))
        assert not flash_allowed(silent)

    def test_never_while_the_listener_paused(self) -> None:
        assert not flash_allowed(on_air(paused_since=NOW))

    def test_never_once_the_farewell_is_planned(self) -> None:
        farewell = on_air(
            slots=(slot(1, RadioFormat.OPENING, reported=True), slot(2, RadioFormat.SIGN_OFF))
        )
        assert not flash_allowed(farewell)

    def test_never_once_ended(self) -> None:
        assert not flash_allowed(on_air(ended=EndReason.LISTENER))

    def test_one_at_a_time(self) -> None:
        assert not flash_allowed(on_air(flashes=(Flash(seq=FLASH_SEQ_BASE + 1, notes=("m1",)),)))


class TestAFlashsLife:
    def test_the_watermark_starts_at_the_session_start(self) -> None:
        state = on_air()
        assert flash_watermark(state) == state.started_at

    def test_it_takes_the_next_number_and_the_newest_note_as_its_watermark(self) -> None:
        state, flash = flash_started(on_air(), [note("m1", minutes=1), note("m2", minutes=3)])
        assert flash == Flash(seq=FLASH_SEQ_BASE + 1, notes=("m1", "m2"))
        assert state.flashes == (flash,)
        assert state.flashes_made == 1
        assert flash_watermark(state) == NOW + timedelta(minutes=3)
        assert is_flash_seq(flash.seq) and not is_flash_seq(2)

    def test_the_second_flash_of_a_session_takes_the_number_after_the_first(self) -> None:
        state, first = flash_started(on_air(), [note("m1")])
        state = flashes_heard(flash_produced(state, first.seq, duration_s=20.0), first.seq)
        _, second = flash_started(state, [note("m2", minutes=5)])
        assert second.seq == FLASH_SEQ_BASE + 2

    def test_it_tells_a_bounded_number_of_notes(self) -> None:
        many = [note(f"m{i}", minutes=i) for i in range(1, FLASH_NOTES_MAX + 3)]
        with pytest.raises(ValueError, match="at most"):
            flash_started(on_air(), many)

    def test_a_produced_flash_waits_to_be_heard_and_counts_as_radio_produced(self) -> None:
        state, flash = flash_started(on_air(), [note()])
        assert pending_flash(state) is None
        state = flash_produced(state, flash.seq, duration_s=24.5)
        assert pending_flash(state) == replace(flash, produced=True)
        assert state.flash_audio_s == 24.5

    def test_a_flash_the_player_heard_leaves_the_state(self) -> None:
        state, flash = flash_started(on_air(), [note()])
        state = flash_produced(state, flash.seq, duration_s=20.0)
        assert flashes_heard(state, flash.seq).flashes == ()

    def test_a_report_of_an_older_flash_leaves_the_newer_one(self) -> None:
        state, flash = flash_started(on_air(), [note()])
        state = flash_produced(state, flash.seq, duration_s=20.0)
        assert flashes_heard(state, flash.seq - 1).flashes == state.flashes
        assert flashes_heard(state, 0) is state

    def test_a_flash_still_in_production_cannot_have_been_heard(self) -> None:
        state, flash = flash_started(on_air(), [note()])
        assert flashes_heard(state, flash.seq).flashes == state.flashes

    def test_a_flash_that_could_not_be_produced_leaves_the_state(self) -> None:
        state, flash = flash_started(on_air(), [note()])
        failed = flash_failed(state, flash.seq)
        assert failed.flashes == ()
        # Its notes are not taken again: they stay in the chat, where the
        # personal corner may still come back to them.
        assert flash_watermark(failed) == flash_watermark(state)


class TestWhatTheFlashCuts:
    """Written when it starts, heard when it is ready: it names only what is certain then."""

    def test_the_programme_on_air_is_cut_and_resumes_while_enough_of_it_is_left(self) -> None:
        state = on_air()  # 18 s of the opening left
        cuts = what_it_cuts(state, now=NOW, ready_in_s=10.0)
        assert cuts is RadioFormat.OPENING
        assert what_resumes(state, cuts) is RadioFormat.OPENING

    def test_a_programme_over_before_the_flash_is_ready_is_not_named(self) -> None:
        """Measured 2026-09-27: written over the welcome, heard after it, the flash
        said « back to the welcome »."""
        state = on_air()
        # Reported 5 s ago: 13 s of the opening left, the flash is ready in 15.
        cuts = what_it_cuts(state, now=NOW + timedelta(seconds=5), ready_in_s=15.0)
        assert cuts is None
        assert what_resumes(state, cuts) is RadioFormat.BRIEF  # ready: it airs next

    def test_between_two_programmes_nothing_is_cut_and_the_ready_one_follows(self) -> None:
        waiting = on_air(playhead=Playhead(seq=2, position_s=0.0, reported_at=NOW, playing=False))
        cuts = what_it_cuts(waiting, now=NOW, ready_in_s=10.0)
        assert cuts is None
        assert what_resumes(waiting, cuts) is RadioFormat.BRIEF

    def test_a_programme_still_in_production_is_never_named(self) -> None:
        """It may never air: its production can fail, or say nothing."""
        waiting = on_air(
            produced=frozenset({1}),
            playhead=Playhead(seq=2, position_s=0.0, reported_at=NOW, playing=False),
        )
        assert what_resumes(waiting, None) is None

    def test_a_place_the_running_order_no_longer_holds_names_nothing(self) -> None:
        lost = on_air(playhead=Playhead(seq=9, position_s=0.0, reported_at=NOW, playing=True))
        cuts = what_it_cuts(lost, now=NOW, ready_in_s=10.0)
        assert cuts is None
        assert what_resumes(lost, cuts) is None


class TestAFlashIsNeverTheGrids:
    def test_the_grid_never_plans_a_flash_whatever_is_available(self) -> None:
        """The station breaks in for a notification; the running order never books one."""
        import random

        from src.domains.radio.grid import GridInputs, next_segment

        for seed in range(200):
            decision = next_segment(
                GridInputs(
                    session_started_at=NOW,
                    aired=(),
                    air_at=NOW + timedelta(minutes=5),
                    timezone=UTC,
                    frequencies={RadioFormat.FLASH: Frequency.OFTEN},
                    available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
                    public_mode=False,
                    voices_by_format=voices_by_format(4),
                    stop_at=None,
                ),
                random.Random(seed),
            )
            assert decision is None or decision.format is not RadioFormat.FLASH

    def test_the_desk_never_feeds_a_flash(self) -> None:
        from src.domains.radio.packs import pack_for

        assert pack_for(RadioFormat.FLASH, desk=_empty_desk()) is None

    def test_a_flash_is_the_hosts_and_bounded_by_its_notes(self) -> None:
        from src.domains.radio.formats import FORMAT_SPECS, Material, RadioRole, selectable_formats

        spec = FORMAT_SPECS[RadioFormat.FLASH]
        assert spec.material is Material.PERSONAL and spec.roles == (RadioRole.HOST,)
        assert spec.stories_max == FLASH_NOTES_MAX
        assert RadioFormat.FLASH not in selectable_formats()


def _empty_desk() -> Desk:
    from src.domains.radio.facts import clock_fact

    return Desk(
        clock=clock_fact(NOW),
        day=(),
        corner=(),
        news={},
        aired=frozenset(),
        heard_this_session=frozenset(),
        said=frozenset(),
    )


class TestWhatAFlashIsGiven:
    def test_each_note_is_a_personal_fact_keyed_like_the_corner_s(self) -> None:
        from src.domains.radio.facts import FactKind, Sensitivity
        from src.domains.radio.flash import flash_pack

        pack = flash_pack([note("m1"), note("m2")])
        assert pack.format is RadioFormat.FLASH
        assert [fact.id for fact in pack.facts] == ["f1", "f2"]
        assert [fact.key for fact in pack.facts] == ["notification:m1", "notification:m2"]
        assert {fact.kind for fact in pack.facts} == {FactKind.NOTIFICATION}
        assert {fact.sensitivity for fact in pack.facts} == {Sensitivity.PERSONAL}
        assert pack.facts[0].text.endswith('(interest): "Hello."')
